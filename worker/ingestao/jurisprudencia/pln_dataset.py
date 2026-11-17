"""Leitura da derivada de PLN sem misturar a amostra antes/depois ao corpus."""
from pathlib import Path
from .light_nlp import load,OUTPUT_FIELDS


def open_dataset(root):
    import pyarrow.dataset as ds
    root=Path(root).resolve();_,manifest=load(root)
    data=(root/manifest['csv']).resolve().parent
    if not data.is_relative_to(root/'dados/processed/jurisprudencia/pln_leve'):raise ValueError('Pasta de dados inválida.')
    files=[]
    for m in manifest['arquivos']:
        path=(root/m['arquivo']).resolve()
        if path.parent!=data or path.name=='amostra_antes_depois.parquet':raise ValueError('Shard não permitido.')
        files.append(str(path))
    if len(files)!=len(set(files)):raise ValueError('Shard repetido no manifesto.')
    corpus=ds.dataset(files,format='parquet')
    if corpus.schema.names!=OUTPUT_FIELDS:raise ValueError('Esquema inesperado.')
    return corpus
