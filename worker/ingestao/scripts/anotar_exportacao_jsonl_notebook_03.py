"""Acrescenta ao final do notebook 03 a anotação da exportação JSONL.

Usa notebook_preservation.save_notebook: o Markdown e o código existentes são
preservados e somente a célula nova (ID autorizado) é inserida.
"""
from pathlib import Path
import copy
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from worker.ingestao.jurisprudencia.notebook_preservation import save_notebook  # noqa: E402

NB = ROOT / 'notebooks/02_jurisprudencia/03_limpeza_estruturacao_jurisprudencia.ipynb'
MANIFEST = ROOT / 'dados/processed/jurisprudencia/exportacao' / (
    sys.argv[sys.argv.index('--subpasta') + 1] if '--subpasta' in sys.argv else '') / 'manifesto_jsonl.json'
CELL_ID = 'exportacao_jsonl_jurisprudencia'


def fmt(n):
    return f'{n:,}'.replace(',', '.')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    m = json.loads(MANIFEST.read_text(encoding='utf-8'))
    s = m['saida']
    gb = f"{s['bytes'] / 1e9:.1f}".replace('.', ',')
    data = m['criado_em_utc'][:10]
    text = (
        '### 11.1. Exportação consolidada em JSONL\n'
        '\n'
        f'Em {data}, os 19 Parquets ativos da etapa de PLN leve (`{m["origem"]["pasta_dados"].replace(chr(92), "/")}`) '
        f'foram convertidos em um único arquivo JSONL, com um registro JSON por linha em UTF-8: '
        f'`{s["arquivo"].replace(chr(92), "/")}`.\n'
        '\n'
        f'- Registros: {fmt(s["registros"])}, todos relidos e validados como JSON.\n'
        f'- Tamanho: {gb} GB.\n'
        f'- SHA-256: `{s["sha256"]}`.\n'
        f'- Colunas: as {len(s["colunas"])} da versão PLN (`{"`, `".join(s["colunas"])}`).\n'
        '- Manifesto, com a contagem e o hash de cada Parquet de origem: '
        f'`{MANIFEST.relative_to(ROOT).as_posix()}`.\n'
        '- Script: `scripts/exportar_jsonl_jurisprudencia.py`.\n'
        '\n'
        'O JSONL é uma cópia derivada para compartilhamento. Os Parquets continuam sendo a base '
        'canônica do pipeline: o chunking definitivo (05) e os embeddings (06) leem os Parquets, '
        'não o JSONL. Os CPFs já estão mascarados, o que não equivale a uma anonimização integral.\n'
    )
    if '--subpasta' in sys.argv:
        text += ('\nA exportação da base completa (609.872 registros, 13,4 GB) foi preservada em '
                 '`data/processed/jurisprudencia/exportacao/jurisprudencia_pln_leve.jsonl`.\n')
    original = NB.read_bytes()
    current = json.loads(original.decode('utf-8-sig'))
    existing = next((c for c in current['cells'] if c.get('id') == CELL_ID), None)
    if existing is not None:
        # Atualização solicitada da própria célula de exportação; demais células intactas.
        existing['source'] = text.splitlines(keepends=True)
        if NB.read_bytes() != original:
            raise RuntimeError('Notebook alterado durante a atualização.')
        NB.write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Célula de exportação atualizada.')
        return
    generated = copy.deepcopy(current)
    generated['cells'].append(dict(cell_type='markdown', id=CELL_ID, metadata={},
                                   source=text.splitlines(keepends=True)))
    changed = save_notebook(NB, generated, mode='generation', allow_new_cell_ids=(CELL_ID,))
    print('Notebook atualizado.' if changed else 'Sem alteração.')


if __name__ == '__main__':
    main()
