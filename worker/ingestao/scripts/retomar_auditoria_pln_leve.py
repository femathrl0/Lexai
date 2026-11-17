"""Recupera a auditoria e finaliza shards completos sem repetir a normalização."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import json,sys,unicodedata,sqlite3,csv


def main():
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
    from worker.ingestao.jurisprudencia import audit,dataset,privacy,structure,light_nlp as pln
    _,protected=privacy.load(root);_,base_reports=dataset.locations(root)
    signature=audit.digest((audit.hash_file(pln.__file__)+audit.hash_file(privacy.__file__)+audit.hash_file(structure.__file__)+protected['csv_sha256']).encode())
    out=root/'dados/processed/jurisprudencia/pln_leve'/signature;folder=root/'dados/relatorios/jurisprudencia/pln_leve'/signature
    if not (out/'jurisprudencia_pln_leve.csv.partial').exists() and not (out/'jurisprudencia_pln_leve.csv').exists():
        completed=[p.parent for p in (root/'dados/processed/jurisprudencia/pln_leve').glob('*/jurisprudencia_pln_leve.csv.partial')
                   if all((p.parent/(m['arquivo_id']+'.parquet')).exists() for m in protected['arquivos_protegidos'])]
        if len(completed)!=1:raise ValueError('Não há uma única execução completa recuperável.')
        out=completed[0];folder=root/'dados/relatorios/jurisprudencia/pln_leve'/out.name
    target=out/'jurisprudencia_pln_leve.csv';partial=target.with_suffix('.csv.partial')
    source=partial if partial.exists() else target
    checkpoint=folder/'resumo_recuperacao.json'
    if '--finalizar' in sys.argv:
        result=json.loads(checkpoint.read_text(encoding='utf-8'))
        if source.stat().st_size!=result['csv_bytes'] or audit.hash_file(source)!=result['csv_sha256']:
            raise ValueError('CSV alterado depois da validação.')
        if partial.exists():privacy.replace_completed(partial,target)
        audit.write_json(folder/'resumo_pln.json',result)
        audit.write_json(root/'dados/processed/jurisprudencia/pln_leve/ativa.json',dict(pasta_dados=str(out.relative_to(root)),pasta_relatorios=str(folder.relative_to(root))))
        print('PLN finalizado:',target,flush=True);return
    base={m['arquivo_id']:m for m in json.loads((base_reports/'manifestos_arquivos.json').read_text(encoding='utf-8'))}
    counts=Counter();ops=Counter();files=[]
    # Sinal amplo para revisão, sem tentar provar que houve uma palavra partida.
    broken=r'[-\x{00ad}][ \t]*\n'
    for m in protected['arquivos_protegidos']:
        ident=m['arquivo_id'];before_path=root/m['arquivo'];after_path=out/(ident+'.parquet')
        if audit.hash_file(before_path)!=m['sha256']:raise ValueError('Entrada protegida alterada.')
        if pq.ParquetFile(after_path).metadata.num_rows!=m['totais']['registros']:raise ValueError('Shard incompleto.')
        if pq.read_schema(after_path).names!=pln.OUTPUT_FIELDS:raise ValueError('Esquema divergente.')
        cache=folder/('recuperacao_'+ident+'.json')
        after_hash=audit.hash_file(after_path)
        if cache.exists():
            saved=json.loads(cache.read_text(encoding='utf-8'))
            if saved['codigo_recuperacao_sha256']==audit.hash_file(__file__) and saved['file']['sha256']==after_hash and saved['file']['origem_sha256']==m['sha256']:
                counts.update(saved['indicadores']);ops.update(saved['operacoes']);files.append(saved['file'])
                print('Conferência preservada:',ident,flush=True);continue
        previous_counts=counts.copy();previous_ops=ops.copy()
        canonical=root/base[ident]['saida']
        if audit.hash_file(canonical)!=base[ident]['saida_sha256']:raise ValueError('Base original alterada.')
        types={r['registro_id']:r['texto_tipo_declarado'] for r in pq.read_table(canonical,columns=['registro_id','texto_tipo_declarado']).to_pylist()}
        left=pq.ParquetFile(before_path).iter_batches(batch_size=128,use_threads=False)
        right=pq.ParquetFile(after_path).iter_batches(batch_size=128,use_threads=False)
        n=0
        for old,new in zip(left,right,strict=True):
            if old.num_rows!=new.num_rows:raise ValueError('Batches desalinhados.')
            for name in pln.TEXT_FIELDS:
                column=new.column(new.schema.get_field_index(name))
                for key,pattern in [('campos_com_hifen_em_fim_de_linha_revisar',broken),
                                    ('campos_com_entidades_residuais_revisar',pln.ENTITY.pattern),
                                    ('campos_com_substituicao_unicode_revisar','\ufffd')]:
                    counts[key]+=pc.sum(pc.cast(pc.fill_null(pc.match_substring_regex(column,pattern),False),pa.int64())).as_py() or 0
            for before,after in zip(old.to_pylist(),new.to_pylist(),strict=True):
                if before['registro_id']!=after['registro_id']:raise ValueError('IDs desalinhados.')
                main,fields=pln.separate_texts(before['texto_protegido'],before['ementa_protegida'],types.pop(before['registro_id']))
                if main!=after['texto_principal_campo']:raise ValueError('Tipo textual alterado.')
                if any(before[k]!=after[k] for k in pln.META):raise ValueError('Metadado alterado.')
                for field,value in fields.items():
                    actual=after[field]
                    if value!=actual:
                        normalized,operations=pln.clean_light(value)
                        expected,nmask=privacy.mask_array(pa.array([normalized],type=pa.string()))
                        if expected[0].as_py()!=actual:raise ValueError('Saída não corresponde às regras de limpeza.')
                        ops.update(operations);counts['substituicoes_cpf_apos_decodificacao']+=nmask
                        counts['campos_textuais_alterados']+=value!=normalized
                        counts['campos_textuais_alterados_finais']+=1
                    if value is not None and not value.strip():counts['campos_vazios_antes']+=1
                    if actual is not None and not actual.strip():counts['campos_vazios_depois']+=1
                    if actual is None:counts['campos_ausentes_'+field]+=1
                counts['registros']+=1;n+=1
                counts['textos_principais_vazios_antes']+=not bool(before['texto_protegido'] and before['texto_protegido'].strip())
                counts['textos_principais_vazios_depois']+=not bool(after[main] and after[main].strip())
        if types or n!=m['totais']['registros']:raise ValueError('Cobertura incompleta.')
        file=dict(arquivo_id=ident,arquivo=str(after_path.relative_to(root)),registros=n,sha256=after_hash,origem_sha256=m['sha256'])
        files.append(file)
        audit.write_json(cache,dict(codigo_recuperacao_sha256=audit.hash_file(__file__),file=file,
            indicadores={k:v-previous_counts.get(k,0) for k,v in counts.items()},
            operacoes={k:v-previous_ops.get(k,0) for k,v in ops.items()}))
        print('Auditoria recuperada:',ident,n,'registros',flush=True)
    if counts['registros']!=protected['registros']:raise ValueError('Contagem global divergente.')
    conn=sqlite3.connect('file:'+str(out/'auditoria_hashes.sqlite').replace('\\','/')+'?mode=ro',uri=True)
    if conn.execute('SELECT COUNT(*) FROM docs').fetchone()[0]!=counts['registros']:raise ValueError('Índice de auditoria incompleto.')
    conn.close()
    with (folder/'duplicatas_exatas.csv').open(encoding='utf-8-sig',newline='') as f:
        duplicates=[{k:(v if k=='campo' else int(v)) for k,v in r.items()} for r in csv.DictReader(f)]
    with (folder/'cabecalhos_rodapes_candidatos.csv').open(encoding='utf-8-sig',newline='') as f:edge_count=sum(1 for _ in csv.DictReader(f))
    samples=pq.read_table(out/'amostra_antes_depois.parquet',columns=['marcadores_juridicos_reduzidos'])
    counts['amostras_com_marcadores_juridicos_reduzidos_revisar']=sum(r['marcadores_juridicos_reduzidos']>0 for r in samples.to_pylist())
    print('Validando o CSV completo...',flush=True)
    validation=pln.validate_csv(source,counts['registros'])
    result=dict(executado_em_utc=datetime.now(timezone.utc).isoformat(),codigo_sha256=audit.hash_file(pln.__file__),
        assinatura_diretorio_execucao_anterior=out.name,codigo_regras_revalidadas_sha256=audit.hash_file(pln.__file__),
        auditoria_recuperacao_sha256=audit.hash_file(__file__),base_cpf_csv_sha256=protected['csv_sha256'],
        registros=counts['registros'],indicadores=dict(counts),operacoes=dict(ops),duplicatas_exatas=duplicates,
        linhas_limite_repetidas_candidatas=edge_count,amostras=samples.num_rows,amostra_automatica_status='verificada_por_marcadores',
        arquivos=files,csv=str(target.relative_to(root)),csv_sha256=audit.hash_file(source),csv_bytes=source.stat().st_size,
        validacao_csv=validation,amostra_local=str((out/'amostra_antes_depois.parquet').relative_to(root)),
        colunas=pln.OUTPUT_FIELDS,originais_preservados=True,exclusoes_automaticas=0,
        recuperacao='Shards completos preservados. Comparação integral com entrada protegida e validação de cada diferença pelas regras com NFC. Campos idênticos herdam NFC da base canônica. Sinal amplo de hífen no fim da linha recontado para revisão, sem afirmar palavra partida. CSV relido em processo separado da renomeação.',
        politica_pdf='Origem PDF não confirmada: nenhuma junção automática; correção exige PDF confirmado e vocabulário aprovado.',
        politica_bordas='Primeiras/últimas duas linhas, 8–200 caracteres, repetidas em pelo menos 10 registros: candidatos por hash, sem remoção.',
        limites='PLN leve de formato, sem remoção de stopwords/acentos/pontuação ou anonimização integral. Amostra comparada por marcadores; relatórios não exibem textos reais ou PII.')
    audit.write_json(checkpoint,result)
    print('Auditoria e CSV validados. Encerrando o leitor antes da renomeação.',flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
