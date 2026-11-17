"""Complementos da verificação automática (iguais aos do fluxo da base completa).

Executa, sobre a verificação automática ativa: cópia do código executado, conferência independente
das partições, amostra da estrutura JSON serializada e consulta HTTP (HEAD) da amostra de URLs
oficiais *.jus.br, como em scripts/verificar_jurisprudencia_automaticamente.py e
scripts/verificar_fontes_oficiais_jurisprudencia.py.
"""
from pathlib import Path
import runpy
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    from worker.ingestao.jurisprudencia import automatic_review
    from worker.ingestao.jurisprudencia.automated_checks import verify_partitions, serialized_json
    folder, _ = automatic_review.load(ROOT)
    shutil.copyfile(ROOT / 'src/jurisprudencia/automatic_review.py', folder / 'codigo_automatico_executado.py')
    print('Partições:', verify_partitions(ROOT), flush=True)
    print('JSON serializado:', len(serialized_json(ROOT)), 'linhas', flush=True)
    runpy.run_path(str(ROOT / 'scripts/verificar_fontes_oficiais_jurisprudencia.py'), run_name='__main__')
