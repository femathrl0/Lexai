"""Normalização conservadora em lotes, com originais preservados e linhagem."""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import re
import sqlite3
import unicodedata
from html.parser import HTMLParser
from collections import Counter
from datetime import datetime, timezone

from . import audit
from .report import load

PROTOCOL='jurisprudencia-estrutura-v1'
BLOCKS={'p','div','br','hr','li','tr','h1','h2','h3','h4','h5','h6','pre','section','article','blockquote'}
KNOWN=BLOCKS|{'html','body','head','span','table','tbody','thead','tfoot','td','th','ul','ol','strong','em','b','i','u','a','script','style','img','meta','link','title'}
HTML_MARKUP=re.compile(r'</?(?:'+ '|'.join(sorted(KNOWN)) +r')\b[^>]*>', re.I)
STR_FIELDS=['registro_id','arquivo_id','arquivo_origem','arquivo_sha256','registro_original_sha256',
    'documento_id_origem','tribunal','tribunal_original','tribunal_metodo','processo_original','processo_cnj',
    'orgao_julgador','relator','classe_origem','tipo_decisao_origem','ramo_direito_origem',
    'data_julgamento','data_publicacao','data_assinatura','data_referencia_temporal','data_referencia_tipo',
    'data_julgamento_campo','data_publicacao_campo','texto_campo_origem','texto_tipo_declarado',
    'texto_original','texto_limpo','ementa_original','ementa_limpa','texto_original_sha256','texto_limpo_sha256',
    'grupo_documental_sha256','grupo_processo_sha256','url_origem','captura_origem','coletor_origem',
    'base_origem','pertinencia_tematica_status','privacidade_status']


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]; self.hidden=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):
            self.hidden.append(tag);return
        if self.hidden:return
        if tag in BLOCKS:self.parts.append('\n')
        elif tag in ('td','th'):self.parts.append(' ')
        elif tag=='img':
            alt=dict(attrs).get('alt')
            if alt:self.parts.append(' '+alt+' ')
        elif tag not in KNOWN:self.parts.append(self.get_starttag_text())
    def handle_endtag(self,tag):
        if self.hidden:
            if tag==self.hidden[-1]:self.hidden.pop()
            return
        if tag in BLOCKS:self.parts.append('\n')
        elif tag in ('td','th'):self.parts.append(' ')
        elif tag not in KNOWN:self.parts.append('</'+tag+'>')
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag in ('script','style'):self.handle_endtag(tag)
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)


def clean_text(value):
    if not isinstance(value,str):return '',[]
    text=value;ops=[]
    if text.startswith('\ufeff'):text=text.lstrip('\ufeff');ops.append('bom_inicial_removido')
    if HTML_MARKUP.search(text):
        parser=VisibleHTML();parser.feed(text);parser.close();text=''.join(parser.parts);ops.append('html_para_texto_visivel')
        if parser.hidden:ops.append('html_nao_balanceado_revisar')
    normalized=unicodedata.normalize('NFC',text)
    if normalized!=text:ops.append('unicode_nfc')
    text=normalized.replace('\r\n','\n').replace('\r','\n').replace('\u2028','\n').replace('\u2029','\n\n')
    if text!=normalized:ops.append('quebras_de_linha_normalizadas')
    normalized=re.sub(r'[\x00-\x08\x0b\x0e-\x1f]','',text).replace('\f','\n\n')
    if normalized!=text:ops.append('controles_de_apresentacao_removidos')
    text=normalized
    normalized='\n'.join(re.sub(r'[ \t\u00a0]+',' ',line).strip() for line in text.split('\n')).strip()
    normalized=re.sub(r'\n{3,}','\n\n',normalized)
    if normalized!=text:ops.append('espacos_e_linhas_vazias_normalizados')
    return normalized,ops


def scalar(flat, fields, numeric=False):
    for name in fields:
        value=flat.get(name)
        if isinstance(value,str) and value.strip():return value.strip(),name
        if numeric and isinstance(value,(int,float)) and not isinstance(value,bool):return str(value),name
    return None,None


def cnj(value):
    if not value:return None
    found=audit.CNJ.search(value)
    if found:return re.sub(r'\D','',found[0])
    return value if re.fullmatch(r'\d{20}',value) else None


def date_field(flat, fields):
    name,value=audit.first(flat,fields)
    parsed=audit.parse_date(value)
    return parsed.isoformat() if parsed else None,name or None,value


def normalize_record(record,entry,line):
    flat=audit.flatten(record);flags=[]
    tribunal,method,conflict=audit.identify_court(flat,entry['arquivo'])
    if not method.startswith('campo_estruturado:') or tribunal=='não identificado':
        tribunal=None;flags.append('tribunal_sem_identificacao_estruturada')
    if conflict:flags.append('conflito_tribunal')
    tribunal_raw,_=scalar(flat,['tribunal','court','registro.orgao.sigla','registro.orgao.nome'])
    field,raw=audit.first(flat,audit.TEXT_FIELDS)
    original=raw if isinstance(raw,str) else ''
    if raw is not None and not isinstance(raw,str):flags.append('texto_principal_tipo_inesperado')
    cleaned,operations=clean_text(original)
    _,ementa_raw=audit.first(flat,['ementa','registro.ementa','registro.ementaNaoAnalisada','registro.ementaHtml'])
    ementa=ementa_raw if isinstance(ementa_raw,str) else None
    clean_ementa,ementa_operations=clean_text(ementa)
    if not cleaned:flags.append('sem_texto_utilizavel')
    if '\ufffd' in cleaned:flags.append('unicode_substituicao_revisar')
    if original.lstrip().startswith('{\\rtf'):flags.append('rtf_nao_extraido')
    if 'html_nao_balanceado_revisar' in operations:flags.append('html_nao_balanceado_revisar')
    if any(x in cleaned for x in ('Ã£','Ã§','â€','Â§')):flags.append('possivel_mojibake_nao_corrigido')
    _,process_raw=audit.first(flat,audit.PROCESS_FIELDS)
    process=process_raw if isinstance(process_raw,str) else str(process_raw) if isinstance(process_raw,(int,float)) and not isinstance(process_raw,bool) else None
    doc,_=scalar(flat,audit.DOC_FIELDS,numeric=True)
    judgment,jfield,jraw=date_field(flat,['data_julgamento','registro.dtaJulgamento'])
    publication,pfield,praw=date_field(flat,audit.PUBLICATION_FIELDS)
    signature,_,sraw=date_field(flat,['data_assinatura'])
    reference,ref_field=judgment or signature,'julgamento' if judgment else 'assinatura' if signature else None
    for name,value,parsed in [('julgamento',jraw,judgment),('publicacao',praw,publication),('assinatura',sraw,signature)]:
        if not audit.empty(value) and parsed is None:flags.append('data_'+name+'_nao_interpretavel')
        if parsed and parsed>datetime.now(timezone.utc).date().isoformat():flags.append('data_'+name+'_futura')
    if judgment and publication and publication<judgment:flags.append('publicacao_anterior_julgamento')
    if not doc:flags.append('sem_id_documental_na_origem')
    if not process:flags.append('sem_processo_na_origem')
    has_cpf=any(audit.cpf_valid(m[0]) for m in audit.cpf_candidates(original))
    has_email='@' in original and bool(audit.EMAIL.search(original))
    if has_cpf:flags.append('cpf_candidato_checksum_valido')
    if has_email:flags.append('email_candidato')
    party_fields=any(not audit.empty(v) for k,v in flat.items() if k.split('.')[-1].lower() in ('partes','cpf','cnpj','endereco','telefone','email','advogados'))
    if party_fields:flags.append('campos_de_partes_ou_contato_na_origem')
    url,_=scalar(flat,['url','source','fonte'])
    if url and not re.match(r'^https?://[^\s/]+',url,re.I):url=None
    values={'orgao_julgador':['orgao_julgador','orgao_julgador_colegiado','registro.orgaoJudicante.descricao'],
        'relator':['relator','registro.nomRelator'],'classe_origem':['classe','registro.classe'],
        'tipo_decisao_origem':['tipo_decisao','registro.tipo.nome','tipo'], 'ramo_direito_origem':['ramo_direito'],
        'captura_origem':['captured_at','scraped_at'],'coletor_origem':['spider_name'],'base_origem':['base','fonte_tabela']}
    row={name:scalar(flat,aliases)[0] for name,aliases in values.items()}
    record_hash=audit.digest(json.dumps(record,ensure_ascii=False,sort_keys=True,default=str,separators=(',',':')).encode())
    clean_hash=audit.digest(cleaned.encode()) if cleaned else None
    group_process=audit.digest(((tribunal or 'indeterminado')+'|'+re.sub(r'\W','',process)).encode()) if process else None
    group_doc=audit.digest(((tribunal or 'indeterminado')+'|'+doc).encode()) if doc else None
    ident=audit.digest(f"{entry['sha256']}|{entry['arquivo_id']}|{line}".encode())
    row.update(registro_id=ident,arquivo_id=entry['arquivo_id'],arquivo_origem=entry['arquivo'],
        arquivo_sha256=entry['sha256'],linha_origem=line,registro_original_sha256=record_hash,
        documento_id_origem=doc,tribunal=tribunal,tribunal_original=tribunal_raw,tribunal_metodo=method,
        processo_original=process,processo_cnj=cnj(process),data_julgamento=judgment,data_publicacao=publication,
        data_assinatura=signature,data_referencia_temporal=reference,data_referencia_tipo=ref_field,
        data_julgamento_campo=jfield,data_publicacao_campo=pfield,texto_campo_origem=field or None,
        texto_tipo_declarado='ementa' if field and 'ementa' in field.lower() else 'texto_busca_declarado' if field=='texto_busca' else 'inteiro_teor_declarado' if field else 'ausente',
        texto_original=original,texto_limpo=cleaned,ementa_original=ementa,ementa_limpa=clean_ementa or None,
        texto_original_sha256=audit.digest(original.encode()),texto_limpo_sha256=clean_hash,
        grupo_documental_sha256=group_doc,grupo_processo_sha256=group_process,url_origem=url,
        texto_chars_original=len(original),texto_chars_limpo=len(cleaned),offsets_identicos=original==cleaned,
        texto_alterado=original!=cleaned,operacoes_limpeza=operations,operacoes_ementa=ementa_operations,
        motivos_revisao=sorted(set(flags)),candidato_tecnico_indexacao=bool(cleaned and tribunal and not conflict and
            'rtf_nao_extraido' not in flags and 'html_nao_balanceado_revisar' not in flags),
        pertinencia_tematica_status='nao_avaliada',privacidade_status='nao_anonimizado_requer_revisao')
    return row


def arrow_schema():
    import pyarrow as pa
    return pa.schema([(k,pa.string()) for k in STR_FIELDS]+[
        ('linha_origem',pa.int64()),('texto_chars_original',pa.int64()),('texto_chars_limpo',pa.int64()),
        ('offsets_identicos',pa.bool_()),('texto_alterado',pa.bool_()),('candidato_tecnico_indexacao',pa.bool_()),
        ('operacoes_limpeza',pa.list_(pa.string())),('operacoes_ementa',pa.list_(pa.string())),('motivos_revisao',pa.list_(pa.string()))])


def run(root):
    import pyarrow as pa
    import pyarrow.parquet as pq
    root=Path(root)
    audit_folder,summary,profiles=load(root)
    entries=json.loads((audit_folder/'inventario.json').read_text(encoding='utf-8'))
    by_file={p['arquivo_id']:p for p in profiles}
    if len({e['arquivo_id'] for e in entries})!=len(entries):raise ValueError('IDs de arquivos duplicados.')
    protocol=audit.digest((audit.hash_file(__file__)+audit.hash_file(audit.__file__)).encode())
    output=root/'dados/processed/jurisprudencia'/summary['inventario_sha256']/protocol
    reports=root/'dados/relatorios/jurisprudencia/estruturacao'/summary['inventario_sha256']/protocol
    temporary=root/'tmp/jurisprudencia_estrutura'/summary['inventario_sha256']/protocol
    for folder in (output,reports,temporary):folder.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(temporary/'indice.sqlite')
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('CREATE TABLE IF NOT EXISTS registros(registro_id TEXT PRIMARY KEY,arquivo_id TEXT,texto_hash TEXT,processo_hash TEXT,documento_hash TEXT)')
    schema=arrow_schema(); manifests=[];quarantine=[]
    for e in entries:
        p=by_file[e['arquivo_id']]
        if p['status_leitura']!='concluido':
            quarantine.append({'arquivo':e['arquivo'],'arquivo_id':e['arquivo_id'],'sha256':e.get('sha256'),
                'motivo':p['status_leitura'],'registros_reais':None,'acao':'Recuperar origem e reauditar; original não movido nem reparado.'})
            continue
        source=Path(e['caminho_original'])
        print('Conferindo origem:',e['arquivo'],flush=True)
        if not source.is_file() or audit.hash_file(source)!=e['sha256']:
            raise ValueError('Fonte alterada ou ausente depois da auditoria; reauditar antes de continuar.')
        path=output/f"{e['arquivo_id']}.parquet";manifest_path=reports/f"{e['arquivo_id']}.json"
        if path.exists() and manifest_path.exists():
            old=json.loads(manifest_path.read_text(encoding='utf-8'))
            index_n=conn.execute('SELECT COUNT(*) FROM registros WHERE arquivo_id=?',(e['arquivo_id'],)).fetchone()[0]
            if (audit.hash_file(path)==old['saida_sha256'] and old['registros']==p['registros_lidos']==index_n):
                manifests.append(old);print('Checkpoint preservado:',e['arquivo'],flush=True);continue
        conn.execute('DELETE FROM registros WHERE arquivo_id=?',(e['arquivo_id'],));conn.commit()
        partial=path.with_suffix('.partial.parquet')
        count=0;previous_line=0;buffer=[];index=[];ops=Counter();flags=Counter();courts=Counter();meta=Counter()
        writer=pq.ParquetWriter(partial,schema,compression='zstd')
        issues={}
        try:
            for line,record in audit.records(source,issues):
                if line<=previous_line:raise ValueError('Ordem de origem não monotônica.')
                previous_line=line
                row=normalize_record(record,e,line);buffer.append(row)
                index.append((row['registro_id'],e['arquivo_id'],row['texto_limpo_sha256'],row['grupo_processo_sha256'],row['grupo_documental_sha256']))
                count+=1;ops.update(row['operacoes_limpeza']);flags.update(row['motivos_revisao']);courts[row['tribunal'] or 'não identificado']+=1
                meta['texto_alterado']+=row['texto_alterado'];meta['candidatos_tecnicos']+=row['candidato_tecnico_indexacao']
                meta['chars_antes']+=row['texto_chars_original'];meta['chars_depois']+=row['texto_chars_limpo']
                if len(buffer)>=256:
                    writer.write_table(pa.Table.from_pylist(buffer,schema=schema));buffer.clear()
                    conn.executemany('INSERT INTO registros VALUES (?,?,?,?,?)',index);conn.commit();index.clear()
                if count%10000==0:print(e['arquivo'],count,'registros estruturados',flush=True)
            if buffer:writer.write_table(pa.Table.from_pylist(buffer,schema=schema))
            if index:conn.executemany('INSERT INTO registros VALUES (?,?,?,?,?)',index);conn.commit()
        finally:writer.close()
        if count!=p['registros_lidos']:raise ValueError('Quantidade estruturada diverge da auditoria.')
        if audit.hash_file(source)!=e['sha256']:raise ValueError('Origem foi modificada durante a estruturação.')
        partial.replace(path)
        manifest={'arquivo_id':e['arquivo_id'],'arquivo':e['arquivo'],'origem_sha256':e['sha256'],
            'registros':count,'saida':str(path.relative_to(root)),'saida_sha256':audit.hash_file(path),
            'pyarrow':pa.__version__,'operacoes':dict(ops),'motivos_revisao':dict(flags),'tribunais':dict(courts),**dict(meta)}
        audit.write_json(manifest_path,manifest);manifests.append(manifest)
    total=sum(m['registros'] for m in manifests)
    if total!=summary['registros_lidos']:raise ValueError('Total estruturado não corresponde aos registros integralmente auditados.')
    # Grupos laterais evitam reescrever ou apagar textos; join por registro_id.
    for col in ('texto_hash','processo_hash','documento_hash'):
        conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{col} ON registros({col})')
    conn.commit()
    repeat_schema=pa.schema([('registro_id',pa.string()),('ocorrencias_texto_limpo',pa.int64()),
                            ('ocorrencias_processo',pa.int64()),('ocorrencias_chave_documental',pa.int64())])
    sql='''SELECT r.registro_id, COALESCE(t.n,0), COALESCE(p.n,0), COALESCE(d.n,0) FROM registros r
        LEFT JOIN (SELECT texto_hash,COUNT(*) n FROM registros WHERE texto_hash IS NOT NULL GROUP BY texto_hash) t ON r.texto_hash=t.texto_hash
        LEFT JOIN (SELECT processo_hash,COUNT(*) n FROM registros WHERE processo_hash IS NOT NULL GROUP BY processo_hash) p ON r.processo_hash=p.processo_hash
        LEFT JOIN (SELECT documento_hash,COUNT(*) n FROM registros WHERE documento_hash IS NOT NULL GROUP BY documento_hash) d ON r.documento_hash=d.documento_hash'''
    cursor=conn.execute(sql);count_index=0
    with pq.ParquetWriter(output/'sinais_repeticao.parquet',repeat_schema,compression='zstd') as writer:
        while True:
            block=cursor.fetchmany(2048)
            if not block:break
            writer.write_table(pa.Table.from_pylist([dict(zip(repeat_schema.names,r)) for r in block],schema=repeat_schema));count_index+=len(block)
    if count_index!=total:raise ValueError('Índice lateral de repetição incompleto.')
    duplicate_stats=[]
    for col,name in (('texto_hash','texto_limpo'),('processo_hash','processo'),('documento_hash','chave_documental_candidata')):
        group_count,excess=conn.execute(f'SELECT COUNT(*),COALESCE(SUM(n-1),0) FROM (SELECT COUNT(*) n FROM registros WHERE {col} IS NOT NULL GROUP BY {col} HAVING COUNT(*)>1)').fetchone()
        duplicate_stats.append({'criterio':name,'grupos_repetidos':group_count,'ocorrencias_excedentes':excess})
    conn.close()
    totals=Counter();operations=Counter();reason=Counter()
    for m in manifests:
        totals.update({k:m.get(k,0) for k in ('registros','texto_alterado','candidatos_tecnicos','chars_antes','chars_depois')})
        operations.update(m['operacoes']);reason.update(m['motivos_revisao'])
    result={'protocolo':PROTOCOL,'inventario_sha256':summary['inventario_sha256'],'codigo_estrutura_sha256':audit.hash_file(__file__),
        'codigo_funcoes_auditoria_sha256':audit.hash_file(audit.__file__),'executado_em_utc':datetime.now(timezone.utc).isoformat(),
        'pasta_dados':str(output.relative_to(root)),'arquivos_estruturados':len(manifests),'arquivos_em_quarentena':len(quarantine),
        **dict(totals),'operacoes':dict(operations),'motivos_revisao':dict(reason),'grupos_repeticao':duplicate_stats,
        'reconciliacao_com_auditoria':total==summary['registros_lidos'],'registros_excluidos_automaticamente':0,
        'anonimizacao_realizada':False,'avaliacao_merito_juridico':False,'indexacao_realizada':False,
        'nota':'Candidato técnico não equivale a aprovação de privacidade, licença, pertinência temática ou correção jurídica.'}
    audit.write_json(reports/'resumo_estruturacao.json',result)
    audit.write_json(reports/'quarentena_manifesto.json',quarantine)
    audit.write_json(reports/'manifestos_arquivos.json',manifests)
    audit.write_csv(reports/'repeticoes_pos_limpeza.csv',duplicate_stats)
    audit.write_csv(reports/'motivos_revisao.csv',[{'motivo':k,'registros_com_sinal':v} for k,v in sorted(reason.items())],['motivo','registros_com_sinal'])
    audit.write_csv(reports/'schema_canonico.csv',[{'campo':f.name,'tipo':str(f.type)} for f in schema])
    audit.write_json(output/'manifesto.json',result)
    audit.write_json(root/'dados/processed/jurisprudencia/estrutura_ativa.json',{'pasta_dados':str(output.relative_to(root)),'pasta_relatorios':str(reports.relative_to(root))})
    return reports,result


def figures(folder,result):
    import matplotlib.pyplot as plt
    folder=Path(folder)
    fig,axes=plt.subplots(1,2,figsize=(14,6))
    axes[0].bar(['Registros auditados e preservados','Texto modificado na versão limpa','Candidatos técnicos'],
                [result['registros'],result['texto_alterado'],result['candidatos_tecnicos']],color=['#4477aa','#cc9944','#228866'])
    axes[0].set_title('Transformações sem exclusão automática')
    axes[0].tick_params(axis='x',rotation=15)
    reasons=sorted(result['motivos_revisao'].items(),key=lambda pair:pair[1],reverse=True)[:10]
    if reasons:axes[1].barh([r[0] for r in reasons],[r[1] for r in reasons],color='#cc9944')
    axes[1].set_title('Sinais para revisão — podem se sobrepor')
    fig.tight_layout();fig.savefig(folder/'limpeza_estrutura.png',dpi=150)
    return [fig]
