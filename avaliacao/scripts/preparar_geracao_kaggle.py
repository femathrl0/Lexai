"""Prepara a geração no Kaggle: perguntas da base → guardrail de entrada → recuperação → pedidos para a LLM.

Saídas (fora do Git: contêm texto de decisões e perguntas protegidas):
  output/kaggle/geracao/dataset/pedidos.jsonl + dataset-metadata.json   (dataset privado no Kaggle)
  output/kaggle/geracao/kernel/gerar_respostas.py + kernel-metadata.json (kernel com GPU T4)
O arquivo de pedidos é gravado de forma incremental; uma nova execução continua de onde parou.
"""
from pathlib import Path
import glob
import hashlib
import json
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from worker.evidencia.indices.pgvector_store import load_database_url
from worker.evidencia.recuperador import Recuperador, Configuracao
from worker.evidencia.explicador import montar_pedido, MODELO_GERACAO, OPCOES_GERACAO

USUARIO_KAGGLE = 'laisapaiva93'
DATASET = 'lexia-geracao-pedidos'
KERNEL = 'lexia-geracao-qwen3'
DESTINO = ROOT / 'dados/output/kaggle/geracao'
COTAS = {'legislacao': 3, 'jurisprudencia': 3}


def _norm(texto):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', texto.lower()) if unicodedata.category(c) != 'Mn').split())


def perguntas_da_base():
    itens = []
    curadoria = pd.read_csv(next((ROOT / 'avaliacao/dados/legislacao/avaliacao_09').glob('*/perguntas_consolidadas.csv')))
    for _, q in curadoria.iterrows():
        itens.append(dict(pergunta_id=q['query_id'], origem='curadoria_09', tipo=q['tipo'], pergunta=q['pergunta']))
    for nome in ('dev', 'test'):
        for q in json.loads((ROOT / f'avaliacao/dados/legislacao/eval_dataset_{nome}_aprovado.json').read_text(encoding='utf-8')):
            itens.append(dict(pergunta_id=q['query_id'], origem=f'legislacao_{nome}', tipo=q.get('rotulo_resposta'), pergunta=q['pergunta']))
    for linha in (ROOT / 'avaliacao/dados/jurisprudencia/perguntas_suporte.jsonl').read_text(encoding='utf-8').splitlines():
        if linha.strip():
            q = json.loads(linha)
            itens.append(dict(pergunta_id=q['query_id'], origem='jurisprudencia_suporte', tipo=None, pergunta=q['pergunta']))
    unicos, vistos = [], set()
    for q in itens:
        chave = _norm(q['pergunta'])
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(q)
    return unicos


def escrever_metadados():
    (DESTINO / 'dataset').mkdir(parents=True, exist_ok=True)
    (DESTINO / 'dataset/dataset-metadata.json').write_text(json.dumps(dict(
        title=DATASET, id=f'{USUARIO_KAGGLE}/{DATASET}', licenses=[dict(name='unknown')],
        description='Pedidos privados de geração do LexIA (perguntas sanitizadas + fontes recuperadas). '
                    'Contém trechos de decisões não anonimizados integralmente; não redistribuir.'), indent=2), encoding='utf-8')
    (DESTINO / 'kernel').mkdir(parents=True, exist_ok=True)
    (DESTINO / 'kernel/kernel-metadata.json').write_text(json.dumps(dict(
        id=f'{USUARIO_KAGGLE}/{KERNEL}', title=KERNEL, code_file='gerar_respostas.py', language='python',
        kernel_type='script', is_private=True, enable_gpu=True, enable_tpu=False, enable_internet=True,
        machine_shape='NvidiaTeslaT4', dataset_sources=[f'{USUARIO_KAGGLE}/{DATASET}'], competition_sources=[],
        kernel_sources=[], model_sources=[]), indent=2), encoding='utf-8')
    modelo = (ROOT / 'scripts/kaggle_gerar_respostas.py').read_text(encoding='utf-8')
    (DESTINO / 'kernel/gerar_respostas.py').write_text(modelo, encoding='utf-8')


def main():
    escrever_metadados()
    arquivo = DESTINO / 'dataset/pedidos.jsonl'
    feitos = set()
    if arquivo.exists():
        feitos = {json.loads(l)['pergunta_id'] for l in arquivo.read_text(encoding='utf-8').splitlines() if l.strip()}
    perguntas = [q for q in perguntas_da_base() if q['pergunta_id'] not in feitos]
    print(f'{len(feitos)} pedidos já prontos; faltam {len(perguntas)}.', flush=True)
    if not perguntas:
        return
    recuperador = Recuperador(load_database_url(ROOT / '.env.pgvector.local'), device='cpu', carregar_reranker=True)
    config = Configuracao(entrega_por_fonte=COTAS, top_k=10)
    with arquivo.open('a', encoding='utf-8', newline='\n') as saida:
        for i, q in enumerate(perguntas, 1):
            pedido = montar_pedido(q['pergunta_id'], q['pergunta'], recuperador, config)
            pedido.update(origem=q['origem'], tipo=q['tipo'], modelo=MODELO_GERACAO, opcoes=OPCOES_GERACAO,
                          pergunta_sha256=hashlib.sha256(q['pergunta'].encode('utf-8')).hexdigest())
            saida.write(json.dumps(pedido, ensure_ascii=False) + '\n')
            saida.flush()
            print(f'{i}/{len(perguntas)} {q["pergunta_id"]} {pedido["acao"]} {pedido.get("segundos_recuperacao", "")}', flush=True)
    recuperador.fechar()


if __name__ == '__main__':
    main()
