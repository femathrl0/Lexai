from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from worker.ingestao.jurisprudencia.embeddings_backbone import preflight
if __name__=='__main__':print(json.dumps(preflight(ROOT),ensure_ascii=False,indent=2))
