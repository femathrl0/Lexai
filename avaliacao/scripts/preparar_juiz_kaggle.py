"""Prepara os pedidos do juiz (Gemma 3 12B no Kaggle).

Dois grupos de julgamento no mesmo pacote:
  calib_<id>  as 9 respostas antigas com decisão humana (feedback pós-teste): calibração do juiz.
              O juiz não vê a decisão da revisora.
  ger_<id>    as respostas geradas pelo Qwen3 8B (output/kaggle/geracao/respostas_revisadas.jsonl).
Referência: resposta-ouro da curadoria (avaliação 09) ou pontos esperados + limites (conjuntos aprovados).
Saídas (fora do Git): output/kaggle/juiz/dataset/ e output/kaggle/juiz/kernel/.
"""
from pathlib import Path
import glob
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from worker.evidencia import guardas as g
from avaliacao.juiz import pedido_kaggle

USUARIO_KAGGLE = 'laisapaiva93'
DATASET = 'lexia-juiz-pedidos'
KERNEL = 'lexia-juiz-gemma3'
DESTINO = ROOT / 'dados/output/kaggle/juiz'


def referencias():
    refs = {}
    curadoria = pd.read_csv(next((ROOT / 'avaliacao/dados/legislacao/avaliacao_09').glob('*/perguntas_consolidadas.csv')))
    for _, q in curadoria.iterrows():
        if isinstance(q['resposta_ouro_planilha'], str) and q['resposta_ouro_planilha'].strip():
            refs[q['query_id']] = q['resposta_ouro_planilha'].strip()
    for nome in ('dev', 'test'):
        for q in json.loads((ROOT / f'avaliacao/dados/legislacao/eval_dataset_{nome}_aprovado.json').read_text(encoding='utf-8')):
            partes = [f'Pontos esperados: {q["pontos_esperados"]}' if q.get('pontos_esperados') else '',
                      f'Limites: {q["limites_resposta"]}' if q.get('limites_resposta') else '']
            if any(partes):
                refs[q['query_id']] = '\n'.join(p for p in partes if p)
    return refs


def main():
    refs = referencias()
    pedidos = []
    arquivo = glob.glob(str(ROOT / 'avaliacao/dados/legislacao/feedback_pos_teste/*/respostas_reais_e_feedback.jsonl'))[0]
    for l in Path(arquivo).read_text(encoding='utf-8').splitlines():
        if l.strip():
            r = json.loads(l)
            entrada = g.verificar_entrada(r['pergunta'])
            fontes = [dict(fonte='legislacao', caminho_relativo=f.get('caminho_relativo'), artigo_ref=f.get('artigo_ref'),
                           conteudo=f.get('conteudo_chunk', '')) for f in r['fontes_entregues']]
            pedidos.append(dict(pedido_kaggle(f'calib_{r["query_id"]}', entrada.pergunta_sanitizada, entrada.acao, fontes,
                                              r['resposta_real_modelo'], refs.get(r['query_id'])), grupo='calibracao'))
    revisadas = ROOT / 'dados/output/kaggle/geracao/respostas_revisadas.jsonl'
    for l in revisadas.read_text(encoding='utf-8').splitlines():
        if l.strip():
            r = json.loads(l)
            if r['acao'] in ('responder', 'orientar_sem_aconselhar') and r['resposta_modelo']:
                pedidos.append(dict(pedido_kaggle(f'ger_{r["pergunta_id"]}', r['pergunta_sanitizada'], r['acao'], r['fontes'],
                                                  r['resposta_modelo'], refs.get(r['pergunta_id'])), grupo='geracao'))
    (DESTINO / 'dataset').mkdir(parents=True, exist_ok=True)
    with (DESTINO / 'dataset/pedidos.jsonl').open('w', encoding='utf-8', newline='\n') as f:
        for p in pedidos:
            f.write(json.dumps(p, ensure_ascii=False) + '\n')
    (DESTINO / 'dataset/dataset-metadata.json').write_text(json.dumps(dict(
        title=DATASET, id=f'{USUARIO_KAGGLE}/{DATASET}', licenses=[dict(name='unknown')],
        description='Pedidos privados do juiz do LexIA (respostas geradas + fontes). Não redistribuir.'), indent=2), encoding='utf-8')
    (DESTINO / 'kernel').mkdir(parents=True, exist_ok=True)
    (DESTINO / 'kernel/kernel-metadata.json').write_text(json.dumps(dict(
        id=f'{USUARIO_KAGGLE}/{KERNEL}', title=KERNEL, code_file='gerar_respostas.py', language='python',
        kernel_type='script', is_private=True, enable_gpu=True, enable_tpu=False, enable_internet=True,
        machine_shape='NvidiaTeslaT4', dataset_sources=[f'{USUARIO_KAGGLE}/{DATASET}'], competition_sources=[],
        kernel_sources=[], model_sources=[]), indent=2), encoding='utf-8')
    (DESTINO / 'kernel/gerar_respostas.py').write_text((ROOT / 'scripts/kaggle_gerar_respostas.py').read_text(encoding='utf-8'),
                                                       encoding='utf-8')
    print(f'{len(pedidos)} pedidos de julgamento:', pd.Series([p['grupo'] for p in pedidos]).value_counts().to_dict(),
          '| com referência:', sum('RESPOSTA DE REFERÊNCIA' in p['mensagens'][1]['content'] for p in pedidos))


if __name__ == '__main__':
    main()
