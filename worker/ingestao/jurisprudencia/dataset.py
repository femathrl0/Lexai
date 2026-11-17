"""Abre somente os shards canônicos, sem somar o índice lateral ao corpus."""
from pathlib import Path
import json
import hashlib
import re
import sqlite3


def locations(root):
    root=Path(root).resolve()
    active=json.loads((root/'dados/processed/jurisprudencia/estrutura_ativa.json').read_text(encoding='utf-8'))
    data=(root/active['pasta_dados']).resolve();reports=(root/active['pasta_relatorios']).resolve()
    if not data.is_relative_to(root/'dados/processed/jurisprudencia') or not reports.is_relative_to(root/'dados/relatorios/jurisprudencia/estruturacao'):
        raise ValueError('Diretório de estruturação fora do projeto.')
    return data,reports


def open_dataset(root):
    import pyarrow.dataset as ds
    root=Path(root).resolve();data,reports=locations(root)
    manifests=json.loads((reports/'manifestos_arquivos.json').read_text(encoding='utf-8'))
    files=[]
    for manifest in manifests:
        path=(root/manifest['saida']).resolve()
        if not path.is_relative_to(data) or path.name=='sinais_repeticao.parquet':
            raise ValueError('Shard inválido no manifesto.')
        files.append(str(path))
    if len(files)!=len(set(files)):raise ValueError('Shard listado mais de uma vez.')
    return ds.dataset(files,format='parquet')


def process_group_key(tribunal,process_cnj,process_original):
    if process_cnj and re.fullmatch(r'\d{20}',process_cnj):
        value='cnj_sintatico|'+process_cnj
        return hashlib.sha256(value.encode()).hexdigest(),'cnj_sintatico_sem_validacao_dv'
    if process_original and tribunal:
        value='numero_antigo|'+tribunal+'|'+re.sub(r'\W','',process_original).casefold()
        return hashlib.sha256(value.encode()).hexdigest(),'formato_recebido_com_namespace_tribunal'
    return None,'sem_chave_segura'


def build_process_groups(root):
    """Índice auxiliar: CNJ sintático agrupa mesmo processo entre tribunais."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from .audit import hash_file,write_json
    root=Path(root).resolve();data,reports=locations(root)
    source_manifest=hash_file(reports/'manifestos_arquivos.json');code_hash=hash_file(__file__)
    target=data/'grupos_processuais.parquet';manifest_path=reports/'manifesto_grupos_processuais.json'
    if target.exists() and manifest_path.exists():
        old=json.loads(manifest_path.read_text(encoding='utf-8'))
        if old['base_manifesto_sha256']==source_manifest and old['codigo_sha256']==code_hash and hash_file(target)==old['indice_sha256']:
            return old
    private=root/'tmp/jurisprudencia_estrutura'/data.parent.name/data.name
    private.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(private/'processos_canonicos.sqlite')
    conn.execute('CREATE TABLE IF NOT EXISTS grupos(registro_id TEXT PRIMARY KEY,chave TEXT,metodo TEXT)')
    conn.execute('DELETE FROM grupos');conn.commit()
    total=0
    for batch in open_dataset(root).scanner(columns=['registro_id','tribunal','processo_cnj','processo_original'],batch_size=2048,use_threads=False).to_batches():
        rows=[]
        for r in batch.to_pylist():
            key,method=process_group_key(r['tribunal'],r['processo_cnj'],r['processo_original'])
            rows.append((r['registro_id'],key,method))
        conn.executemany('INSERT INTO grupos VALUES (?,?,?)',rows);conn.commit();total+=len(rows)
    conn.execute('CREATE INDEX IF NOT EXISTS idx_chave ON grupos(chave)');conn.commit()
    cursor=conn.execute('SELECT g.registro_id,g.chave,g.metodo,COALESCE(c.n,0) FROM grupos g LEFT JOIN (SELECT chave,COUNT(*) n FROM grupos WHERE chave IS NOT NULL GROUP BY chave)c ON g.chave=c.chave')
    schema=pa.schema([('registro_id',pa.string()),('grupo_processo_canonico_sha256',pa.string()),('metodo',pa.string()),('ocorrencias',pa.int64())])
    with pq.ParquetWriter(target,schema,compression='zstd') as writer:
        while True:
            rows=cursor.fetchmany(2048)
            if not rows:break
            writer.write_table(pa.Table.from_pylist([dict(zip(schema.names,r)) for r in rows],schema=schema))
    methods=dict(conn.execute('SELECT metodo,COUNT(*) FROM grupos GROUP BY metodo'))
    repeated,excess=conn.execute('SELECT COUNT(*),COALESCE(SUM(n-1),0) FROM (SELECT COUNT(*) n FROM grupos WHERE chave IS NOT NULL GROUP BY chave HAVING COUNT(*)>1)').fetchone()
    conn.close()
    result={'base_manifesto_sha256':source_manifest,'codigo_sha256':code_hash,'indice_sha256':hash_file(target),
            'registros':total,'metodos':methods,'grupos_repetidos':repeated,'ocorrencias_excedentes':excess,
            'criterio':'CNJ sintático sem prefixo de tribunal para agrupar recursos do mesmo processo entre tribunais. Números antigos mantêm namespace de tribunal.',
            'limite':'Não valida DV ou identidade jurídica; formatos antigos e casos sem chave exigem revisão. Não exclui registros nem cria splits automaticamente.'}
    write_json(manifest_path,result)
    return result


def conclusion(root):
    data,reports=locations(root)
    result=json.loads((reports/'resumo_estruturacao.json').read_text(encoding='utf-8'))
    text=f'''# Conclusão da limpeza e estruturação

Foram preservados **{result['registros']:,} registros** em **{result['arquivos_estruturados']} shards canônicos**, com **{result['registros_excluidos_automaticamente']} exclusões automáticas**. A reconciliação com a auditoria é **{result['reconciliacao_com_auditoria']}**. Há **{result['arquivos_em_quarentena']} arquivo em manifesto de quarentena**, sem estimar sua quantidade de registros inacessíveis.

## Texto e metadados

Em {result['texto_alterado']:,} registros, a versão limpa difere da versão textual original selecionada. As duas são preservadas, com hashes e operações. As regras tratam HTML, NFC Unicode, BOM, espaços, quebras de linha e controles de apresentação. Não há remoção de stopwords ou reescrita jurídica. HTML não balanceado, RTF e possíveis problemas de codificação ficam identificados para conferência.

Julgamento, publicação e assinatura têm campos separados. A data de referência temporal pode ser assinatura quando assim identificada; não é promovida a julgamento. O processo original é preservado, e a extração de CNJ é sintática, sem validação de dígitos verificadores. As informações não mapeadas permanecem recuperáveis nas fontes pela linhagem de arquivo/hash/linha e pelo hash do registro original.

Há {result['candidatos_tecnicos']:,} candidatos pelos critérios técnicos mínimos. Esse indicador não aprova privacidade, licença, pertinência temática ou correção jurídica. A base inteira continua marcada como **não anonimizada e sujeita a revisão**.

## Repetições

O índice lateral registra repetições de texto limpo, processo e chave documental candidata. Nenhum desses grupos remove dados. Mesmo processo pode ter várias decisões e os identificadores dos produtores podem ter namespaces distintos. Os critérios podem se sobrepor.

Use `worker.ingestao.jurisprudencia.dataset.open_dataset(root)` para abrir somente os shards canônicos. O arquivo `sinais_repeticao.parquet` é um índice lateral, não outro conjunto de decisões. Ler todos os Parquet indiscriminadamente pode duplicar a contagem de linhas.

O índice `grupos_processuais.parquet` usa CNJ sintático sem prefixo do tribunal julgador para reunir referências ao mesmo processo entre graus de jurisdição. Números antigos mantêm namespace de tribunal; exigem revisão quando houver formas diferentes. Esse agrupamento não valida dígitos verificadores nem cria uma partição de avaliação automaticamente.

## Próximos passos

Recuperar o arquivo de leitura problemática; confirmar nomes autor/dataset, versões e licenças das origens; revisar dados pessoais; avaliar pertinência trabalhista, sobretudo nos documentos do STF; decidir sobre versões e duplicatas; e definir chunking e avaliação com grupos relacionados no mesmo split. Nenhum índice, embedding ou treinamento foi executado e o RAG legislativo anterior permanece separado.

Dados protegidos: `{data.relative_to(Path(root).resolve())}`.
'''
    (reports/'conclusao_estrutura.md').write_text(text,encoding='utf-8')
    return text
