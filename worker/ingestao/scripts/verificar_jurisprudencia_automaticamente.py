from pathlib import Path
import sys
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
    from worker.ingestao.jurisprudencia.automatic_review import run
    from worker.ingestao.jurisprudencia.automated_checks import verify_partitions,serialized_json
    import shutil
    folder,result=run(root)
    shutil.copyfile(root/'src/jurisprudencia/automatic_review.py',folder/'codigo_automatico_executado.py')
    verify_partitions(root);serialized_json(root)
    print('Partições e estrutura JSON verificadas automaticamente.')
