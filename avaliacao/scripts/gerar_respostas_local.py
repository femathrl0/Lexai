"""Plano B da geração: roda os pedidos no Ollama local (GPU da máquina) em vez do Kaggle.

A placa local tem 8 GB, então usa `qwen3:8b` (Q4_K_M) em vez de `qwen3:8b-q8_0`. Os pedidos são copiados com o
modelo trocado e o hash recalculado (output/kaggle/geracao/dataset_local/pedidos.jsonl); as respostas vão para
output/kaggle/geracao/resultados_local/respostas.jsonl, no mesmo formato do kernel. Retoma de onde parou.
Depois: python scripts/importar_geracao_kaggle.py --sem-download --local
"""
from pathlib import Path
import json
import re
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from worker.evidencia.explicador import _hash

MODELO_LOCAL = 'qwen3:8b'
BASE = ROOT / 'dados/output/kaggle/geracao'


def chamar(corpo):
    req = urllib.request.Request('http://127.0.0.1:11434/api/chat', json.dumps(corpo).encode(), {'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=3600))


def main():
    origem = [json.loads(l) for l in (BASE / 'dataset/pedidos.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    (BASE / 'dataset_local').mkdir(exist_ok=True)
    pedidos = []
    for p in origem:
        p = dict(p, modelo=MODELO_LOCAL)
        if p['precisa_llm']:
            p['pedido_sha256'] = _hash(MODELO_LOCAL, p['opcoes'], p['mensagens'])
        pedidos.append(p)
    with (BASE / 'dataset_local/pedidos.jsonl').open('w', encoding='utf-8', newline='\n') as f:
        for p in pedidos:
            f.write(json.dumps(p, ensure_ascii=False) + '\n')
    saida = BASE / 'resultados_local/respostas.jsonl'
    saida.parent.mkdir(exist_ok=True)
    feitos = {json.loads(l)['pergunta_id'] for l in saida.read_text(encoding='utf-8').splitlines() if l.strip()} if saida.exists() else set()
    pendentes = [p for p in pedidos if p['precisa_llm'] and p['pergunta_id'] not in feitos]
    print(f'{len(pendentes)} pendentes', flush=True)
    with saida.open('a', encoding='utf-8', newline='\n') as f:
        for i, p in enumerate(pendentes, 1):
            opcoes, tentativas = dict(p['opcoes']), []
            for _ in range(3):
                t = time.monotonic()
                r = chamar(dict(model=p['modelo'], messages=p['mensagens'], stream=False, think=False, options=opcoes))
                texto = r['message']['content']
                problema = ('cortada' if r.get('done_reason') == 'length' else 'vazia' if len(texto.strip()) < 80 else
                            'raciocinio' if re.search(r'</?think>', texto) else None)
                tentativas.append(dict(segundos=round(time.monotonic() - t, 1), done_reason=r.get('done_reason'), problema=problema))
                if problema is None:
                    break
                if problema == 'cortada':
                    opcoes['num_predict'] = int(opcoes['num_predict']) * 2
            f.write(json.dumps(dict(pergunta_id=p['pergunta_id'], pedido_sha256=p['pedido_sha256'], modelo=p['modelo'],
                                    opcoes=opcoes, resposta=texto, done_reason=r.get('done_reason'),
                                    prompt_tokens=r.get('prompt_eval_count'), tokens_saida=r.get('eval_count'),
                                    segundos=sum(x['segundos'] for x in tentativas), tentativas=tentativas),
                               ensure_ascii=False) + '\n')
            f.flush()
            print(f'{i}/{len(pendentes)} {p["pergunta_id"]} {tentativas[-1]}', flush=True)


if __name__ == '__main__':
    main()
