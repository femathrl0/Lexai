"""Triagem local e partição provisória; não libera documentos para publicação."""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib
import json
import re
import struct
from urllib.parse import urlsplit

from . import audit, dataset
from .report import load


def theme(court, branch):
    """Evidência declarada, sem usar palavras do inteiro teor como rótulo jurídico."""
    if court == 'TST' or (court or '').startswith('TRT-'):
        return 'jurisdicao_trabalhista_revisar_conteudo'
    if branch and 'trabalh' in branch.casefold():
        return 'ramo_trabalhista_declarado_revisar'
    return 'pertinencia_nao_confirmada'


def split_name(key):
    bucket = int(hashlib.sha256(('juris-v1|' + key).encode()).hexdigest()[:8], 16) % 100
    return 'treino' if bucket < 80 else 'validacao' if bucket < 90 else 'teste'


class Components:
    def __init__(self):
        self.parent = []
    def add(self):
        n = len(self.parent); self.parent.append(n); return n
    def find(self, n):
        while self.parent[n] != n:
            self.parent[n] = self.parent[self.parent[n]]; n = self.parent[n]
        return n
    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[max(a,b)] = min(a,b)


def parquet_diagnostic(path):
    """Inspeciona limites do footer sem reescrever ou tentar inventar metadados."""
    import pyarrow.parquet as pq
    path = Path(path); size = path.stat().st_size
    with path.open('rb') as stream:
        head = stream.read(4); stream.seek(max(0,size-8)); tail = stream.read(8)
    length = struct.unpack('<I',tail[:4])[0] if len(tail)==8 else None
    result = {'arquivo':path.name,'bytes':size,'magic_inicial':head.hex(),
        'magic_final':tail[4:].hex() if len(tail)==8 else None,'footer_bytes_declarados':length,
        'footer_cabe_no_arquivo':bool(length is not None and 0 < length <= size-12),
        'original_alterado':False,'registros_recuperados':None}
    try:
        p = pq.ParquetFile(path)
        result.update(status='metadados_legiveis',registros_metadados=p.metadata.num_rows,
                      chaves_metadados=[k.decode('utf-8','replace') for k in (p.metadata.metadata or {})])
    except Exception as exc:
        result.update(status='metadados_ilegíveis',tipo_erro=type(exc).__name__,erro=str(exc)[:600],
            acao='Obter novamente o mesmo shard na origem e reauditar. PAR1 não garante integridade. Não é possível reconstruir com segurança apenas o footer.')
    return result


def run(root):
    import pyarrow as pa
    import pyarrow.parquet as pq
    root=Path(root).resolve(); data,reports=dataset.locations(root)
    protocol=audit.digest((audit.hash_file(__file__)+audit.hash_file(reports/'manifestos_arquivos.json')).encode())
    out=root/'dados/processed/jurisprudencia/revisao'/protocol
    folder=root/'dados/relatorios/jurisprudencia/revisao'/protocol
    out.mkdir(parents=True,exist_ok=True); folder.mkdir(parents=True,exist_ok=True)
    provenance=json.loads((root/'dados/raw/jurisprudencia/origens_declaradas.json').read_text(encoding='utf-8'))
    audit_folder,_,_=load(root)
    inventory=json.loads((audit_folder/'inventario.json').read_text(encoding='utf-8'))
    quarantine=json.loads((reports/'quarentena_manifesto.json').read_text(encoding='utf-8'))
    bad_ids={q['arquivo_id'] for q in quarantine}
    diagnostics=[]
    for e in inventory:
        if e['arquivo_id'] in bad_ids:
            source=Path(e['caminho_original'])
            # O inventário mantém o caminho absoluto original; não procura homônimos.
            if not source.exists():
                raise FileNotFoundError('Caminho original ausente no inventário: '+str(e.keys()))
            if audit.hash_file(source)!=e['sha256']:raise ValueError('Fonte em quarentena mudou.')
            diagnostics.append(parquet_diagnostic(source))
    audit.write_json(folder/'diagnostico_quarentena.json',diagnostics)
    for m in json.loads((reports/'manifestos_arquivos.json').read_text(encoding='utf-8')):
        if audit.hash_file(root/m['saida'])!=m['saida_sha256']:raise ValueError('Shard canônico alterado.')
    columns=['registro_id','arquivo_id','tribunal','ramo_direito_origem','processo_cnj',
             'processo_original','texto_limpo_sha256','registro_original_sha256',
             'motivos_revisao','candidato_tecnico_indexacao','url_origem']
    components=Components(); seen={}; ids=[]; courts=[]; themes=[]; flags=[]; samples=defaultdict(list)
    counts=Counter(); domains=Counter(); strata=Counter(); review=Counter()
    for batch in dataset.open_dataset(root).scanner(columns=columns,batch_size=4096,use_threads=False).to_batches():
        for r in batch.to_pylist():
            i=components.add(); ids.append(r['registro_id']); court=r['tribunal'] or 'não identificado'; courts.append(court)
            thematic=theme(r['tribunal'],r['ramo_direito_origem']); themes.append(thematic)
            reasons=r['motivos_revisao'] or []
            privacy=any(x in reasons for x in ('campos_de_partes_ou_contato_na_origem','cpf_candidato_checksum_valido','email_candidato'))
            flags.append(privacy); counts['registros']+=1; counts['sinal_privacidade']+=privacy
            counts['sem_sinal_nao_equivale_anonimizado']+=not privacy
            strata[(court,thematic)]+=1; review.update(reasons)
            key,_=dataset.process_group_key(r['tribunal'],r['processo_cnj'],r['processo_original'])
            for kind,value in [('processo',key),('texto',r['texto_limpo_sha256']),('registro',r['registro_original_sha256'])]:
                if not value:continue
                token=(kind,value)
                if token in seen:components.union(i,seen[token])
                else:seen[token]=i
            if r['url_origem']:
                domains[(r['arquivo_id'],urlsplit(r['url_origem']).hostname or 'inválido')]+=1
            # Amostragem determinística por hash; o relatório não contém textos, nomes ou números de processo.
            key_sample=(court,'sinal_privacidade' if privacy else 'sem_sinal_detectado')
            samples[key_sample].append((r['registro_id'],r['arquivo_id']))
        if len(ids)%65536==0:print('Triagem:',len(ids),flush=True)
    expected=json.loads((reports/'resumo_estruturacao.json').read_text(encoding='utf-8'))['registros']
    if len(ids)!=expected or len(set(ids))!=expected:raise ValueError('Reconciliação ou unicidade falhou.')
    minima={}
    for i,rid in enumerate(ids):
        group=components.find(i)
        if group not in minima or rid<minima[group]:minima[group]=rid
    schema=pa.schema([('registro_id',pa.string()),('grupo_avaliacao',pa.string()),('split_proposto',pa.string()),
        ('triagem_tematica',pa.string()),('sinal_privacidade',pa.bool_()),('liberado_indexacao',pa.bool_())])
    splits=Counter(); cross=Counter(); group_sizes=Counter(); assignments={}
    with pq.ParquetWriter(out/'triagem_particoes.parquet',schema,compression='zstd') as writer:
        for start in range(0,len(ids),4096):
            rows=[]
            for i in range(start,min(start+4096,len(ids))):
                group=components.find(i); key=minima[group]; split=split_name(key)
                previous=assignments.setdefault(group,split)
                if previous!=split:raise ValueError('Componente atravessou splits.')
                group_sizes[group]+=1; splits[split]+=1; cross[(courts[i],split)]+=1
                rows.append(dict(registro_id=ids[i],grupo_avaliacao=key,split_proposto=split,
                    triagem_tematica=themes[i],sinal_privacidade=flags[i],liberado_indexacao=False))
            writer.write_table(pa.Table.from_pylist(rows,schema=schema))
    sample_rows=[]
    for (court,status),rows in sorted(samples.items()):
        for rid,file_id in sorted(rows)[:25]:
            sample_rows.append(dict(registro_id=rid,arquivo_id=file_id,tribunal=court,estrato=status,
                pertinencia_revisada='',privacidade_revisada='',decisao_revisor='',revisor='',justificativa=''))
    audit.write_csv(folder/'amostra_revisao.csv',sample_rows)
    audit.write_csv(folder/'tribunais_tema.csv',[dict(tribunal=c,triagem_tematica=t,registros=n) for (c,t),n in sorted(strata.items())])
    audit.write_csv(folder/'splits_tribunal.csv',[dict(tribunal=c,split_proposto=s,registros=n) for (c,s),n in sorted(cross.items())])
    audit.write_csv(folder/'dominios_declarados.csv',[dict(arquivo_id=f,dominio=d,registros=n) for (f,d),n in sorted(domains.items())])
    audit.write_csv(folder/'sinais_revisao.csv',[dict(motivo=k,registros=n) for k,n in sorted(review.items())])
    audit.write_csv(folder/'origens_a_confirmar.csv',[dict(arquivo_id=e['arquivo_id'],arquivo=e['arquivo'],
        sha256=e['sha256'],repositorio='',revisao_commit='',licenca='',url_fonte='',verificado_por='') for e in inventory])
    result={**dict(counts),'grupos_avaliacao':len(minima),'maior_grupo':max(group_sizes.values()),
        'splits_propostos':dict(splits),'grupos_atravessando_splits':0,'amostra_revisao':len(sample_rows),
        'arquivos_quarentena':len(diagnostics),'licencas_confirmadas':0,'anonimizacao_concluida':False,
        'indexacao_realizada':False,'liberados_indexacao':0,
        'criterio_split':'Componentes conexos de CNJ sintático/número antigo com namespace, hash de texto limpo e registro canônico; hash estável do menor ID do componente. Proposta 80/10/10 por grupos, sem garantia de proporção por linhas.',
        'limites':'Não cobre paráfrases, identidade jurídica não reconhecida ou variantes não ligadas. Não é avaliação temporal. Ausência de sinal não prova ausência de dados pessoais. Tribunal trabalhista não confirma pertinência de cada documento.',
        'base_manifesto_sha256':audit.hash_file(reports/'manifestos_arquivos.json'),
        'codigo_sha256':audit.hash_file(__file__),'indice_sha256':audit.hash_file(out/'triagem_particoes.parquet'),
        'plataforma_declarada':provenance.get('plataforma_parquets_informada')}
    audit.write_json(folder/'resumo_revisao.json',result)
    audit.write_json(root/'dados/relatorios/jurisprudencia/revisao/revisao_ativa.json',dict(pasta=str(folder.relative_to(root)),pasta_dados=str(out.relative_to(root))))
    return folder,result


def figures(folder,result):
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    axes[0].bar(['Com sinais','Sem sinais detectados'],[result['sinal_privacidade'],result['sem_sinal_nao_equivale_anonimizado']],color=['#cc9944','#4477aa'])
    axes[0].set_title('Triagem de privacidade — não é anonimização')
    s=result['splits_propostos'];axes[1].bar(list(s),list(s.values()),color='#4477aa')
    axes[1].set_title('Partição provisória por grupos relacionados')
    for ax in axes:
        ax.set_ylabel('Registros')
        for bar in ax.patches:ax.annotate(f'{int(bar.get_height()):,}',(bar.get_x()+bar.get_width()/2,bar.get_height()),ha='center',va='bottom',fontsize=9)
        ax.margins(y=.15)
    fig.tight_layout();fig.savefig(Path(folder)/'revisao_prontidao.png',dpi=140)
    return fig
