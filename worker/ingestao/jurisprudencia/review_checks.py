"""Conferência independente dos vínculos conhecidos após salvar a partição."""
from pathlib import Path
import json
from . import audit,dataset


def verify(root):
    import pyarrow.parquet as pq
    root=Path(root).resolve()
    active=json.loads((root/'dados/relatorios/jurisprudencia/revisao/revisao_ativa.json').read_text(encoding='utf-8'))
    reports=root/active['pasta'];data=root/active['pasta_dados']
    result=json.loads((reports/'resumo_revisao.json').read_text(encoding='utf-8'))
    assignment={}
    for batch in pq.ParquetFile(data/'triagem_particoes.parquet').iter_batches(columns=['registro_id','split_proposto']):
        for row in batch.to_pylist():
            if row['registro_id'] in assignment:raise ValueError('ID repetido na partição.')
            assignment[row['registro_id']]=row['split_proposto']
    seen={};count=0;leaks=set()
    columns=['registro_id','tribunal','processo_cnj','processo_original','texto_limpo_sha256','registro_original_sha256']
    for batch in dataset.open_dataset(root).scanner(columns=columns,batch_size=8192,use_threads=False).to_batches():
        for r in batch.to_pylist():
            split=assignment.pop(r['registro_id']);count+=1
            process,_=dataset.process_group_key(r['tribunal'],r['processo_cnj'],r['processo_original'])
            for kind,key in [('processo',process),('texto',r['texto_limpo_sha256']),('registro',r['registro_original_sha256'])]:
                if key and seen.setdefault((kind,key),split)!=split:leaks.add((kind,key))
    if leaks or assignment or count!=result['registros']:raise ValueError('Vazamento ou cobertura incompleta na partição salva.')
    check=dict(registros_verificados=count,vinculos_atravessando_splits=len(leaks),ids_sobrando=len(assignment),
        limite='Conferência dos vínculos sintáticos e hashes conhecidos; não prova ausência de relação semântica não detectada.',
        codigo_verificador_sha256=audit.hash_file(__file__),indice_sha256=audit.hash_file(data/'triagem_particoes.parquet'))
    audit.write_json(reports/'verificacao_independente.json',check)
    return check
