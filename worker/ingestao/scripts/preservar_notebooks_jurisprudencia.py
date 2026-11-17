"""Preserva os cinco notebooks existentes, sem executar nem regravar seus conteúdos."""
from pathlib import Path
import sys
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
    from worker.ingestao.jurisprudencia.notebook_preservation import snapshot
    target,manifest=snapshot(root)
    print('Cópias preservadas:',target)
    for e in manifest['arquivos']:print(e['arquivo'],e['sha256'])
