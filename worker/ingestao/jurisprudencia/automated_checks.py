"""Checagens independentes dos índices e da estrutura JSON serializada."""
from pathlib import Path
import json
import sqlite3
from . import audit,light_nlp,automatic_review


def verify_partitions(root):
    import pyarrow.parquet as pq
    root=Path(root).resolve();folder,result=automatic_review.load(root);_,pln=light_nlp.load(root)
    assignments={};seen={};count=0;leaks=0
    for batch in pq.ParquetFile(root/result['indice']).iter_batches(columns=['registro_id','grupo_processo','split_proposto']):
        for r in batch.to_pylist():
            if r['registro_id'] in assignments:raise ValueError('ID duplicado.')
            assignments[r['registro_id']]=r['split_proposto']
            if r['grupo_processo'] and seen.setdefault(('processo',r['grupo_processo']),r['split_proposto'])!=r['split_proposto']:leaks+=1
    connection=sqlite3.connect('file:'+str((root/pln['csv']).parent/'auditoria_hashes.sqlite').replace('\\','/')+'?mode=ro',uri=True)
    try:
        for ident,digest in connection.execute('SELECT id,principal FROM docs'):
            split=assignments.pop(ident);count+=1
            if digest and seen.setdefault(('texto',digest),split)!=split:leaks+=1
    finally:connection.close()
    if leaks or assignments or count!=result['registros']:raise ValueError('Cobertura ou partição inconsistente.')
    report=dict(registros_verificados=count,vinculos_texto_processo_atravessando_splits=leaks,
        indice_sha256=audit.hash_file(root/result['indice']),metodo='Conferência independente de cada chave de texto pós-PLN e de processo.',
        limite='Não cobre vínculos semânticos ou identidade processual não reconhecida.')
    audit.write_json(folder/'verificacao_independente_pos_pln.json',report)
    return report


def serialized_json(root,max_rows=32):
    import pyarrow.parquet as pq
    from .report import load
    root=Path(root).resolve();folder,_=automatic_review.load(root);base,_,profiles=load(root)
    inventory=json.loads((base/'inventario.json').read_text(encoding='utf-8'))
    complete={p['arquivo_id'] for p in profiles if p['status_leitura']=='concluido'}
    rows=[]
    for e in inventory:
        if e['arquivo_id'] not in complete or e['formato']!='parquet':continue
        source=Path(e['caminho_original']);file=pq.ParquetFile(source)
        fields=[f for f in ['data_json','metadata_extra_json'] if f in file.schema_arrow.names]
        for field in fields:
            checked=parsed=bad=empty=objects=arrays=0
            for batch in file.iter_batches(batch_size=4,columns=[field],use_threads=False):
                for value in batch.column(0).to_pylist():
                    if checked>=max_rows:break
                    checked+=1
                    if value is None or value=='':empty+=1;continue
                    try:
                        v=json.loads(value);parsed+=1;objects+=isinstance(v,dict);arrays+=isinstance(v,list)
                    except (ValueError,TypeError):bad+=1
                if checked>=max_rows:break
            rows.append(dict(arquivo_id=e['arquivo_id'],campo=field,registros_amostrados=checked,
                json_validos=parsed,json_invalidos=bad,vazios=empty,objetos=objects,listas=arrays,
                cobertura='primeiros_32_registros_por_campo_e_arquivo',valores_expostos=False))
    audit.write_csv(folder/'estrutura_json_serializado_amostra.csv',rows)
    return rows
