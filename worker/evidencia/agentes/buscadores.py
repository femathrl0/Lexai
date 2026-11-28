"""Buscadores do Agente de Pesquisa. Mesma interface; a demo usa o que estiver disponível na máquina.

- `BuscadorLocal`: em memória, sobre o JSON de artigos (dados/processed, via DVC) e um JSONL opcional de
  jurisprudência. Busca híbrida: palavra-chave (BM25) + vetor (BGE-M3, se instalado), unidas por RRF, e
  reranker opcional. Embeddings ficam em cache em dados/output/.
- `BuscadorPgvector`: envolve o `Recuperador` herdado (precisa do banco do lex_clt.ai).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Protocol

from contratos import TrechoEvidencia

RAIZ = Path(__file__).resolve().parents[3]
ARTIGOS = RAIZ / "dados" / "processed" / "legislacao" / "legislacao_artigos_completos.json"
CACHE = RAIZ / "dados" / "output" / "cache_buscador_local"
RRF_K = 60
JANELA_RERANKER = 500  # caracteres; o reranker lê até 256 tokens (consulta + trecho). 500 > 900 na bateria de 19/11
CONSOLIDADA = ("sumula", "oj")
NOTA_SUMULA = 0.5  # nota mínima do reranker para a súmula/OJ tomar a vaga de uma ementa

NORMAS = {  # caminho -> nome curto para a citação
    "consolidacao-das-leis-do-trabalho-clt": "CLT",
    "constituicao-1988": "Constituição Federal",
    "codigo-civil": "Código Civil",
    "codigo-de-processo-civil": "CPC",
    "lei-8036-1990": "Lei 8.036/1990 (FGTS)",
    "lei-7998-1990": "Lei 7.998/1990 (seguro-desemprego)",
    "lcp-150-2015": "LC 150/2015 (doméstico)",
    "lei-6019-1974": "Lei 6.019/1974 (temporário e terceirização)",
    "lei-605-1949": "Lei 605/1949 (repouso semanal)",
    "lei-4090-1962": "Lei 4.090/1962 (13º salário)",
    "lei-12506-2011": "Lei 12.506/2011 (aviso prévio)",
    "lei-14457-2022": "Lei 14.457/2022 (Emprega + Mulheres)",
    "lei-8213-1991": "Lei 8.213/1991 (benefícios da Previdência)",
    "lei-8212-1991": "Lei 8.212/1991 (custeio da Previdência)",
    "lei-5889-1973": "Lei 5.889/1973 (trabalho rural)",
    "lei-11788-2008": "Lei 11.788/2008 (estágio)",
    "lei-7783-1989": "Lei 7.783/1989 (greve)",
    "lei-9029-1995": "Lei 9.029/1995 (discriminação)",
    "lei-7418-1985": "Lei 7.418/1985 (vale-transporte)",
    "lei-14611-2023": "Lei 14.611/2023 (igualdade salarial)",
}
# Código Civil e CPC são subsidiários e somam 60% dos artigos: na demo, ficam fora por padrão (ruído na busca).
SUBSIDIARIAS = ("codigo-civil", "codigo-de-processo-civil")


class Buscador(Protocol):
    versao: str

    def buscar(self, consulta: str, por_fonte: int = 3) -> list[TrechoEvidencia]: ...


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


PARADAS = set(_norm("""a o as os de da do das dos e em no na nos nas um uma uns umas para por com sem que se ao aos
quais qual quando como onde ou seu sua seus suas meu minha eu voce tem ter ha sobre pelo pela pelos pelas mais
isso este esta esse essa ser sao foi era""").split())


def _tokens(texto: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", _norm(texto)) if t not in PARADAS and len(t) > 1]


def _nome_norma(caminho: str) -> str:
    return next((v for k, v in NORMAS.items() if k in caminho), Path(caminho).stem)


def _limpar(texto: str) -> str:
    return re.sub(r"#+\s*|\*\*", "", texto).strip()


def _inicio_adct(artigos: list[dict]) -> int | None:
    """Posição em que começa o ADCT no arquivo da Constituição: a segunda ocorrência do "Art. 1º"."""
    inicios = sorted(a.get("posicao_inicio", 0) for a in artigos
                     if "constituicao" in a["caminho_relativo"] and re.fullmatch(r"Art\. 1º?", a["identificador_artigo"]))
    return inicios[1] if len(inicios) > 1 else None


def _numeros_artigo(consulta: str) -> set[str]:
    """Números de artigo citados na pergunta: "art. 477", "artigo 60", "arts. 457 e 458", "art. 391-A"."""
    numeros = set()
    for m in re.finditer(r"\bartigos?\b|\barts?\.?", consulta, re.IGNORECASE):
        trecho = consulta[m.end():m.end() + 40]
        lista = re.match(r"\s*((?:\d+(?:-[A-Za-z])?[ºo°]?\s*(?:,|e)?\s*)+)", trecho)
        if lista:
            numeros.update(n.upper() for n in re.findall(r"\d+(?:-[A-Za-z])?", lista.group(1)))
    return numeros


def rrf(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    esc: dict[str, float] = {}
    for ranking in rankings:
        for pos, ident in enumerate(ranking, 1):
            esc[ident] = esc.get(ident, 0.0) + 1.0 / (k + pos)
    return esc


class BuscadorLocal:
    def __init__(self, artigos: Path = ARTIGOS, jurisprudencia: Path | None = None, normas: tuple[str, ...] | None = None,
                 usar_vetor: bool = True, usar_reranker: bool = True, device: str | None = None,
                 incluir_subsidiarias: bool = False, reranker_modelo: str = "BAAI/bge-reranker-v2-m3",
                 reranker_revisao: str | None = None):
        self.docs: list[dict] = []
        todos = json.loads(Path(artigos).read_text(encoding="utf-8"))
        inicio_adct = _inicio_adct(todos)
        for a in todos:
            fora_do_recorte = (normas and not any(n in a["caminho_relativo"] for n in normas)) or (
                not incluir_subsidiarias and any(s in a["caminho_relativo"] for s in SUBSIDIARIAS))
            if a.get("status_declarado") not in (None, "in_force") or fora_do_recorte:
                continue
            norma = _nome_norma(a["caminho_relativo"])
            if inicio_adct is not None and "constituicao" in a["caminho_relativo"] and \
                    a.get("posicao_inicio", -1) >= inicio_adct:
                norma = "ADCT"  # o LawCodex põe o ADCT no mesmo arquivo da Constituição, com numeração reiniciada
            self.docs.append(dict(
                id=f"lei:{a['artigo_id'][:16]}", tipo_fonte="lei", fonte=f"{norma}, {a['identificador_artigo']}",
                texto=_limpar(a["texto_artigo_completo"]), versao=f"lawcodex:{a['sha256_fonte'][:12]}",
                origem=a.get("source")))
        if jurisprudencia and Path(jurisprudencia).exists():
            for linha in Path(jurisprudencia).read_text(encoding="utf-8").splitlines():
                if linha.strip():
                    j = json.loads(linha)
                    self.docs.append(dict(id=f"jur:{j['id']}", tipo_fonte=j.get("tipo_fonte", "ementa"),
                                          fonte=j["fonte"], texto=j["texto"], versao=j.get("versao", "recorte-demo")))
        self.versao = "local:" + hashlib.sha256("".join(d["id"] for d in self.docs).encode()).hexdigest()[:12]
        self._indexar_bm25()
        self.device = device
        self.encoder = self.reranker = self.vetores = None
        if usar_vetor:
            self._carregar_vetores()
        if usar_reranker:
            try:
                from sentence_transformers import CrossEncoder
                self.reranker = CrossEncoder(reranker_modelo, max_length=256, device=device, revision=reranker_revisao)
            except Exception as e:  # noqa: BLE001 - reranker é opcional na demo
                print(f"[buscador] reranker indisponível ({type(e).__name__}); seguindo com RRF")

    # --- palavra-chave (BM25) ---------------------------------------------------------------------------------
    def _indexar_bm25(self) -> None:
        self.tf = [Counter(_tokens(d["fonte"] + " " + d["texto"])) for d in self.docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.media = sum(self.len) / max(len(self.len), 1)
        df = Counter(t for c in self.tf for t in c)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def _bm25(self, consulta: str, k: int, k1: float = 1.5, b: float = 0.75) -> list[int]:
        q = _tokens(consulta)
        # "art. 477" na pergunta: o número do artigo vira um sinal forte, como no full-text do Postgres.
        numeros = _numeros_artigo(consulta)
        esc = []
        for i, tf in enumerate(self.tf):
            s = sum(self.idf.get(t, 0) * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * self.len[i] / self.media))
                    for t in q if t in tf)
            if numeros and any(re.search(rf"\bArt\. {re.escape(n)}(?:º)?(?![\w-])", self.docs[i]["fonte"])
                               for n in numeros):
                s += 10
            if s > 0:
                esc.append((s, i))
        return [i for _, i in sorted(esc, reverse=True)[:k]]

    # --- vetor (BGE-M3) ---------------------------------------------------------------------------------------
    def _carregar_vetores(self) -> None:
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
        except ImportError:
            print("[buscador] sentence-transformers não instalado; só palavra-chave")
            return
        self.encoder = SentenceTransformer("BAAI/bge-m3", device=self.device)
        self.encoder.max_seq_length = 512
        CACHE.mkdir(parents=True, exist_ok=True)
        arq = CACHE / f"{self.versao}.npy"
        if arq.exists():
            self.vetores = np.load(arq)
        else:
            print(f"[buscador] gerando embeddings de {len(self.docs)} trechos (uma vez; fica em {arq})")
            self.vetores = self.encoder.encode([d["fonte"] + "\n" + d["texto"] for d in self.docs], batch_size=16,
                                               normalize_embeddings=True, show_progress_bar=True,
                                               convert_to_numpy=True).astype("float32")
            np.save(arq, self.vetores)

    def _vetor(self, consulta: str, k: int) -> list[int]:
        if self.vetores is None:
            return []
        import numpy as np
        q = self.encoder.encode([consulta], normalize_embeddings=True, convert_to_numpy=True)[0].astype("float32")
        return list(np.argsort(-(self.vetores @ q))[:k])

    # --- busca ------------------------------------------------------------------------------------------------
    def buscar(self, consulta: str, por_fonte: int = 3, candidatos: int = 30) -> list[TrechoEvidencia]:
        fundidos = rrf([[str(i) for i in self._bm25(consulta, candidatos)],
                        [str(i) for i in self._vetor(consulta, candidatos)]])
        ordem = sorted(fundidos, key=lambda i: -fundidos[i])[:candidatos]
        notas = {i: fundidos[i] for i in ordem}
        if self.reranker is not None and ordem:
            # O reranker lê ~256 tokens: em artigo longo, julga a janela mais parecida com a consulta (ex.: a alínea
            # da gestante no fim do art. 10 do ADCT), não o começo do artigo.
            pares = [(consulta, self._janela_relevante(self.docs[int(i)], consulta)) for i in ordem]
            for i, s in zip(ordem, self.reranker.predict(pares, show_progress_bar=False), strict=True):
                notas[i] = float(s)
            ordem.sort(key=lambda i: -notas[i])
        # Garante os dois tipos de fonte no topo (manual): cota por tipo antes de entregar.
        escolhidos, por_tipo = [], Counter()
        for i in ordem:
            grupo = "lei" if self.docs[int(i)]["tipo_fonte"] == "lei" else "jurisprudencia"
            if por_tipo[grupo] < por_fonte:
                por_tipo[grupo] += 1
                escolhidos.append(i)
        if self.reranker is not None:
            escolhidos = self._priorizar_sumula(ordem, escolhidos, notas)
        saida = []
        for i in escolhidos:
            d = self.docs[int(i)]
            saida.append(TrechoEvidencia(id=d["id"], indice="corpus_juridico", tipo_fonte=d["tipo_fonte"],
                                         texto=d["texto"][:4000], fonte=d["fonte"], versao=d["versao"],
                                         nota_reranker=round(notas[i], 4)))
        return saida


    def _janela_relevante(self, doc: dict, consulta: str, tamanho: int = JANELA_RERANKER) -> str:
        """Lei: rótulo + a janela de parágrafos seguidos com mais termos da consulta (pesados pelo IDF)."""
        texto = doc["texto"]
        cabeca = doc["fonte"] + "\n"
        if doc["tipo_fonte"] != "lei":  # súmula e ementa: o essencial está no começo (verbetação)
            return cabeca + texto[:2000]
        if len(texto) <= tamanho:
            return cabeca + texto
        termos = set(_tokens(consulta))
        paragrafos = [x for x in texto.split("\n") if x.strip()]
        melhor, nota_melhor = texto[:tamanho], -1.0
        for ini in range(len(paragrafos)):
            janela = ""
            for par in paragrafos[ini:]:
                if janela and len(janela) + len(par) > tamanho:
                    break
                janela = f"{janela}\n{par}" if janela else par
            nota = sum(self.idf.get(t, 0) for t in termos & set(_tokens(janela)))
            if nota > nota_melhor:
                melhor, nota_melhor = janela[:tamanho], nota
        return cabeca + melhor

    def _priorizar_sumula(self, ordem: list[str], escolhidos: list[str], notas: dict) -> list[str]:
        """Súmula ou OJ relevante (nota ≥ NOTA_SUMULA) entra no lugar da última ementa de caso concreto: é o
        entendimento consolidado do tribunal, mais útil para explicar a regra do que um caso isolado."""
        tipo = {i: self.docs[int(i)]["tipo_fonte"] for i in ordem}
        if any(tipo[i] in CONSOLIDADA for i in escolhidos):
            return escolhidos
        sumula = next((i for i in ordem if tipo[i] in CONSOLIDADA and notas[i] >= NOTA_SUMULA), None)
        ementas = [i for i in escolhidos if tipo[i] not in ("lei", *CONSOLIDADA)]
        if sumula is None or not ementas:  # com vaga sobrando a súmula já teria entrado pela ordem
            return escolhidos
        trocada = ementas[-1]
        return [sumula if i == trocada else i for i in escolhidos]


class BuscadorPgvector:
    """Adapta o `Recuperador` herdado (worker/evidencia/recuperador.py) ao contrato `TrechoEvidencia`."""

    def __init__(self, database_url: str, device: str = "cpu"):
        from worker.evidencia.recuperador import Configuracao, Recuperador

        self.rec = Recuperador(database_url, device=device)
        self.config = Configuracao(entrega_por_fonte={"legislacao": 3, "jurisprudencia": 3})
        self.versao = f"pgvector:{self.rec.dataset_jurisprudencia[:12]}"

    def buscar(self, consulta: str, por_fonte: int = 3) -> list[TrechoEvidencia]:
        from worker.evidencia.explicador import fonte_para_prompt

        self.config.entrega_por_fonte = {"legislacao": por_fonte, "jurisprudencia": por_fonte}
        unidades, _ = self.rec.buscar(consulta, self.config)
        saida = []
        for u in unidades:
            f = fonte_para_prompt(u)
            lei = u["fonte"] == "legislacao"
            rotulo = (f"{_nome_norma(f.get('caminho_relativo') or '')}, {f.get('artigo_ref')}" if lei else
                      " · ".join(str(x) for x in (f.get("tribunal"), f.get("processo"), f.get("data_julgamento")) if x))
            saida.append(TrechoEvidencia(id=f"{'lei' if lei else 'jur'}:{str(u['unidade'])[:16]}", indice="corpus_juridico",
                                         tipo_fonte="lei" if lei else "ementa", texto=f["conteudo"][:4000],
                                         fonte=rotulo or "fonte sem rótulo", versao=self.versao,
                                         nota_reranker=round(float(u["escore"]), 4)))
        return saida
