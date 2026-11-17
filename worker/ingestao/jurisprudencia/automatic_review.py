"""Diagnóstico automático posterior ao PLN, sem exclusão destrutiva ou parecer jurídico."""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import date,datetime,timezone
from urllib.parse import urlsplit
import hashlib,json,sqlite3
from . import audit,dataset,light_nlp
from .readiness import Components,split_name

SIGNALS={'clt':r'(^|[^a-z])clt([^a-z]|$)|consolida..o das leis do trabalho',
    'jurisdicao':r'justi.a do trabalho|tribunal superior do trabalho|trabalhista',
    'emprego':r'v.nculo empregat.cio|rela..o de emprego|contrato de trabalho|empregad[oa]',
    'verbas':r'fgts|verbas rescis.rias|horas extras|aviso.pr.vio|sal.rio|f.rias'}


def infer_content(declared,chars,structure_signal):
    if not chars:return 'sem_texto'
    if declared=='ementa':return 'ementa_declarada'
    if declared=='inteiro_teor_declarado':
        if chars<500:return 'texto_curto_rotulado_inteiro_teor'
        return 'inteiro_teor_com_indicio_estrutural' if structure_signal else 'inteiro_teor_declarado_sem_indicio_no_prefixo'
    return 'texto_busca_declarado' if declared=='texto_busca_declarado' else 'texto_sem_tipo_confirmado'


def official_host(url):
    try:
        parsed=urlsplit(url or '');host=(parsed.hostname or '').lower()
        return host if parsed.scheme=='https' and host.endswith('.jus.br') and not parsed.username and not parsed.password and parsed.port in (None,443) else None
    except ValueError:return None


def policy():
    return dict(versao='lexia-preparacao-automatica-v1',uso_principal='RAG de jurisprudência trabalhista',
        rag=dict(tribunais_prioritarios=['TST','TRT-*'],stf='Candidato somente com pelo menos dois grupos de sinais lexicais no prefixo de até 8.000 caracteres.',
            tamanho_minimo_caracteres=80,origem_hash_tamanho_confirmados=True,licenca='Registrar declaração do publicador; não equivale a parecer sobre direitos de terceiros.',
            periodo='Todos os períodos observados; datas ausentes/futuras são alertas. Não é aplicado corte cronológico arbitrário.',
            assunto='Trabalhista por jurisdição ou sinais lexicais documentados; sem classificação semântica exaustiva.'),
        avaliacao=dict(particoes='Proposta 80/10/10 por componentes relacionados, recalculada após o PLN.',
            agrupamento='Texto principal idêntico e processo canônico sintático ficam no mesmo split.',gabarito='Não fornecido neste lote; métricas de respostas do modelo não calculadas.'),
        ajuste_fino=dict(habilitado=False,motivo='Objetivo não solicitado; nenhum treinamento ou conjunto supervisionado foi criado.'),
        automacao=dict(validacao='Regras, invariantes e evidências computacionais.',
            amostras='Seleção determinística de textos curtos, longos e com alertas por arquivo; referências por ID, sem expor conteúdo.',
            limite='Sinais não comprovam integralidade do documento, pertinência jurídica ou anonimização completa. Integrações adicionais têm seu estado técnico documentado.'))


def load(root):
    root=Path(root).resolve();p=json.loads((root/'dados/relatorios/jurisprudencia/automacao/ativa.json').read_text(encoding='utf-8'))
    folder=(root/p['pasta_relatorios']).resolve()
    if not folder.is_relative_to(root/'dados/relatorios/jurisprudencia/automacao'):raise ValueError('Relatório fora da pasta permitida.')
    return folder,json.loads((folder/'resumo_automatico.json').read_text(encoding='utf-8'))


def run(root):
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    root=Path(root).resolve();pln_dir,pln=light_nlp.load(root);_,base_dir=dataset.locations(root)
    base={m['arquivo_id']:m for m in json.loads((base_dir/'manifestos_arquivos.json').read_text(encoding='utf-8'))}
    provenance=json.loads((root/'dados/relatorios/jurisprudencia/origens_huggingface/rastreabilidade_atual.json').read_text(encoding='utf-8'))
    verified={r['arquivo_id']:bool(r['correspondencias']) for r in provenance}
    signature=audit.digest((audit.hash_file(__file__)+audit.hash_file(pln_dir/'resumo_pln.json')).encode())
    folder=root/'dados/relatorios/jurisprudencia/automacao'/signature;out=root/'dados/processed/jurisprudencia/automacao'/signature
    folder.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    audit.write_json(folder/'criterios_uso_recorte.json',policy())
    conn=sqlite3.connect('file:'+str((root/pln['csv']).parent/'auditoria_hashes.sqlite').replace('\\','/')+'?mode=ro',uri=True)
    text_hashes=dict(conn.execute('SELECT id,principal FROM docs'));conn.close()
    components=Components();seen_text={};seen_process={};rows=[];copies=defaultdict(list)
    counts=Counter();coverage=Counter();lengths=Counter();by_court=Counter();quality=Counter();samples=defaultdict(list)
    urls=[];today=date.today().isoformat()
    for f in pln['arquivos']:
        ident=f['arquivo_id'];path=root/f['arquivo'];canonical=root/base[ident]['saida']
        if audit.hash_file(path)!=f['sha256']:raise ValueError('Shard PLN alterado.')
        if audit.hash_file(canonical)!=base[ident]['saida_sha256']:raise ValueError('Base canônica alterada.')
        meta_cols=['registro_id','texto_tipo_declarado','processo_original','documento_id_origem','ramo_direito_origem','url_origem','motivos_revisao']
        metadata={r['registro_id']:r for r in pq.read_table(canonical,columns=meta_cols).to_pylist()}
        for batch in pq.ParquetFile(path).iter_batches(batch_size=512,use_threads=False):
            main=pa.array([None]*batch.num_rows,type=pa.string())
            for field in light_nlp.TEXT_FIELDS:
                main=pc.if_else(pc.equal(batch.column(batch.schema.get_field_index('texto_principal_campo')),field),batch.column(batch.schema.get_field_index(field)),main)
            chars=pc.fill_null(pc.utf8_length(main),0)
            prefix=pc.utf8_lower(pc.utf8_slice_codeunits(pc.fill_null(main,''),0,8000))
            signals={k:pc.match_substring_regex(prefix,v).to_pylist() for k,v in SIGNALS.items()}
            structural=pc.match_substring_regex(prefix,r'relat.rio|fundamenta..o|voto|ac.rdao|decid').to_pylist()
            short_rows=pa.Table.from_batches([batch]).select([k for k in batch.schema.names if k not in light_nlp.TEXT_FIELDS]).to_pylist()
            for j,(r,n) in enumerate(zip(short_rows,chars.to_pylist(),strict=True)):
                m=metadata.pop(r['registro_id']);court=r['tribunal'] or 'não identificado'
                declared=m['texto_tipo_declarado'];inferred=infer_content(declared,n,structural[j])
                score=sum(bool(signals[k][j]) for k in signals)
                topic='jurisdicao_trabalhista' if court=='TST' or court.startswith('TRT-') else 'sinal_lexical_trabalhista' if court=='STF' and score>=2 else 'sem_sinal_suficiente_no_prefixo'
                future=any(r[k] and r[k]>today for k in ['data_julgamento','data_publicacao','data_assinatura'])
                flags=[]
                if n<80:flags.append('texto_menor_80')
                if inferred=='texto_curto_rotulado_inteiro_teor':flags.append('inteiro_teor_curto')
                if not verified.get(ident):flags.append('origem_sem_correspondencia_hash')
                if court=='não identificado':flags.append('tribunal_nao_identificado')
                if future:flags.append('data_futura')
                if not any(r[k] for k in ['data_julgamento','data_publicacao','data_assinatura']):flags.append('sem_datas')
                flags.extend(x for x in m['motivos_revisao'] if x in ('publicacao_anterior_julgamento','unicode_substituicao_revisar','possivel_mojibake_nao_corrigido'))
                candidate=bool(n>=80 and verified.get(ident) and topic!='sem_sinal_suficiente_no_prefixo' and court!='não identificado' and not future and 'inteiro_teor_curto' not in flags)
                process,method=dataset.process_group_key(r['tribunal'],r['processo_cnj'],m['processo_original'])
                h=text_hashes.pop(r['registro_id']);i=components.add()
                for key,seen in [(h,seen_text),(process,seen_process)]:
                    if key:
                        if key in seen:components.union(i,seen[key])
                        else:seen[key]=i
                # Chave estrita de cópia textual candidata; não afirma mesmo acórdão.
                copy_key=hashlib.sha256('|'.join([h,court,process,r['data_julgamento'] or r['data_assinatura'] or '',declared]).encode()).hexdigest() if h and process and (r['data_julgamento'] or r['data_assinatura']) else None
                if copy_key:copies[copy_key].append(r['registro_id'])
                rows.append(dict(registro_id=r['registro_id'],arquivo_id=ident,tribunal=court,tipo_conteudo_declarado=declared,
                    tipo_conteudo_inferido=inferred,metodo_tipo_conteudo='rotulo_fonte_mais_tamanho_e_marcadores_no_prefixo',texto_caracteres=n,
                    sinais_tematicos=score,triagem_tematica=topic,candidato_rag_criterios_automaticos=candidate,
                    grupo_copia_textual=copy_key,grupo_processo=process,metodo_processo=method,alertas=sorted(set(flags))))
                counts['registros']+=1;counts['candidatos_rag_criterios_automaticos']+=candidate;counts['texto_caracteres_total']+=n
                counts['textos_vazios']+=n==0;coverage[(court,declared,inferred)]+=1;by_court[(court,topic,candidate)]+=1
                lengths['<80' if n<80 else '80-499' if n<500 else '500-1999' if n<2000 else '2000-9999' if n<10000 else '>=10000']+=1
                quality.update(set(flags))
                for stratum in (['curto'] if n<500 else ['longo'] if n>=50000 else [])+(['alerta'] if flags else []):
                    samples[(ident,stratum)].append(r['registro_id'])
                host=official_host(m['url_origem'])
                if host:urls.append(dict(registro_id=r['registro_id'],url=m['url_origem'],host=host))
        if metadata:raise ValueError('Metadados não alinhados.')
        print('Verificação automática:',ident,'|',len(rows),'registros',flush=True)
    if len(rows)!=pln['registros'] or text_hashes:raise ValueError('Cobertura incompleta.')
    minima={}
    for i,r in enumerate(rows):
        g=components.find(i);minima[g]=min(minima.get(g,r['registro_id']),r['registro_id'])
    representatives={k:min(ids) for k,ids in copies.items()}
    splits=Counter();counts['grupos_copias_textuais_candidatas']=sum(len(v)>1 for v in copies.values())
    counts['ocorrencias_copias_textuais_excedentes']=sum(max(0,len(v)-1) for v in copies.values())
    for i,r in enumerate(rows):
        r['grupo_avaliacao']=minima[components.find(i)];r['split_proposto']=split_name(r['grupo_avaliacao'])
        r['representante_copia_textual']=r['grupo_copia_textual'] is None or representatives[r['grupo_copia_textual']]==r['registro_id']
        r['candidato_consolidado']=r['candidato_rag_criterios_automaticos'] and r['representante_copia_textual']
        counts['candidatos_consolidados']+=r['candidato_consolidado'];splits[r['split_proposto']]+=1
    # Conferência independente das chaves conhecidas na partição salva.
    assigned={r['registro_id']:r['split_proposto'] for r in rows};leaks=0
    for ids in copies.values():leaks+=len({assigned[i] for i in ids})>1
    if leaks:raise ValueError('Vazamento nas cópias relacionadas.')
    pq.write_table(pa.Table.from_pylist(rows),out/'indice_automatico.parquet',compression='zstd')
    audit.write_csv(folder/'cobertura_conteudo.csv',[dict(tribunal=c,tipo_declarado=d,tipo_inferido=i,registros=n) for (c,d,i),n in sorted(coverage.items())])
    audit.write_csv(folder/'recorte_tribunais.csv',[dict(tribunal=c,triagem=t,candidato=ok,registros=n) for (c,t,ok),n in sorted(by_court.items())])
    audit.write_csv(folder/'alertas_automaticos.csv',[dict(alerta=k,registros=n) for k,n in sorted(quality.items())])
    audit.write_csv(folder/'tamanho_textos.csv',[dict(faixa=k,registros=v) for k,v in lengths.items()])
    sample_rows=[dict(arquivo_id=f,estrato=s,registro_id=rid,metodo='menores_ids_hash_ate_15_por_arquivo_estrato') for (f,s),ids in sorted(samples.items()) for rid in sorted(ids)[:15]]
    audit.write_csv(folder/'amostras_automaticas.csv',sample_rows)
    # URLs ficam no diretório processado, sem expor caminhos/processos no relatório público.
    selected=[];perhost=Counter()
    for r in sorted(urls,key=lambda r:r['registro_id']):
        if perhost[r['host']]<2 and len(selected)<8:selected.append(r);perhost[r['host']]+=1
    audit.write_json(out/'fontes_oficiais_amostra.json',selected)
    result={**dict(counts),'executado_em_utc':datetime.now(timezone.utc).isoformat(),'codigo_sha256':audit.hash_file(__file__),
        'base_pln_csv_sha256':pln['csv_sha256'],'media_caracteres':counts['texto_caracteres_total']/len(rows),
        'componentes_avaliacao':len(minima),'splits_propostos':dict(splits),'grupos_copias_atravessando_splits':leaks,
        'amostras_automaticas':len(sample_rows),'fontes_oficiais_candidatas_amostra':len(selected),
        'indice':str((out/'indice_automatico.parquet').relative_to(root)),'indice_sha256':audit.hash_file(out/'indice_automatico.parquet'),
        'pasta_dados':str(out.relative_to(root)),'exclusoes_fisicas':0,'indexacao_executada':False,'publicacao_executada':False,
        'anonimizacao_integral':False,'avaliacao_respostas_modelo_executada':False,
        'limites':'Critérios automáticos versionados, sem parecer jurídico. Triagem temática e inferência de conteúdo examinam até 8.000 caracteres. Cópia textual candidata não comprova identidade de acórdão. Vínculos semânticos não reconhecidos podem não ser agrupados.'}
    audit.write_json(folder/'resumo_automatico.json',result)
    audit.write_json(root/'dados/relatorios/jurisprudencia/automacao/ativa.json',dict(pasta_relatorios=str(folder.relative_to(root))))
    print('Automação concluída:',folder,flush=True)
    return folder,result
