from pathlib import Path
import argparse,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from worker.ingestao.jurisprudencia.chunking_definitivo import run,finalize
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--max-lotes',type=int)
    a=p.parse_args();state,result=run(ROOT,max_lotes=a.max_lotes)
    if result['documentos_restantes']==0:result=finalize(state)
    print(result)
