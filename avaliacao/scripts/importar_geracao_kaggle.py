"""Baixa as respostas do kernel do Kaggle, valida e aplica o guardrail de saída.

Saídas:
  output/kaggle/geracao/resultados/            saída bruta do kernel (fora do Git)
  output/kaggle/geracao/respostas_revisadas.jsonl  pergunta, ação, fontes, resposta final e alertas (fora do Git)
  reports/integracao/geracao/revisao_saida.csv     uma linha por pergunta, só identificadores e métricas (no Git)
Uso: python scripts/importar_geracao_kaggle.py [--sem-download]
"""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from worker.evidencia import guardas as g
from worker.evidencia.explicador import validar_resposta, revisar

KERNEL = 'laisapaiva93/lexia-geracao-qwen3'
BASE = ROOT / 'dados/output/kaggle/geracao'
RELATORIOS = ROOT / 'dados/relatorios/integracao/geracao'


def main():
    local = '--local' in sys.argv   # plano B: geração no Ollama local (scripts/gerar_respostas_local.py)
    resultados = BASE / ('resultados_local' if local else 'resultados')
    resultados.mkdir(parents=True, exist_ok=True)
    if '--sem-download' not in sys.argv and not local:
        subprocess.run(['kaggle', 'kernels', 'output', KERNEL, '-p', str(resultados), '-o'], check=True)
    arquivo_pedidos = BASE / ('dataset_local' if local else 'dataset') / 'pedidos.jsonl'
    pedidos = [json.loads(l) for l in arquivo_pedidos.read_text(encoding='utf-8').splitlines() if l.strip()]
    respostas = {}
    for l in (resultados / 'respostas.jsonl').read_text(encoding='utf-8').splitlines():
        if l.strip():
            r = json.loads(l)
            respostas[r['pergunta_id']] = r
    linhas, revisadas = [], []
    for p in pedidos:
        if p['precisa_llm']:
            r = respostas.get(p['pergunta_id'])
            problemas = ['sem resposta do kernel'] if r is None else validar_resposta(p, r)
            texto = (r or {}).get('resposta') or ''
            segundos, tokens = (r or {}).get('segundos'), (r or {}).get('tokens_saida')
        else:
            problemas, texto, segundos, tokens = [], p['resposta_fixa'], 0, None
        saida = revisar(p, texto) if texto else g.ResultadoSaida(False, [dict(codigo='sem_resposta', detalhe='')], '')
        codigos = sorted({a['codigo'] for a in saida.alertas})
        linhas.append(dict(pergunta_id=p['pergunta_id'], origem=p['origem'], acao=p['acao'], precisa_llm=p['precisa_llm'],
                           fontes=len(p['fontes']), valida=not problemas, problemas='; '.join(problemas),
                           aprovada=saida.aprovada and not problemas,
                           bloqueantes=', '.join(c for c in codigos if c in g.BLOQUEANTES),
                           alertas=', '.join(c for c in codigos if c not in g.BLOQUEANTES),
                           segundos_geracao=segundos, tokens_saida=tokens, segundos_recuperacao=p.get('segundos_recuperacao')))
        revisadas.append(dict(pergunta_id=p['pergunta_id'], origem=p['origem'], acao=p['acao'],
                              pergunta_sanitizada=p['pergunta_sanitizada'], fontes=p['fontes'], resposta_modelo=texto,
                              resposta_final=saida.resposta_final, alertas=saida.alertas, aprovada=linhas[-1]['aprovada'],
                              problemas=problemas))
    with (BASE / 'respostas_revisadas.jsonl').open('w', encoding='utf-8', newline='\n') as f:
        for r in revisadas:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    RELATORIOS.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(linhas)
    df.to_csv(RELATORIOS / 'revisao_saida.csv', index=False, encoding='utf-8')
    resumo = json.loads((resultados / 'resumo.json').read_text(encoding='utf-8')) if (resultados / 'resumo.json').exists() else {}
    (RELATORIOS / 'resumo_kernel.json').write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding='utf-8')
    print(df.groupby(['precisa_llm', 'acao']).agg(perguntas=('aprovada', 'size'), validas=('valida', 'mean'),
                                                  aprovadas=('aprovada', 'mean')).round(2))
    print(resumo)


if __name__ == '__main__':
    main()
