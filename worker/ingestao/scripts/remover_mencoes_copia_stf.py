"""Remove dos notebooks 01–03 e dos textos de apresentação as menções à cópia oficial de 50.000 registros STF.

A cópia (train-00002.hf.parquet) nunca integrou a base. A seção 5.2 do notebook 03 passa a tratar apenas
do arquivo local em quarentena. Frases que citam a cópia são removidas; os demais textos são mantidos.
"""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
NB_DIR = ROOT / 'notebooks/02_jurisprudencia'
MENCAO = re.compile(r'[Cc]ópia oficial|[Cc]ópia adicional|50\.000 registros STF|50\.000 registros declarados|'
                    r'shard oficial|registros STF adicionais')

SECAO_52 = '''### 5.2. Arquivo em quarentena

O arquivo local `train-00002.parquet` não pôde ser lido (erro de leitura nos metadados do Parquet) e permanece em quarentena, fora da base ativa. O original não foi alterado nem reparado; o diagnóstico técnico está abaixo.

Os registros do STF da base atual vêm de `train-00000.parquet`, `train-00001.parquet` e `train-00005.parquet`: são 6.926 registros com sinais de tema trabalhista, que integram a base junto com TST e TRTs e passam pelas mesmas etapas, critérios e partições, sem separação.
'''
CODIGO_52 = '''REVISAO_ATIVA=json.loads((ROOT_JUR/'dados/relatorios/jurisprudencia/revisao/revisao_ativa.json').read_text(encoding='utf-8'))
diagnostico_quarentena=json.loads((ROOT_JUR/REVISAO_ATIVA['pasta']/'diagnostico_quarentena.json').read_text(encoding='utf-8'))
assert [d['arquivo'] for d in diagnostico_quarentena]==['train-00002.parquet']
assert not any(d['original_alterado'] for d in diagnostico_quarentena)
display(pd.DataFrame(diagnostico_quarentena)[['arquivo','bytes','status','tipo_erro','footer_cabe_no_arquivo','original_alterado','acao']])
'''


STF = ('Os 6.926 registros do STF com sinais de tema trabalhista integram a base atual, junto com TST e TRTs, '
       'sem separação.')
TRECHOS = [  # Orações com a cópia dentro de frases que têm outra informação a preservar.
    ('; a cópia oficial adicional de 50.000 registros STF não integra o escopo ativo.',
     '; os 6.926 registros do STF integram a base atual, sem separação.'),
    (', e a cópia adicional de 50.000 registros STF permanece separada.',
     ', e os 6.926 registros do STF integram a base atual, sem separação.'),
    ('Os 50.000 registros STF adicionais não integram estes gráficos.',
     'Os gráficos incluem os 6.926 registros do STF da base atual, junto com TST e TRTs.'),
]


def sem_mencoes(texto):
    for antes, depois in TRECHOS:
        texto = texto.replace(antes, depois)
    linhas = []
    for linha in texto.split('\n'):
        if not MENCAO.search(linha):
            linhas.append(linha)
            continue
        frases, substituida = [], False
        for f in re.split(r'(?<=[.!?])\s+', linha):
            if not MENCAO.search(f):
                frases.append(f)
                continue
            fim = re.search(r"'''[),]*\s*$", f)  # Preserva o fechamento da string Python.
            prefixo = re.match(r'^\s*(?:[-*] )?', f).group()
            if not substituida and STF not in linha:
                frases.append(prefixo + STF + (fim.group().strip() if fim else ''))
                substituida = True
            elif fim:
                if frases:
                    frases[-1] += fim.group().strip()
                else:
                    frases.append(fim.group().strip())
        if frases:
            linhas.append(' '.join(frases))
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(linhas))


def notebooks():
    for nome in ('01_auditoria_jurisprudencia.ipynb', '02_eda_jurisprudencia.ipynb', '03_limpeza_estruturacao_jurisprudencia.ipynb'):
        path = NB_DIR / nome
        original = path.read_bytes()
        nb = json.loads(original.decode('utf-8-sig'))
        alteradas = 0
        for c in nb['cells']:
            fonte = ''.join(c['source'])
            if c.get('id') == 'ori05_recuperacao_origens_texto':
                nova = SECAO_52
            elif c.get('id') == 'ori05_verificacao_origens':
                nova = CODIGO_52
            elif c.get('id') == 'ori05_config_origens':
                nova = fonte.replace("recovery=json.loads((SOURCE_DIR/'recuperacao_shard.json').read_text(encoding='utf-8'))\n", '')
            elif c['cell_type'] == 'markdown':
                nova = sem_mencoes(fonte)
            else:
                nova = fonte
            if nova != fonte:
                c['source'] = nova.splitlines(keepends=True)
                if c['cell_type'] == 'code':
                    c['outputs'], c['execution_count'] = [], None
                alteradas += 1
        if path.read_bytes() != original:
            raise RuntimeError(f'{nome} alterado durante a atualização.')
        path.write_text(json.dumps(nb, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'{nome}: {alteradas} células atualizadas')


def modulos():
    p = ROOT / 'src/jurisprudencia/presentation.py'
    t = p.read_text(encoding='utf-8')
    t = t.replace("    recovery=read(source/'recuperacao_shard.json')\n", '')
    t = t.replace("    if recovery['incorporado_base_canonica']:raise ValueError('Atualize o escopo: cópia adicional foi incorporada.')\n", '')
    t = t.replace('c=dict(root=root,origins=origins,recovery=recovery,', 'c=dict(root=root,origins=origins,')
    t = t.replace("o,r,v=c['origins'],c['recovery'],c['reviewed']", "o,v=c['origins'],c['reviewed']")
    t = re.sub(r"\*\*Cópia adicional separada:\*\*[^\n]*\n",
               "**STF na base atual:** {fmt(sum(x['registros_lidos'] for x in c['audited']['tribunais_observados'] if x['tribunal']=='STF'))} "
               "registros do STF com sinais de tema trabalhista integram a base, junto com TST e TRTs, nas mesmas etapas, "
               "critérios e partições, sem separação.\n", t)
    t = t.replace('[05 — Origens e cópia oficial]', '[05 — Origens]')
    p.write_text(sem_mencoes(t), encoding='utf-8')
    for nome in ('automation_presentation.py', 'notebook_layout.py'):
        q = ROOT / 'src/jurisprudencia' / nome
        q.write_text(sem_mencoes(q.read_text(encoding='utf-8')), encoding='utf-8')
    print('Módulos de apresentação atualizados.')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    modulos()
    notebooks()
