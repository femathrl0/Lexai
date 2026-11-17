"""PLN leve auditável: formato e Unicode, sem reescrita jurídica."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import hashlib,html,json,re,sqlite3,unicodedata
from . import audit,dataset,privacy,structure

ENTITY=re.compile(r'&(?:#[0-9]{1,12}|#x[0-9a-fA-F]{1,12}|[A-Za-z][A-Za-z0-9]{1,63});')
BROKEN=re.compile(r'\b([^\W\d_]{2,80})[-\u00ad][ \t]*\n[ \t]*([^\W\d_]{2,80})\b',re.UNICODE)
WORDS=re.compile(r'\b(?:não|salvo)\b|\bart\.\s*\d+|§\s*\d+º?|\bsúmula\s*\d+',re.I)
TEXT_FIELDS=('ementa','inteiro_teor','texto_busca','texto_outro','ementa_alternativa')


def separate_texts(main_text,ementa,kind):
    main={'ementa':'ementa','inteiro_teor_declarado':'inteiro_teor','texto_busca_declarado':'texto_busca'}.get(kind,'texto_outro')
    fields={k:None for k in TEXT_FIELDS};fields[main]=main_text
    if main!='ementa':fields['ementa']=ementa
    elif ementa is not None and ementa!=main_text:fields['ementa_alternativa']=ementa
    return main,fields


class LegalHTML(structure.VisibleHTML):
    def __init__(self):super().__init__();self.lists=[]
    def handle_starttag(self,tag,attrs):
        if not self.hidden and tag in ('ol','ul'):
            start=dict(attrs).get('start','1')
            self.lists.append([tag,int(start) if str(start).isdigit() else 1])
        super().handle_starttag(tag,attrs)
        if tag=='li' and not self.hidden:
            if self.lists and self.lists[-1][0]=='ol':
                self.parts.append(str(self.lists[-1][1])+'. ');self.lists[-1][1]+=1
            else:self.parts.append('• ')
    def handle_endtag(self,tag):
        super().handle_endtag(tag)
        if tag in ('ol','ul') and self.lists:self.lists.pop()


def clean_light(value,pdf_verified=False,approved_words=frozenset()):
    if value is None:return None,[]
    text=value;ops=[]
    if '&' in text and ENTITY.search(text):
        for _ in range(3):
            decoded=html.unescape(text)
            if decoded==text:break
            text=decoded
        if text!=value:ops.append('entidades_html_convertidas')
    if '<' in text and structure.HTML_MARKUP.search(text):
        parser=LegalHTML();parser.feed(text);parser.close();text=''.join(parser.parts)
        ops.append('html_para_texto_com_listas')
        if parser.hidden:ops.append('html_nao_balanceado_revisar')
    normalized=unicodedata.normalize('NFC',text)
    if normalized!=text:ops.append('unicode_nfc')
    text=normalized
    normalized=text.replace('\r\n','\n').replace('\r','\n').replace('\u2028','\n').replace('\u2029','\n\n').replace('\f','\n\n')
    if normalized!=text:ops.append('quebras_de_linha_normalizadas')
    text=normalized
    if pdf_verified and approved_words and ('-\n' in text or '\u00ad\n' in text):
        def join(m):
            word=m[1]+m[2]
            return word if word.casefold() in approved_words else m[0]
        normalized=BROKEN.sub(join,text)
        if normalized!=text:ops.append('palavra_pdf_unida_com_vocabulario_aprovado')
        text=normalized
    normalized='\n'.join(re.sub(r'[^\S\n]+',' ',line).strip() for line in text.split('\n')).strip()
    normalized=re.sub(r'\n{3,}','\n\n',normalized)
    if normalized!=text:ops.append('espacos_normalizados_paragrafos_preservados')
    return normalized,ops


def fingerprint(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest() if text and text.strip() else None


def token_counts(text):
    return Counter(re.sub(r'\s+',' ',x.casefold()) for x in WORDS.findall(unicodedata.normalize('NFC',html.unescape(text or ''))))


def load(root):
    root=Path(root).resolve()
    p=json.loads((root/'dados/processed/jurisprudencia/pln_leve/ativa.json').read_text(encoding='utf-8'))
    folder=(root/p['pasta_relatorios']).resolve()
    if not folder.is_relative_to(root/'dados/relatorios/jurisprudencia/pln_leve'):raise ValueError('Relatório inválido.')
    return folder,json.loads((folder/'resumo_pln.json').read_text(encoding='utf-8'))


def validate_csv(path,expected):
    import pyarrow as pa
    import pyarrow.csv as csv
    import pyarrow.compute as pc
    rows=0;residual=0
    # Todos os campos como string preservam CNJ, datas e IDs na releitura.
    reader=csv.open_csv(path,read_options=csv.ReadOptions(block_size=64*1024**2,use_threads=False),
        parse_options=csv.ParseOptions(newlines_in_values=True),
        convert_options=csv.ConvertOptions(column_types={k:pa.string() for k in OUTPUT_FIELDS}))
    try:
        if reader.schema.names!=OUTPUT_FIELDS:raise ValueError('Esquema CSV inesperado.')
        for batch in reader:
            rows+=batch.num_rows
            for name in TEXT_FIELDS:
                residual+=pc.sum(pc.count_substring_regex(batch.column(batch.schema.get_field_index(name)),privacy.PATTERN)).as_py() or 0
    finally:reader.close()
    if rows!=expected or residual:raise ValueError('Contagem ou resíduos de CPF no CSV PLN.')
    return dict(registros_csv_relidos=rows,residuos_padrao_cpf=residual)


META=[k for k in privacy.FIELDS.values() if k not in ('texto_protegido','ementa_protegida')]
OUTPUT_FIELDS=META+list(TEXT_FIELDS)+['texto_principal_campo','privacidade_status']


def run(root):
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    import pyarrow.csv as csv
    root=Path(root).resolve();_,protected=privacy.load(root);_,base_reports=dataset.locations(root)
    base={m['arquivo_id']:m for m in json.loads((base_reports/'manifestos_arquivos.json').read_text(encoding='utf-8'))}
    signature=audit.digest((audit.hash_file(__file__)+audit.hash_file(privacy.__file__)+audit.hash_file(structure.__file__)+protected['csv_sha256']).encode())
    out=root/'dados/processed/jurisprudencia/pln_leve'/signature;folder=root/'dados/relatorios/jurisprudencia/pln_leve'/signature
    out.mkdir(parents=True,exist_ok=True);folder.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(out/'auditoria_hashes.sqlite');conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('CREATE TABLE IF NOT EXISTS docs(id TEXT PRIMARY KEY,arquivo TEXT,principal TEXT,ementa TEXT,inteiro TEXT,busca TEXT)')
    conn.execute('DELETE FROM docs');conn.commit()
    counts=Counter();ops=Counter();edges=Counter();samples=[];sample_limits=Counter();files=[]
    schema=pa.schema([(k,pa.string()) for k in OUTPUT_FIELDS])
    for m in protected['arquivos_protegidos']:
        source=root/m['arquivo'];ident=m['arquivo_id']
        if audit.hash_file(source)!=m['sha256']:raise ValueError('Derivada CPF alterada.')
        canonical=root/base[ident]['saida']
        if audit.hash_file(canonical)!=base[ident]['saida_sha256']:raise ValueError('Base canônica alterada.')
        types={r['registro_id']:r['texto_tipo_declarado'] for r in pq.read_table(canonical,columns=['registro_id','texto_tipo_declarado']).to_pylist()}
        target=out/(ident+'.parquet');partial=target.with_suffix('.partial.parquet');n=0
        with pq.ParquetWriter(partial,schema,compression='zstd') as writer:
            for batch in pq.ParquetFile(source).iter_batches(batch_size=128,use_threads=False):
                raw=batch.to_pylist();rows=[];index=[];pending=[]
                for r in raw:
                    kind=types.pop(r['registro_id'])
                    main,texts=separate_texts(r['texto_protegido'],r['ementa_protegida'],kind)
                    row={k:r[k] for k in META};row['texto_principal_campo']=main;row['privacidade_status']='cpf_mascarado_demais_dados_revisar'
                    for name,value in texts.items():
                        cleaned,operations=clean_light(value);row[name]=cleaned;ops.update(operations)
                        if value!=cleaned:counts['campos_textuais_alterados']+=1
                        if value is not None and not value.strip():counts['campos_vazios_antes']+=1
                        if cleaned is not None and not cleaned.strip():counts['campos_vazios_depois']+=1
                        if cleaned is None:counts['campos_ausentes_'+name]+=1
                        if cleaned:
                            if ('-\n' in cleaned or '\u00ad\n' in cleaned) and BROKEN.search(cleaned):counts['campos_com_palavras_partidas_revisar']+=1
                            if ENTITY.search(cleaned):counts['campos_com_entidades_residuais_revisar']+=1
                            if '\ufffd' in cleaned:counts['campos_com_substituicao_unicode_revisar']+=1
                        key=(name,'alterado' if value!=cleaned else 'inalterado')
                        if value and sample_limits[key]<20:
                            # A amostra é local, em dados processados ignorados pelo Git.
                            # O antes já vem da derivada de CPF, mas pode conter outras PII.
                            pending.append((len(rows),name,value,operations));sample_limits[key]+=1
                    rows.append(row)
                table=pa.Table.from_pylist(rows,schema=schema)
                # Decodificar entidades pode revelar CPFs antes codificados: mascarar novamente.
                for name in TEXT_FIELDS:
                    column,nmask=privacy.mask_array(table[name]);counts['substituicoes_cpf_apos_decodificacao']+=nmask
                    table=table.set_column(table.schema.get_field_index(name),name,column)
                final=table.to_pylist()
                for r,old in zip(final,raw):
                    main=r['texto_principal_campo'];text=r[main]
                    counts['registros']+=1;counts['textos_principais_vazios_depois']+=not bool(text and text.strip())
                    counts['textos_principais_vazios_antes']+=not bool(old['texto_protegido'] and old['texto_protegido'].strip())
                    hashes={k:fingerprint(r[k]) for k in TEXT_FIELDS}
                    index.append((r['registro_id'],ident,hashes[main],hashes['ementa'],hashes['inteiro_teor'],hashes['texto_busca']))
                    if text:
                        lines=text.splitlines()
                        for side,candidates in [('inicio',lines[:2]),('fim',lines[-2:])]:
                            for digest in {fingerprint(x.strip()) for x in candidates if 8<=len(x.strip())<=200}:
                                edges[(side,digest)]+=1
                for i,name,before,operations in pending:
                    after=final[i][name];before_counts=token_counts(before);after_counts=token_counts(after)
                    # Ocultar CPFs da amostra antes; não imprimir textos no notebook.
                    safe_before,_=privacy.mask_array(pa.array([before],type=pa.string()))
                    dropped=sum((before_counts-after_counts).values())
                    counts['amostras_com_marcadores_juridicos_reduzidos_revisar']+=bool(dropped)
                    samples.append(dict(registro_id=final[i]['registro_id'],campo=name,antes=safe_before[0].as_py(),depois=after,
                        operacoes=';'.join(operations),marcadores_juridicos_reduzidos=dropped,verificacao_automatica='sem_reducao_dos_marcadores' if not dropped else 'alerta_marcadores'))
                writer.write_table(table);conn.executemany('INSERT INTO docs VALUES (?,?,?,?,?,?)',index);n+=len(rows)
        if types or n!=m['totais']['registros']:raise ValueError('Alinhamento ou quantidade divergente.')
        conn.commit();privacy.replace_completed(partial,target)
        files.append(dict(arquivo_id=ident,arquivo=str(target.relative_to(root)),registros=n,sha256=audit.hash_file(target),origem_sha256=m['sha256']))
        print('PLN leve:',ident,n,'registros',flush=True)
    if counts['registros']!=protected['registros']:raise ValueError('Total PLN divergente.')
    duplicates=[]
    for col,name in [('principal','texto_principal'),('ementa','ementa'),('inteiro','inteiro_teor'),('busca','texto_busca')]:
        groups,excess=conn.execute(f'SELECT COUNT(*),COALESCE(SUM(n-1),0) FROM (SELECT COUNT(*) n FROM docs WHERE {col} IS NOT NULL GROUP BY {col} HAVING COUNT(*)>1)').fetchone()
        duplicates.append(dict(campo=name,grupos_exatos_repetidos=groups,ocorrencias_excedentes=excess))
    conn.close()
    audit.write_csv(folder/'duplicatas_exatas.csv',duplicates)
    edge_rows=[dict(posicao=side,linha_sha256=sha,documentos=n,status='candidato_repetido_nao_removido') for (side,sha),n in edges.most_common() if n>=10]
    audit.write_csv(folder/'cabecalhos_rodapes_candidatos.csv',edge_rows,['posicao','linha_sha256','documentos','status'])
    pq.write_table(pa.Table.from_pylist(samples),out/'amostra_antes_depois.parquet',compression='zstd')
    target_csv=out/'jurisprudencia_pln_leve.csv';partial_csv=target_csv.with_suffix('.csv.partial')
    print('Consolidando CSV PLN...',flush=True)
    with csv.CSVWriter(partial_csv,schema) as writer:
        for m in files:
            for batch in pq.ParquetFile(root/m['arquivo']).iter_batches(batch_size=128,use_threads=False):writer.write_batch(batch)
    print('Validando CSV PLN integralmente...',flush=True)
    validation=validate_csv(partial_csv,counts['registros']);privacy.replace_completed(partial_csv,target_csv)
    result=dict(executado_em_utc=datetime.now(timezone.utc).isoformat(),codigo_sha256=audit.hash_file(__file__),
        base_cpf_csv_sha256=protected['csv_sha256'],registros=counts['registros'],indicadores=dict(counts),operacoes=dict(ops),
        duplicatas_exatas=duplicates,linhas_limite_repetidas_candidatas=len(edge_rows),amostras=len(samples),
        amostra_automatica_status='verificada_por_marcadores',arquivos=files,csv=str(target_csv.relative_to(root)),csv_sha256=audit.hash_file(target_csv),
        validacao_csv=validation,amostra_local=str((out/'amostra_antes_depois.parquet').relative_to(root)),
        colunas=OUTPUT_FIELDS,originais_preservados=True,exclusoes_automaticas=0,
        politica_pdf='Não há origem PDF confirmada para aplicar junção automática. Padrões de palavras partidas são sinalizados; correção depende de confirmação de PDF e vocabulário aprovado.',
        politica_bordas='Primeiras/últimas duas linhas, 8–200 caracteres, recorrentes em ao menos 10 documentos: candidatos por fingerprint, sem remoção. Repetição pode ser conteúdo jurídico legítimo.',
        limites='PLN leve de formato; não classifica mérito jurídico, não remove stopwords/acentos/pontuação e não realiza anonimização completa. Amostra comparada por marcadores; relatórios públicos não exibem textos ou PII.')
    audit.write_json(folder/'resumo_pln.json',result)
    audit.write_json(root/'dados/processed/jurisprudencia/pln_leve/ativa.json',dict(pasta_dados=str(out.relative_to(root)),pasta_relatorios=str(folder.relative_to(root))))
    print('PLN e CSV validados:',target_csv,flush=True)
    return folder,result
