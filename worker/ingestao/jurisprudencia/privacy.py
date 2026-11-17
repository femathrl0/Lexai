"""Derivada textual com CPFs mascarados; não equivale a anonimização integral."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import json
import re
import time

from . import audit,dataset

TOKEN='[CPF_REMOVIDO]'
# Limites numéricos preservam o CNJ de 20 dígitos. Mascarar também sequências
# sintaticamente compatíveis com DV inválido é uma escolha conservadora.
PATTERN=r'(^|[^0-9])(?:[0-9]{3}[.\s\x{00a0}]?[0-9]{3}[.\s\x{00a0}]?[0-9]{3}[-\s\x{00a0}\x{2010}-\x{2015}]?[0-9]{2})([^0-9]|$)'
PY_PATTERN=re.compile(r'(?<![0-9])[0-9]{3}[.\s\u00a0]?[0-9]{3}[.\s\u00a0]?[0-9]{3}[-\s\u00a0\u2010-\u2015]?[0-9]{2}(?![0-9])')
FIELDS={'registro_id':'registro_id','arquivo_id':'arquivo_id','tribunal':'tribunal',
    'processo_cnj':'processo_cnj','orgao_julgador':'orgao_julgador','relator':'relator',
    'classe_origem':'classe_origem','tipo_decisao_origem':'tipo_decisao_origem',
    'data_julgamento':'data_julgamento','data_publicacao':'data_publicacao',
    'data_assinatura':'data_assinatura','texto_limpo':'texto_protegido','ementa_limpa':'ementa_protegida'}
FORBIDDEN={'texto_original','texto_limpo','ementa_original','ementa_limpa','processo_original','partes','data_json','metadata_extra_json','url_origem'}
TECHNICAL_IDS={'registro_id':r'^[a-f0-9]{64}$','arquivo_id':r'^f[0-9]{2,}$'}


def replace_completed(source,target):
    """Tolera bloqueios breves de sincronização no Windows após fechar leitores."""
    for attempt in range(20):
        try:Path(source).replace(target);return
        except PermissionError:
            if attempt==19:raise
            time.sleep(1)


def mask_array(values):
    import pyarrow as pa
    import pyarrow.compute as pc
    if pa.types.is_null(values.type):values=pc.cast(values,pa.string())
    before=pc.sum(pc.count_substring(values,TOKEN)).as_py() or 0
    while pc.any(pc.match_substring_regex(values,PATTERN)).as_py():
        values=pc.replace_substring_regex(values,PATTERN,r'\1'+TOKEN+r'\2')
    after=pc.sum(pc.count_substring(values,TOKEN)).as_py() or 0
    return values,after-before


def protect_batch(batch):
    import pyarrow as pa
    import pyarrow.compute as pc
    arrays=[];counts={};changed=pa.array([False]*batch.num_rows)
    for source,target in FIELDS.items():
        original=batch.column(batch.schema.get_field_index(source))
        if source in TECHNICAL_IDS:
            if not pc.all(pc.fill_null(pc.match_substring_regex(original,TECHNICAL_IDS[source]),False)).as_py():
                raise ValueError('Identificador técnico inválido; não exportado.')
            masked,n=original,0
        else:masked,n=mask_array(original)
        changed=pc.or_(changed,pc.fill_null(pc.not_equal(original,masked),False))
        arrays.append(masked);counts[target]=n
    arrays.extend([changed,pa.array(['cpf_mascarado_demais_dados_revisar']*batch.num_rows)])
    return pa.RecordBatch.from_arrays(arrays,list(FIELDS.values())+['cpf_mascarado','privacidade_status']),counts


def validate_csv(path,expected):
    """Relê todo o CSV e procura resíduos sem imprimir qualquer dado pessoal."""
    import pyarrow as pa
    import pyarrow.csv as acsv
    import pyarrow.compute as pc
    types={k:pa.string() for k in FIELDS.values()}
    types.update(cpf_mascarado=pa.bool_(),privacidade_status=pa.string())
    count=0;residual=0
    reader=acsv.open_csv(path,read_options=acsv.ReadOptions(block_size=64*1024**2,use_threads=False),
        parse_options=acsv.ParseOptions(newlines_in_values=True),convert_options=acsv.ConvertOptions(column_types=types,strings_can_be_null=True))
    try:
        if set(reader.schema.names)&FORBIDDEN:raise ValueError('Coluna não permitida na exportação.')
        for batch in reader:
            count+=batch.num_rows
            for field in batch.schema:
                if pa.types.is_string(field.type):
                    if field.name in TECHNICAL_IDS:
                        if not pc.all(pc.fill_null(pc.match_substring_regex(batch.column(batch.schema.get_field_index(field.name)),TECHNICAL_IDS[field.name]),False)).as_py():
                            raise ValueError('Identificador técnico fora do contrato.')
                        continue
                    residual+=pc.sum(pc.count_substring_regex(batch.column(batch.schema.get_field_index(field.name)),PATTERN)).as_py() or 0
    finally:reader.close()
    if count!=expected or residual:raise ValueError('Validação do CSV falhou: contagem ou padrão residual.')
    return dict(registros_csv_relidos=count,sequencias_compativeis_residuais=residual,
        colunas_originais_expostas=False,metodo='Releitura integral do CSV UTF-8 com campos multilinha. Textos e metadados de conteúdo conferidos contra o padrão; IDs técnicos validados separadamente como hash hexadecimal de 64 caracteres e código fNN, sem alterar a linhagem.')


def run(root):
    import pyarrow as pa
    import pyarrow.parquet as pq
    import pyarrow.compute as pc
    import pyarrow.csv as acsv
    root=Path(root).resolve();base,reports=dataset.locations(root)
    manifests=json.loads((reports/'manifestos_arquivos.json').read_text(encoding='utf-8'))
    expected=json.loads((reports/'resumo_estruturacao.json').read_text(encoding='utf-8'))['registros']
    protocol=audit.digest((audit.hash_file(__file__)+audit.hash_file(reports/'manifestos_arquivos.json')).encode())
    out=root/'dados/processed/jurisprudencia/protecao_cpf'/protocol
    report_dir=root/'dados/relatorios/jurisprudencia/protecao_cpf'/protocol
    out.mkdir(parents=True,exist_ok=True);report_dir.mkdir(parents=True,exist_ok=True)
    outputs=[];totals=Counter();by_field=Counter()
    for manifest in manifests:
        source=root/manifest['saida'];ident=manifest['arquivo_id']
        if audit.hash_file(source)!=manifest['saida_sha256']:raise ValueError('Base canônica alterada.')
        target=out/(ident+'.parquet');checkpoint=report_dir/(ident+'.json')
        if target.exists() and checkpoint.exists():
            old=json.loads(checkpoint.read_text(encoding='utf-8'))
            if old['sha256']==audit.hash_file(target) and old['origem_sha256']==manifest['saida_sha256']:
                outputs.append(old);totals.update(old['totais']);by_field.update(old['por_campo']);print('Proteção preservada:',ident,flush=True);continue
        partial=target.with_suffix('.partial.parquet');writer=None;metrics=Counter();field_counts=Counter()
        try:
            for batch in pq.ParquetFile(source).iter_batches(batch_size=128,columns=list(FIELDS),use_threads=False):
                protected,counts=protect_batch(batch)
                if writer is None:writer=pq.ParquetWriter(partial,protected.schema,compression='zstd')
                writer.write_batch(protected)
                metrics['registros']+=batch.num_rows
                metrics['registros_com_mascaramento']+=pc.sum(pc.cast(protected.column(protected.schema.get_field_index('cpf_mascarado')),pa.int64())).as_py() or 0
                metrics['sequencias_compativeis_mascaradas']+=sum(counts.values());field_counts.update(counts)
        finally:
            if writer is not None:writer.close()
        if metrics['registros']!=manifest['registros']:raise ValueError('Contagem protegida diverge da origem.')
        replace_completed(partial,target)
        old=dict(arquivo_id=ident,arquivo=str(target.relative_to(root)),sha256=audit.hash_file(target),
            origem_sha256=manifest['saida_sha256'],totais=dict(metrics),por_campo=dict(field_counts))
        audit.write_json(checkpoint,old);outputs.append(old);totals.update(metrics);by_field.update(field_counts)
        print('Protegido:',ident,metrics['registros'],'registros;',metrics['registros_com_mascaramento'],'alterados',flush=True)
    if totals['registros']!=expected:raise ValueError('Total protegido divergente.')
    csv_path=out/'jurisprudencia_cpf_protegido.csv';partial_csv=csv_path.with_suffix('.csv.partial')
    writer=None;rows_written=0
    try:
        for m in outputs:
            for batch in pq.ParquetFile(root/m['arquivo']).iter_batches(batch_size=128,use_threads=False):
                if writer is None:writer=acsv.CSVWriter(partial_csv,batch.schema,write_options=acsv.WriteOptions(include_header=True))
                writer.write_batch(batch);rows_written+=batch.num_rows
            print('CSV:',m['arquivo_id'],rows_written,'registros',flush=True)
    finally:
        if writer is not None:writer.close()
    validation=validate_csv(partial_csv,expected)
    replace_completed(partial_csv,csv_path)
    result=dict(protocolo='cpf-mascaramento-v1',executado_em_utc=datetime.now(timezone.utc).isoformat(),
        codigo_sha256=audit.hash_file(__file__),manifesto_base_sha256=audit.hash_file(reports/'manifestos_arquivos.json'),
        **dict(totals),mascaramentos_por_campo=dict(by_field),validacao=validation,
        csv=str(csv_path.relative_to(root)),csv_sha256=audit.hash_file(csv_path),csv_bytes=csv_path.stat().st_size,
        arquivos_protegidos=outputs,colunas=list(FIELDS.values())+['cpf_mascarado','privacidade_status'],
        marcador=TOKEN,padrao_re2=PATTERN,originais_preservados=True,
        anonimizado_integralmente=False,indexacao_realizada=False,
        limites='Mascaramento de sequências sintaticamente compatíveis com CPF, formatadas ou de 11 dígitos, inclusive com DV inválido. Pode mascarar outros números de 11 dígitos, como telefones. Não cobre formas por extenso, todos os tipos de ofuscação, nomes, endereços ou outros dados pessoais. Não é autorização de publicação ou indexação.',
        offsets='Chunking deve usar texto_protegido e seus próprios offsets. Offsets do texto original/limpo não são reutilizáveis após substituições.')
    audit.write_json(report_dir/'resumo_protecao.json',result)
    audit.write_json(root/'dados/processed/jurisprudencia/protecao_cpf/ativa.json',dict(pasta_dados=str(out.relative_to(root)),pasta_relatorios=str(report_dir.relative_to(root))))
    print('Proteção e exportação concluídas:',csv_path,flush=True)
    return report_dir,result


def load(root):
    root=Path(root).resolve()
    pointer=json.loads((root/'dados/processed/jurisprudencia/protecao_cpf/ativa.json').read_text(encoding='utf-8'))
    report_dir=(root/pointer['pasta_relatorios']).resolve()
    if not report_dir.is_relative_to(root/'dados/relatorios/jurisprudencia/protecao_cpf'):raise ValueError('Relatório inválido.')
    return report_dir,json.loads((report_dir/'resumo_protecao.json').read_text(encoding='utf-8'))
