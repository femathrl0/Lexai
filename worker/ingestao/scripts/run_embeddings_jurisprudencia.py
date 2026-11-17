from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from worker.ingestao.jurisprudencia.embeddings_definitivos import run
from worker.evidencia.indices.jurisprudencia_pgvector import import_verified
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--device',choices=['cpu','cuda'],default='cpu');p.add_argument('--max-lotes',type=int);p.add_argument('--somente-embeddings',action='store_true')
    args=p.parse_args();state,progress=run(ROOT,device=args.device,max_lotes=args.max_lotes)
    print(json.dumps(progress,ensure_ascii=False))
    if progress['chunks_restantes']==0 and not args.somente_embeddings:print(import_verified(state))
