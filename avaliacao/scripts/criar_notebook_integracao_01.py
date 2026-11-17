"""Cria notebooks/03_integracao/01_recuperacao_conjunta.ipynb (código; as saídas vêm da execução).

Gera a primeira versão (seções 1 a 8). As seções 9 (custo do reranker), 10 (busca lexical com IDF) e as
conclusões atualizadas foram editadas diretamente no notebook, que é a versão de referência; não regenere
o notebook com este script sem reaplicar essas seções.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
DESTINO = ROOT / 'notebooks/03_integracao/01_recuperacao_conjunta.ipynb'

celulas = []


def md(ident, texto):
    celulas.append(dict(cell_type='markdown', id=ident, metadata={}, source=texto.strip().splitlines(keepends=True)))


def code(ident, texto):
    celulas.append(dict(cell_type='code', id=ident, metadata={}, execution_count=None, outputs=[],
                        source=texto.strip().splitlines(keepends=True)))


md('int01_intro', '''
# 01 — Recuperação conjunta: legislação e jurisprudência

Este notebook implementa e avalia a **recuperação conjunta** do LexIA: um único fluxo consulta as duas coleções do mesmo banco PostgreSQL/pgvector e combina os resultados.

| Fonte | Coleção | Unidade buscada | Unidade entregue |
|---|---|---|---|
| Legislação | `lex_clt.chunk_embeddings` (estratégia D, 10.971 chunks) | parágrafo completo | artigo completo (estratégia A) |
| Jurisprudência | `lex_jurisprudencia.embeddings` (303.257 chunks) | janela de 500 tokens | trecho da decisão, com tribunal, processo e data |

Em cada fonte, a busca semântica (BGE-M3) e a busca lexical (full-text search do PostgreSQL) são fundidas por **RRF**. As duas fontes entram na combinação com uma **cota de candidatos** cada, e o cross-encoder **bge-reranker-v2-m3** reordena a lista combinada. Chunks do mesmo artigo ou da mesma decisão são agrupados em uma única unidade.

A busca lexical usa visões materializadas no schema próprio `lex_integracao`; as tabelas de legislação e de jurisprudência não são alteradas. O código está em `src/integracao/recuperacao.py` e `src/integracao/avaliacao_recuperacao.py`.
''')

md('int01_setup_texto', '## 1. Configuração e conexão')
code('int01_setup', r'''
from pathlib import Path
import sys, json, time
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, Markdown
ROOT = next(p for p in (Path.cwd(), *Path.cwd().parents) if (p / 'src/integracao').exists())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from worker.evidencia.indices.pgvector_store import load_database_url
from worker.evidencia.recuperador import Recuperador, Configuracao, LEGISLACAO_D, LEGISLACAO_A
from avaliacao import recuperacao as av

RELATORIOS = ROOT / 'dados/relatorios/integracao/recuperacao'
RELATORIOS.mkdir(parents=True, exist_ok=True)
EXECUTAR_AVALIACAO = False   # True recalcula todas as configurações (cerca de 30 min em CPU)
recuperador = Recuperador(load_database_url(ROOT / '.env.pgvector.local'), device='cpu', carregar_reranker=True)
print('Dataset de jurisprudência:', recuperador.dataset_jurisprudencia[:12], '| legislação D:', LEGISLACAO_D[:12], '| A:', LEGISLACAO_A[:12])
''')

md('int01_lexico_texto', '''
## 2. Índice lexical no PostgreSQL

As visões `lex_integracao.lexico_legislacao` e `lex_integracao.lexico_jurisprudencia` guardam o `tsvector` (configuração `portuguese`) de cada chunk, com índice GIN. A consulta usa os lexemas da pergunta combinados com OU e ordena por `ts_rank_cd`. A criação é idempotente.
''')
code('int01_lexico', r'''
inicio = time.monotonic()
contagens = recuperador.preparar_lexico()
display(pd.Series(contagens, name='chunks indexados').to_frame())
print(f'Índice lexical pronto em {time.monotonic() - inicio:.0f} s.')
''')

md('int01_exemplo_texto', '''
## 3. Exemplo de busca integrada

Uma pergunta, as duas fontes e o resultado final após fusão e reranking. Para cada unidade entregue, a fonte, a identificação e o início do texto.
''')
code('int01_exemplo', r'''
pergunta = 'Qual é o adicional devido pelo trabalho noturno urbano?'
entregues, diagnostico = recuperador.buscar(pergunta, Configuracao(top_k=6))
linhas = []
for i, u in enumerate(entregues, 1):
    m = u['metadata']
    ident = (m.get('artigo_ref'), m.get('caminho_relativo', '').split('/')[-1]) if u['fonte'] == 'legislacao' \
        else (m.get('tribunal'), m.get('data_julgamento') or m.get('data_publicacao'))
    linhas.append(dict(posicao=i, fonte=u['fonte'], identificacao=' | '.join(str(x) for x in ident if x),
                       escore_reranker=round(u['escore'], 3), inicio_do_texto=u['texto'][:140].replace('\n', ' ')))
display(pd.DataFrame(linhas))
print(f"{diagnostico['candidatos']} candidatos, {diagnostico['unidades']} unidades, {diagnostico['segundos']:.1f} s.")
''')

md('int01_gabaritos_texto', '''
## 4. Gabaritos usados na avaliação

- **Legislação:** perguntas respondíveis dos conjuntos aprovados de desenvolvimento e teste, com norma e artigo esperados. As perguntas sem resposta ficam para os guardrails.
- **Jurisprudência:** perguntas de ajuste com intervalos de suporte anotados. A reserva do teste final do notebook 04 de jurisprudência não é usada.

Todos os documentos de jurisprudência citados no gabarito pertencem ao recorte indexado.
''')
code('int01_gabaritos', r'''
gab_leg = av.gabarito_legislacao(ROOT)
gab_jur = av.gabarito_jurisprudencia(ROOT)
registros = sorted({r for q in gab_jur for r in q['registros']})
presentes = recuperador.conexao.execute(
    'SELECT count(DISTINCT registro_id) FROM lex_jurisprudencia.embeddings WHERE dataset_id=%s AND registro_id = ANY(%s)',
    (recuperador.dataset_jurisprudencia, registros)).fetchone()[0]
assert presentes == len(registros), 'Documento do gabarito fora do índice.'
display(pd.DataFrame([dict(fonte='legislacao', perguntas=len(gab_leg)), dict(fonte='jurisprudencia', perguntas=len(gab_jur),
                      documentos_de_suporte=len(registros), presentes_no_indice=presentes)]))
''')

md('int01_avaliacao_texto', '''
## 5. Avaliação das configurações

Cada fonte é avaliada sozinha em quatro configurações (semântica, lexical, híbrida por RRF e híbrida com reranker). Na **configuração integrada**, as duas fontes disputam as mesmas posições, e cada pergunta é avaliada pela posição da unidade correta na lista combinada.

Métricas: **Hit@k** (a unidade correta está entre as k primeiras), **MRR@10** (inverso da posição da primeira correta) e, na jurisprudência, **cobertura de suporte@k** (fração dos caracteres anotados presentes nos chunks recuperados). Os resultados ficam em `reports/integracao/recuperacao/resultados_por_pergunta.parquet`.
''')
code('int01_avaliacao', r'''
arquivo = RELATORIOS / 'resultados_por_pergunta.parquet'
configs = {
    'semantica':         dict(usar_lexical=False, usar_reranker=False),
    'lexical':           dict(usar_semantica=False, usar_reranker=False),
    'hibrida_rrf':       dict(usar_reranker=False),
    'hibrida_reranker':  dict(),
}
if EXECUTAR_AVALIACAO or not arquivo.exists():
    partes = []
    for nome, opcoes in configs.items():
        for fonte, gab in (('legislacao', gab_leg), ('jurisprudencia', gab_jur)):
            cfg = Configuracao(fontes=(fonte,), top_k=10, **opcoes)
            partes.append(av.avaliar(recuperador, gab, cfg, f'{nome} | {fonte} sozinha'))
            print('concluído:', nome, fonte, flush=True)
    for nome in ('hibrida_rrf', 'hibrida_reranker'):
        cfg = Configuracao(top_k=10, **configs[nome])
        partes.append(av.avaliar(recuperador, gab_leg + gab_jur, cfg, f'{nome} | integrada'))
        print('concluído:', nome, 'integrada', flush=True)
    resultados = pd.concat(partes, ignore_index=True)
    resultados.to_parquet(arquivo, index=False)
else:
    resultados = pd.read_parquet(arquivo)
tabela = av.resumo(resultados)
tabela.to_csv(RELATORIOS / 'resumo_metricas.csv', index=False)
display(tabela)
''')

md('int01_graficos_texto', '## 6. Gráficos')
code('int01_graficos', r'''
fig, eixos = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
for eixo, fonte in zip(eixos, ('legislacao', 'jurisprudencia')):
    t = tabela[tabela.fonte == fonte].set_index('configuracao')[['hit@1', 'hit@3', 'hit@5', 'mrr@10']]
    t.plot.barh(ax=eixo, width=0.8)
    eixo.set_title(f'{fonte.capitalize()} — perguntas do gabarito ({int(tabela[tabela.fonte == fonte].perguntas.iloc[0])})')
    eixo.set_xlim(0, 1)
    eixo.set_xlabel('proporção / MRR')
    eixo.legend(loc='lower right')
fig.suptitle('Recuperação por configuração (sozinha × integrada)')
fig.tight_layout()
fig.savefig(RELATORIOS / 'recuperacao_por_configuracao.png', dpi=130)
plt.show()
''')

md('int01_erros_texto', '''
## 7. Perguntas em que a unidade correta não aparece no topo

Lista, na melhor configuração integrada, as perguntas cuja unidade correta ficou fora das 3 primeiras posições. São os casos a investigar antes da geração.
''')
code('int01_erros', r'''
integrada = resultados[resultados.configuracao == 'hibrida_reranker | integrada']
falhas = integrada[integrada['hit@3'] == 0][['fonte', 'query_id', 'posicao', 'unidades']]
perguntas = {q['query_id']: q['pergunta'] for q in gab_leg + gab_jur}
falhas = falhas.assign(pergunta=falhas.query_id.map(perguntas).str.slice(0, 110))
display(falhas)
print(f'{len(falhas)} de {len(integrada)} perguntas sem a unidade correta entre as 3 primeiras.')
''')

md('int01_tempo_texto', '## 8. Tempo por pergunta')
code('int01_tempo', r'''
display(resultados.groupby('configuracao').segundos.describe()[['mean', '50%', 'max']].round(1))
''')

md('int01_conclusao', '''
## 9. Conclusões

As conclusões são preenchidas após a execução, a partir das tabelas e dos gráficos acima.
''')

DESTINO.parent.mkdir(parents=True, exist_ok=True)
if DESTINO.exists():
    raise SystemExit(f'{DESTINO} já existe; preserve as edições.')
nb = dict(cells=celulas, nbformat=4, nbformat_minor=5,
          metadata=dict(kernelspec=dict(display_name='Python (.venv lex_clt.ai)', language='python', name='lex-clt-ai'),
                        language_info=dict(name='python')))
DESTINO.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
for c in celulas:
    if c['cell_type'] == 'code':
        compile(''.join(c['source']), c['id'], 'exec')
print('Notebook criado:', DESTINO)
