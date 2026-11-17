"""Baixa os julgamentos do Gemma 3 12B (Kaggle), valida o JSON e cruza com as decisões humanas e os guardrails.

Saídas:
  output/kaggle/juiz/julgamentos.jsonl            julgamentos completos (fora do Git)
  reports/integracao/juiz/calibracao.csv          juiz × revisora nas 9 respostas com decisão humana
  reports/integracao/juiz/julgamentos.csv         notas e veredito por resposta gerada, com o resultado dos guardrails
Uso: python scripts/importar_juiz_kaggle.py [--sem-download]
"""
from pathlib import Path
import glob
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from avaliacao.juiz import interpretar

KERNEL = 'laisapaiva93/lexia-juiz-gemma3'
BASE = ROOT / 'dados/output/kaggle/juiz'
RELATORIOS = ROOT / 'dados/relatorios/integracao/juiz'


def main():
    resultados = BASE / 'resultados'
    resultados.mkdir(parents=True, exist_ok=True)
    if '--sem-download' not in sys.argv:
        subprocess.run(['kaggle', 'kernels', 'output', KERNEL, '-p', str(resultados), '-o'], check=True)
    pedidos = {json.loads(l)['pergunta_id']: json.loads(l)
               for l in (BASE / 'dataset/pedidos.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()}
    saidas = {json.loads(l)['pergunta_id']: json.loads(l)
              for l in (resultados / 'respostas.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()}
    julgamentos = []
    for jid, p in pedidos.items():
        s = saidas.get(jid)
        registro = dict(julgamento_id=jid, grupo=p['grupo'], valido=False, erro=None)
        if s is None:
            registro['erro'] = 'sem saída do kernel'
        elif s.get('pedido_sha256') != p['pedido_sha256']:
            registro['erro'] = 'hash do pedido diferente'
        else:
            try:
                registro.update(interpretar(s['resposta']), valido=True, segundos=s.get('segundos'))
            except (ValueError, TypeError) as e:
                registro['erro'] = str(e)[:200]
        julgamentos.append(registro)
    with (BASE / 'julgamentos.jsonl').open('w', encoding='utf-8', newline='\n') as f:
        for j in julgamentos:
            f.write(json.dumps(j, ensure_ascii=False) + '\n')

    RELATORIOS.mkdir(parents=True, exist_ok=True)
    colunas = ['fidelidade', 'correcao', 'comportamento', 'clareza']
    tabela = pd.DataFrame([{k: j.get(k) for k in ['julgamento_id', 'grupo', 'valido', 'erro', 'veredito', 'segundos', *colunas]}
                           | dict(afirmacoes=len(j.get('afirmacoes') or []),
                                  sem_apoio=sum(a.get('suporte') in ('sem_apoio', 'contradita') for a in j.get('afirmacoes') or []),
                                  jurisprudencia_entregue=len(j.get('jurisprudencia_pertinente') or []),
                                  jurisprudencia_pertinente=sum(bool(x.get('pertinente')) for x in j.get('jurisprudencia_pertinente') or []))
                           for j in julgamentos])
    humano = {}
    arquivo = glob.glob(str(ROOT / 'avaliacao/dados/legislacao/feedback_pos_teste/*/respostas_reais_e_feedback.jsonl'))[0]
    for l in Path(arquivo).read_text(encoding='utf-8').splitlines():
        if l.strip():
            r = json.loads(l)
            humano[f'calib_{r["query_id"]}'] = r['decisao_sobre_resposta_original']
    calib = tabela[tabela.grupo == 'calibracao'].assign(humano=lambda d: d.julgamento_id.map(humano))
    calib = calib.assign(concorda=calib.veredito == calib.humano)
    calib.to_csv(RELATORIOS / 'calibracao.csv', index=False, encoding='utf-8')
    geradas = tabela[tabela.grupo == 'geracao'].copy()
    revisao = ROOT / 'dados/relatorios/integracao/geracao/revisao_saida.csv'
    if revisao.exists():
        guard = pd.read_csv(revisao).set_index('pergunta_id')
        ids = geradas.julgamento_id.str.removeprefix('ger_')
        geradas['guardrail'] = ids.map(guard['aprovada']).map({True: 'aprovada', False: 'reprovada'})
        geradas['acao'] = ids.map(guard['acao'])
    geradas.to_csv(RELATORIOS / 'julgamentos.csv', index=False, encoding='utf-8')
    print('válidos:', tabela.valido.sum(), 'de', len(tabela))
    print('calibração (juiz × revisora):', int(calib.concorda.sum()), 'de', len(calib))
    print(calib[['julgamento_id', 'humano', 'veredito', *colunas]].to_string(index=False))
    print(geradas.veredito.value_counts(dropna=False).to_dict())


if __name__ == '__main__':
    main()
