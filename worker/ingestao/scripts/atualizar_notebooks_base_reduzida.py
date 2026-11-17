"""Atualiza os notebooks 01–03 de jurisprudência para a base reduzida (opção D).

Mantém todas as seções, títulos e textos atuais; altera somente:
  - valores fixos da base completa (total de registros, tamanho do CSV) no código e no Markdown;
  - a pasta de originais do notebook 01 (base reduzida);
  - um parágrafo de contexto no primeiro bloco Markdown de cada notebook.
Células de código alteradas têm as saídas limpas; os executores do projeto geram as novas saídas.
Antes de gravar, rode scripts/preservar_notebooks_jurisprudencia.py (cópias integrais com SHA-256).
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
NB_DIR = ROOT / 'notebooks/02_jurisprudencia'
MARCA = '**Base reduzida (opção D).**'


def fmt(n):
    return f'{n:,}'.replace(',', '.')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    from worker.ingestao.jurisprudencia import report, privacy
    _, auditoria, _ = report.load(ROOT)
    total = auditoria['registros_lidos']
    manifesto = json.loads((ROOT / 'dados/relatorios/jurisprudencia/base_reduzida/manifesto_base_reduzida.json').read_text(encoding='utf-8'))
    if manifesto['registros'] != total:
        raise ValueError('A auditoria ativa não corresponde à base reduzida.')
    manifesto_ids = json.loads((ROOT / 'dados/relatorios/jurisprudencia/base_reduzida/ids_obrigatorios.json').read_text(encoding='utf-8'))['registro_ids']
    _, protecao = privacy.load(ROOT)
    gb = protecao['csv_bytes'] / 1e9
    tamanho_csv = f'aproximadamente {gb:.1f} GB'.replace('.', ',')
    nota = (
        f'{MARCA} Estes notebooks usam a base reduzida em `data/raw/jurisprudencia/base_reduzida/`: os mesmos '
        '20 arquivos de entrada, nos formatos originais, somente com os registros selecionados. A seleção parte '
        'do recorte consolidado da base completa, mantém um documento por processo e limita o TST a 100.000 '
        'documentos por amostragem estratificada (ano × órgão julgador, seed fixa). TRT-10, TRT-13, TRT-17, o STF '
        f'trabalhista e os {len(manifesto_ids)} documentos usados nos experimentos de chunking (notebook 04) e na avaliação '
        'foram mantidos obrigatoriamente. O JSON TST, sem candidatos ao RAG, '
        f'permanece no inventário com um documento por processo. São **{fmt(total)} registros** '
        '(a base completa tinha 609.872).\n\n'
        'Critérios, contagens e o mapa de `registro_id` antigo → novo estão em '
        '`reports/jurisprudencia/base_reduzida/manifesto_base_reduzida.json`. A origem de cada arquivo reduzido é '
        'rastreada pelo hash do arquivo completo de onde foi recortado. Os resultados da base completa continuam '
        'em disco, e os ponteiros anteriores estão em `reports/jurisprudencia/base_completa_ponteiros/`.\n')
    anteriores = [609872, 179813]  # Totais de versões anteriores (base completa e primeira base reduzida).
    trocas_codigo = [(f'=={n}', f'=={total}') for n in anteriores if n != total] + [
        ("PASTA_ORIGINAIS = Path.home()/'Downloads'", "PASTA_ORIGINAIS = ROOT_JUR/'dados/raw/jurisprudencia/base_reduzida'")]
    trocas_codigo += [(f'(aproximadamente {x} GB)', f'({tamanho_csv})') for x in ('13', '4,1')]
    trocas_md = [(f'{fmt(n)} registros', f'{fmt(total)} registros') for n in anteriores if n != total]
    primeiros = {'01_auditoria_jurisprudencia.ipynb': 'titulo_auditoria_jurisprudencia',
                 '02_eda_jurisprudencia.ipynb': 'intro_eda',
                 '03_limpeza_estruturacao_jurisprudencia.ipynb': 'intro_estrutura'}
    for nome, intro in primeiros.items():
        path = NB_DIR / nome
        original = path.read_bytes()
        nb = json.loads(original.decode('utf-8-sig'))
        if not any(c.get('id') == intro for c in nb['cells']):
            intro = nb['cells'][0]['id']
        alteradas = 0
        for c in nb['cells']:
            fonte = ''.join(c['source'])
            nova = fonte
            if c.get('id') == 'exportacao_jsonl_jurisprudencia':
                continue  # Atualizada pela exportação JSONL da base reduzida.
            for a, b in (trocas_codigo if c['cell_type'] == 'code' else trocas_md):
                nova = nova.replace(a, b)
            if c.get('id') == intro:
                if MARCA in nova:  # Substitui a nota anterior pela atual, mantendo o restante da célula.
                    nova = nova[:nova.index(MARCA)].rstrip('\n')
                nova = nova.rstrip('\n') + '\n\n' + nota
            if nova != fonte:
                c['source'] = nova.splitlines(keepends=True)
                if c['cell_type'] == 'code':
                    c['outputs'], c['execution_count'] = [], None
                alteradas += 1
        if path.read_bytes() != original:
            raise RuntimeError(f'{nome} foi alterado durante a atualização.')
        path.write_text(json.dumps(nb, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'{nome}: {alteradas} células atualizadas')


if __name__ == '__main__':
    main()
