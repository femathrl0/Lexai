"""Recuperação conjunta de legislação e jurisprudência no mesmo banco PostgreSQL/pgvector.

Fluxo por pergunta:
  1. Para cada fonte, busca semântica (BGE-M3, cosseno no pgvector) e busca lexical (full-text search do
     PostgreSQL, configuração 'portuguese'), fundidas por RRF (k=60).
  2. As listas das duas fontes são combinadas com uma cota de candidatos por fonte e, opcionalmente,
     reordenadas pelo cross-encoder bge-reranker-v2-m3 (o mesmo do notebook 06 de legislação).
  3. Entrega: na legislação, o artigo completo (estratégia A) do chunk de parágrafo encontrado (D → A);
     na jurisprudência, o trecho da decisão com tribunal, processo, órgão julgador e data. Resultados
     repetidos do mesmo artigo ou da mesma decisão são agrupados.

A busca lexical usa visões materializadas no schema próprio `lex_integracao`, com índices GIN; as tabelas
de legislação (`lex_clt`) e de jurisprudência (`lex_jurisprudencia`) não são alteradas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import time

import numpy as np

LEGISLACAO_D = '036e49f3a30a99ea706fce9be2f8301aabf5817c81e9f700535753b046657313'  # D_paragrafo_completo
LEGISLACAO_A = '508abda2246b7cc1db28bd9b0bf762bddfb2a5696f6681ec22e99b60108876f9'  # A_artigo
MODELO = 'BAAI/bge-m3'
REVISAO = '5617a9f61b028005a4858fdac845db406aefb181'
RERANKER = 'BAAI/bge-reranker-v2-m3'
RRF_K = 60
FONTES = ('legislacao', 'jurisprudencia')

DDL_LEXICO = """
CREATE SCHEMA IF NOT EXISTS lex_integracao;
CREATE MATERIALIZED VIEW IF NOT EXISTS lex_integracao.lexico_legislacao AS
  SELECT chunk_id, article_id, to_tsvector('portuguese', text_content) AS tsv
  FROM lex_clt.chunk_embeddings WHERE dataset_id = %(d)s;
CREATE INDEX IF NOT EXISTS lexico_legislacao_tsv ON lex_integracao.lexico_legislacao USING GIN (tsv);
CREATE UNIQUE INDEX IF NOT EXISTS lexico_legislacao_id ON lex_integracao.lexico_legislacao (chunk_id);
CREATE MATERIALIZED VIEW IF NOT EXISTS lex_integracao.lexico_jurisprudencia AS
  SELECT chunk_id, registro_id, to_tsvector('portuguese', texto) AS tsv
  FROM lex_jurisprudencia.embeddings WHERE dataset_id = %(j)s;
CREATE INDEX IF NOT EXISTS lexico_jurisprudencia_tsv ON lex_integracao.lexico_jurisprudencia USING GIN (tsv);
CREATE UNIQUE INDEX IF NOT EXISTS lexico_jurisprudencia_id ON lex_integracao.lexico_jurisprudencia (chunk_id);
"""


def rrf(rankings, k=RRF_K):
    """Reciprocal Rank Fusion: soma 1/(k+posição) de cada lista; não depende da escala dos escores."""
    escores = {}
    for ranking in rankings:
        for posicao, ident in enumerate(ranking, 1):
            escores[ident] = escores.get(ident, 0.0) + 1.0 / (k + posicao)
    return sorted(escores, key=lambda i: (-escores[i], i)), escores


@dataclass
class Configuracao:
    fontes: tuple = FONTES
    candidatos_por_busca: int = 50       # por fonte, em cada busca (semântica e lexical)
    cota_por_fonte: int = 10             # candidatos de cada fonte enviados à combinação (notebook 01, seção 9)
    usar_lexical: bool = True
    usar_semantica: bool = True
    usar_reranker: bool = True
    top_k: int = 5                       # unidades entregues (artigos ou decisões), sem cotas
    # Cotas de entrega por fonte, por exemplo {'legislacao': 3, 'jurisprudencia': 3}. Com cotas, cada fonte
    # mantém o próprio ranking e reserva suas posições; sem cotas, uma única lista combinada é cortada em top_k.
    entrega_por_fonte: dict | None = None
    reranker_max_length: int | None = 256    # tokens lidos por par pergunta–trecho (None = valor do carregamento)
    lexical_modo: str = 'idf'            # 'idf', 'ts_rank' ou 'ts_rank_cd' (primeira versão)
    lexical_poda: float = 0.20           # descarta lexemas presentes em mais dessa fração dos chunks (modo idf)
    extras: dict = field(default_factory=dict)


class Recuperador:
    def __init__(self, database_url, device='cpu', carregar_reranker=True, reranker_max_length=512):
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
        os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
        import psycopg
        from pgvector.psycopg import register_vector
        from sentence_transformers import SentenceTransformer
        self.conexao = psycopg.connect(database_url, connect_timeout=10, autocommit=True)
        register_vector(self.conexao)
        self.dataset_jurisprudencia = self._dataset_jurisprudencia()
        self._df = {}   # frequência de documentos por (fonte, lexema), usada no IDF da busca lexical
        self.encoder = SentenceTransformer(MODELO, revision=REVISAO, device=device, local_files_only=True)
        self.encoder.max_seq_length = 8192
        self.reranker = None
        if carregar_reranker:
            from sentence_transformers import CrossEncoder
            self.reranker = CrossEncoder(RERANKER, max_length=reranker_max_length, device=device, local_files_only=True)
            self._max_length_original = self.reranker.max_length

    # --- preparação -------------------------------------------------------------------------------------
    def _dataset_jurisprudencia(self):
        linhas = self.conexao.execute(
            "SELECT dataset_id FROM lex_jurisprudencia.datasets WHERE estado='validado'").fetchall()
        if len(linhas) != 1:
            raise ValueError(f'Esperado um dataset de jurisprudência validado; encontrados {len(linhas)}.')
        return linhas[0][0]

    def preparar_lexico(self):
        """Cria (uma vez) as visões materializadas e os índices GIN da busca lexical."""
        import re
        ids = dict(d=LEGISLACAO_D, j=self.dataset_jurisprudencia)
        if not all(re.fullmatch(r'[0-9a-f]{64}', v) for v in ids.values()):
            raise ValueError('Identificador de dataset inválido.')
        # DDL não aceita parâmetros: os IDs, já validados como hexadecimais, entram como literais.
        for comando in filter(str.strip, DDL_LEXICO.split(';')):
            self.conexao.execute(comando.replace('%(d)s', f"'{ids['d']}'").replace('%(j)s', f"'{ids['j']}'"))
        contagens = {}
        for fonte in FONTES:
            contagens[fonte] = self.conexao.execute(f'SELECT count(*) FROM lex_integracao.lexico_{fonte}').fetchone()[0]
        return contagens

    # --- buscas por fonte -------------------------------------------------------------------------------
    def vetor(self, pergunta):
        v = self.encoder.encode([pergunta], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)[0]
        return np.asarray(v, dtype=np.float32)

    def semantica(self, fonte, vetor, k):
        if fonte == 'legislacao':
            sql = ('SELECT chunk_id FROM lex_clt.chunk_embeddings WHERE dataset_id=%s '
                   'ORDER BY embedding <=> %s, row_index LIMIT %s')
            parametros = (LEGISLACAO_D, vetor, k)
        else:
            sql = ('SELECT chunk_id FROM lex_jurisprudencia.embeddings WHERE dataset_id=%s '
                   'ORDER BY embedding <=> %s, chunk_id LIMIT %s')
            parametros = (self.dataset_jurisprudencia, vetor, k)
        return [r[0] for r in self.conexao.execute(sql, parametros).fetchall()]

    def _frequencia(self, fonte, lexema):
        """Número de chunks da fonte que contêm o lexema; lexema=None dá o total de chunks (cache em memória)."""
        chave = (fonte, lexema)
        if chave not in self._df:
            sql = f'SELECT count(*) FROM lex_integracao.lexico_{fonte}'
            if lexema is None:
                self._df[chave] = self.conexao.execute(sql).fetchone()[0]
            else:
                self._df[chave] = self.conexao.execute(
                    sql + " WHERE tsv @@ to_tsquery('portuguese', %s)", (lexema,)).fetchone()[0]
        return self._df[chave]

    def lexical(self, fonte, pergunta, k, modo='idf', poda=0.20):
        """Busca lexical com os lexemas da pergunta (sem stopwords) combinados com OU.

        modo='idf': ordena pela soma dos pesos IDF (fórmula do BM25) dos lexemas presentes no chunk; lexemas que
        aparecem em mais de `poda` dos chunks são descartados (equivalem a stopwords do domínio, como "trabalho").
        modo='ts_rank' ou 'ts_rank_cd': ordenação nativa do PostgreSQL, sem IDF. ts_rank_cd foi a primeira versão
        e é a pior: favorece chunks curtos com termos genéricos (ver notebook 01, seção 10).
        """
        import math
        lexemas = self.conexao.execute(
            "SELECT tsvector_to_array(to_tsvector('portuguese', %s))", (pergunta,)).fetchone()[0] or []
        if modo == 'idf':
            total = self._frequencia(fonte, None)
            presentes = [l for l in lexemas if self._frequencia(fonte, l)]
            lexemas = [l for l in presentes if self._frequencia(fonte, l) / total <= poda] or presentes
        if not lexemas:
            return []
        consulta = ' | '.join(lexemas)
        if modo == 'idf':
            pesos = [math.log((total - self._frequencia(fonte, l) + 0.5) / (self._frequencia(fonte, l) + 0.5) + 1)
                     for l in lexemas]
            soma = ' + '.join(f"(CASE WHEN tsv @@ to_tsquery('portuguese', %s) THEN {p:.6f} ELSE 0 END)" for p in pesos)
            sql = (f"SELECT chunk_id FROM lex_integracao.lexico_{fonte}, to_tsquery('portuguese', %s) q WHERE tsv @@ q "
                   f'ORDER BY ({soma}) DESC, ts_rank_cd(tsv, q, 32) DESC, chunk_id LIMIT %s')
            parametros = (consulta, *lexemas, k)
        elif modo in ('ts_rank', 'ts_rank_cd'):
            sql = (f"SELECT chunk_id FROM lex_integracao.lexico_{fonte}, to_tsquery('portuguese', %s) q "
                   f'WHERE tsv @@ q ORDER BY {modo}(tsv, q) DESC, chunk_id LIMIT %s')
            parametros = (consulta, k)
        else:
            raise ValueError(f'Modo lexical desconhecido: {modo}')
        return [r[0] for r in self.conexao.execute(sql, parametros).fetchall()]

    def buscar_fonte(self, fonte, pergunta, config, vetor=None):
        listas = []
        if config.usar_semantica:
            listas.append(self.semantica(fonte, vetor if vetor is not None else self.vetor(pergunta), config.candidatos_por_busca))
        if config.usar_lexical:
            listas.append(self.lexical(fonte, pergunta, config.candidatos_por_busca, config.lexical_modo, config.lexical_poda))
        ordem, escores = rrf(listas)
        return [dict(fonte=fonte, chunk_id=c, rrf=escores[c]) for c in ordem]

    # --- conteúdo e entrega -----------------------------------------------------------------------------
    def conteudo(self, candidatos):
        por_fonte = {f: [c['chunk_id'] for c in candidatos if c['fonte'] == f] for f in FONTES}
        dados = {}
        if por_fonte['legislacao']:
            for cid, art, texto, meta in self.conexao.execute(
                    'SELECT chunk_id, article_id, text_content, metadata FROM lex_clt.chunk_embeddings '
                    'WHERE dataset_id=%s AND chunk_id = ANY(%s)', (LEGISLACAO_D, por_fonte['legislacao'])).fetchall():
                dados[('legislacao', cid)] = dict(texto=texto, unidade=art, metadata=meta)
        if por_fonte['jurisprudencia']:
            for cid, reg, texto, meta in self.conexao.execute(
                    'SELECT chunk_id, registro_id, texto, metadata FROM lex_jurisprudencia.embeddings '
                    'WHERE dataset_id=%s AND chunk_id = ANY(%s)', (self.dataset_jurisprudencia, por_fonte['jurisprudencia'])).fetchall():
                dados[('jurisprudencia', cid)] = dict(texto=texto, unidade=reg, metadata=meta)
        return [dict(c, **dados[(c['fonte'], c['chunk_id'])]) for c in candidatos]

    def artigos(self, article_ids):
        linhas = self.conexao.execute(
            'SELECT article_id, text_content, metadata FROM lex_clt.chunk_embeddings WHERE dataset_id=%s AND article_id = ANY(%s)',
            (LEGISLACAO_A, list(article_ids))).fetchall()
        return {a: dict(texto=t, metadata=m) for a, t, m in linhas}

    def buscar(self, pergunta, config=None):
        """Retorna (unidades entregues, diagnóstico). Unidade = artigo (legislação) ou decisão (jurisprudência)."""
        config = config or Configuracao()
        inicio = time.monotonic()
        vetor = self.vetor(pergunta) if config.usar_semantica else None
        candidatos = []
        for fonte in config.fontes:
            candidatos += self.buscar_fonte(fonte, pergunta, config, vetor)[:config.cota_por_fonte]
        candidatos = self.conteudo(candidatos)
        if config.usar_reranker and self.reranker is not None and candidatos:
            self.reranker.max_length = config.reranker_max_length or self._max_length_original
            escores = self.reranker.predict([(pergunta, c['texto']) for c in candidatos], show_progress_bar=False)
            for c, s in zip(candidatos, escores):
                c['rerank'] = float(s)
            candidatos.sort(key=lambda c: (-c['rerank'], c['chunk_id']))
        else:
            candidatos.sort(key=lambda c: (-c['rrf'], c['fonte'], c['chunk_id']))
        # Agrupa por unidade (artigo ou decisão), mantendo a melhor posição e todos os chunks encontrados.
        unidades, vistas = [], {}
        for posicao, c in enumerate(candidatos, 1):
            chave = (c['fonte'], c['unidade'])
            if chave in vistas:
                vistas[chave]['chunks'].append(c)
                continue
            u = dict(fonte=c['fonte'], unidade=c['unidade'], posicao_chunk=posicao, chunks=[c],
                     escore=c.get('rerank', c['rrf']))
            vistas[chave] = u
            unidades.append(u)
        por_fonte = {f: [u for u in unidades if u['fonte'] == f] for f in config.fontes}
        if config.entrega_por_fonte:
            # Cada fonte entrega suas melhores unidades; a legislação vem antes da jurisprudência no contexto.
            entregues = [u for f in config.fontes for u in por_fonte[f][:config.entrega_por_fonte.get(f, 0)]]
        else:
            entregues = unidades[:config.top_k]
        artigos = self.artigos([u['unidade'] for u in entregues if u['fonte'] == 'legislacao'])
        for u in entregues:
            if u['fonte'] == 'legislacao':
                a = artigos.get(u['unidade'])
                u['texto'] = a['texto'] if a else u['chunks'][0]['texto']
                u['metadata'] = a['metadata'] if a else u['chunks'][0]['metadata']
            else:
                u['texto'] = u['chunks'][0]['texto']
                u['metadata'] = u['chunks'][0]['metadata']
        diagnostico = dict(segundos=time.monotonic() - inicio, candidatos=len(candidatos), unidades=len(unidades),
                           ranking_unidades=[(u['fonte'], u['unidade']) for u in unidades],
                           ranking_por_fonte={f: [(u['fonte'], u['unidade']) for u in lista] for f, lista in por_fonte.items()},
                           com_cotas=bool(config.entrega_por_fonte),
                           candidatos_detalhe=[dict(fonte=c['fonte'], unidade=c['unidade'], metadata=c['metadata'])
                                               for c in candidatos])
        return entregues, diagnostico

    def fechar(self):
        self.conexao.close()
