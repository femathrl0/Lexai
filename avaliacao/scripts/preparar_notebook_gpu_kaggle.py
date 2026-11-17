"""Gera notebook portátil de configuração/embeddings, sem credenciais ou banco local."""
from pathlib import Path
import base64,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from worker.ingestao.jurisprudencia import audit,chunking_definitivo as chunks
from worker.ingestao.jurisprudencia.notebook_preservation import save_notebook


def main():
    from transformers import AutoTokenizer
    folder=ROOT/'dados/output/kaggle';folder.mkdir(parents=True,exist_ok=True)
    path=folder/'06_embeddings_gpu_kaggle.ipynb'
    if path.exists():raise RuntimeError('Notebook portátil já existe; preserve suas edições.')
    preflight=json.loads((ROOT/'dados/relatorios/jurisprudencia/embeddings/preflight.json').read_text(encoding='utf-8'))
    old=json.loads((ROOT/'dados/relatorios/legislacao/pgvector/D_paragrafo_completo/manifesto_importacao.json').read_text(encoding='utf-8'))
    source=ROOT/'dados/chunks/legislacao/chunks_D_paragrafo_completo.json';vectorspath=ROOT/'indexes/legislacao/embeddings'/(old['cache_key']+'.npy')
    assert audit.hash_file(source)==old['chunks_sha256'] and audit.hash_file(vectorspath)==old['vectors_sha256']
    records=json.loads(source.read_text(encoding='utf-8'));v=np.load(vectorspath,mmap_mode='r',allow_pickle=False)
    tok=AutoTokenizer.from_pretrained(preflight['backbone']['modelo'],revision=preflight['backbone']['revisao'],local_files_only=True,use_fast=True)
    probes=[];selected=[]
    for i,r in enumerate(records):
        ids=tok.encode(r['conteudo_chunk'],add_special_tokens=False,truncation=False,verbose=False)
        if 8<=len(ids)<=80:
            probes.append(dict(texto=r['conteudo_chunk'],tokens=ids,sha256=chunks.base.sha(r['conteudo_chunk'])))
            selected.append(i)
        if len(probes)==3:break
    encoded=base64.b64encode(np.asarray(v[selected],dtype='<f4').tobytes()).decode()
    cells=[]
    def add(kind,ident,text):
        c=dict(cell_type=kind,id=ident,metadata={},source=text.strip().splitlines(keepends=True))
        if kind=='code':c.update(execution_count=None,outputs=[])
        cells.append(c)
    add('markdown','kg_intro','''# LexIA — Jurisprudência — BGE-M3 na GPU do Kaggle

Notebook privado para configurar a GPU, comprovar compatibilidade com legislação e gerar embeddings de lotes validados. Nesta primeira execução, rode até o benchmark: nenhum documento de jurisprudência é necessário para configurar a GPU.

**Configuração no Kaggle:** GPU disponível em Settings → Accelerator, Internet habilitada para baixar o snapshot oficial do modelo e notebook privado. Se Accelerator estiver desabilitado, conclua pessoalmente a verificação da conta. Não coloque senha, token de API ou conexão do PostgreSQL neste notebook.

A produção exige o notebook 05 concluído e pacotes privados exportados dessa versão. Os resultados serão baixados para validação e indexação local no pgvector; não se expõe o banco do computador à Internet.''')
    add('code','kg_gpu',r'''
import os,sys,json,hashlib,time,base64,subprocess,importlib.util
from pathlib import Path
import numpy as np
import torch
assert torch.cuda.is_available(), 'GPU não habilitada: verifique a conta e Settings → Accelerator.'
DEVICE='cuda:0'
print('PyTorch:',torch.__version__)
print('GPUs disponíveis:',torch.cuda.device_count())
for i in range(torch.cuda.device_count()):print(i,torch.cuda.get_device_name(i))
print('Esta execução usa somente',DEVICE,'; T4 x2 não significa uso automático das duas GPUs.')
torch.backends.cuda.matmul.allow_tf32=False
torch.backends.cudnn.allow_tf32=False
''')
    add('markdown','kg_packages_text','''## Dependências

Preserve o PyTorch com CUDA fornecido pelo Kaggle. A célula instala somente dependências ausentes pelo pip; não instala uma versão CPU do PyTorch. As versões efetivas são registradas para reproduzir a execução.''')
    add('code','kg_packages',r'''
required={'sentence_transformers':'sentence-transformers','huggingface_hub':'huggingface-hub','pyarrow':'pyarrow'}
missing=[package for module,package in required.items() if importlib.util.find_spec(module) is None]
if missing:subprocess.check_call([sys.executable,'-m','pip','install','-q',*missing])
from importlib.metadata import version
from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer
import pyarrow as pa
import pyarrow.parquet as pq
VERSIONS={name:version(name) for name in ['torch','numpy','transformers','sentence-transformers','huggingface-hub','pyarrow']}
print(VERSIONS)
assert torch.cuda.is_available(), 'O ambiente deixou de disponibilizar CUDA.'
''')
    add('markdown','kg_model_text','''## Snapshot fixado e precisão

São utilizados os arquivos exatos do backbone já adotado em legislação: BGE-M3, saída densa, 1.024 dimensões, float32 e normalização L2. O modelo é baixado para `/tmp`, fora da pasta de resultados, e cada arquivo é confrontado com seu SHA-256 original. Não se habilita FP16, quantização ou TF32 nesta configuração inicial.''')
    setup='''MODEL='BAAI/bge-m3'
REVISION='5617a9f61b028005a4858fdac845db406aefb181'
EXPECTED_FILES='''+repr(preflight['backbone']['arquivos_sha256'])+'''
PROBES='''+repr(probes)+'''
PROBE_VECTORS_B64='''+repr(encoded)+'''
def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def text_sha(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()
def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.partial.json');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
snapshot=Path(snapshot_download(MODEL,revision=REVISION,allow_patterns=list(EXPECTED_FILES),cache_dir='/tmp/lexia_hf'))
for name,digest in EXPECTED_FILES.items():assert sha_file(snapshot/name)==digest, 'Arquivo do modelo divergente: '+name
model=SentenceTransformer(str(snapshot),device=DEVICE,local_files_only=True)
model.float();model.max_seq_length=8192
assert model.get_embedding_dimension()==1024
assert all(p.dtype==torch.float32 for p in model.parameters() if p.is_floating_point())
OUTPUT=Path('/kaggle/working/lexia_embeddings');OUTPUT.mkdir(parents=True,exist_ok=True)
print('Backbone verificado; dimensão 1024; precisão float32.')
'''
    add('code','kg_model',setup)
    add('markdown','kg_compat_text','''## Compatibilidade numérica com legislação

Três pequenos textos normativos e seus vetores originais são usados somente como prova técnica. O teste confronta os IDs de tokens e os embeddings da GPU, com tolerância explícita; não regrava nenhum artefato de legislação.''')
    add('code','kg_compat',r'''
for p in PROBES:
    assert text_sha(p['texto'])==p['sha256']
    assert model.tokenizer.encode(p['texto'],add_special_tokens=False,truncation=False,verbose=False)==p['tokens'], 'Tokenização incompatível.'
reference=np.frombuffer(base64.b64decode(PROBE_VECTORS_B64),dtype='<f4').reshape(3,1024)
actual=np.asarray(model.encode([p['texto'] for p in PROBES],normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False),dtype=np.float32)
cosines=np.sum(reference*actual,axis=1);max_error=float(np.max(np.abs(reference-actual)))
assert np.isfinite(actual).all() and float(cosines.min())>=.99999 and max_error<=1e-4, 'Compatibilidade numérica não confirmada.'
PROFILE=dict(modelo=MODEL,revisao=REVISION,arquivos_sha256=EXPECTED_FILES,dimensao=1024,dtype='float32',normalizacao_l2=True,
    device=DEVICE,gpu=torch.cuda.get_device_name(0),versoes=VERSIONS,cosine_min=float(cosines.min()),erro_max=max_error)
atomic_json(OUTPUT/'compatibilidade_gpu.json',PROFILE)
print('Compatibilidade aprovada:',float(cosines.min()),'erro máximo:',max_error)
''')
    add('markdown','kg_benchmark_text','''## Benchmark técnico e dimensionamento

O teste usa oito textos artificiais de 500 tokens e mede custo, não qualidade jurídica. Use a velocidade observada para planejar os lotes dentro da quota exibida pela sua conta. O lote inicial é pequeno; mantenha esta configuração antes de explorar outras precisões ou múltiplas GPUs.''')
    add('code','kg_benchmark',r'''
synthetic='Texto artificial para medição de tempo. Não representa decisão judicial. '*500
offsets=model.tokenizer(synthetic,add_special_tokens=False,return_offsets_mapping=True,verbose=False)['offset_mapping']
samples=[synthetic[:offsets[499][1]] for _ in range(8)]
torch.cuda.synchronize();started=time.monotonic()
test=model.encode(samples,batch_size=8,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)
torch.cuda.synchronize();elapsed=time.monotonic()-started
BENCHMARK=dict(entradas=8,tokens_por_entrada=500,segundos=elapsed,chunks_por_segundo=8/elapsed,
    horas_por_milhao=elapsed/8*1_000_000/3600,amostra='artificial; não é previsão garantida nem métrica jurídica')
atomic_json(OUTPUT/'benchmark_gpu.json',BENCHMARK)
print(BENCHMARK)
''')
    add('markdown','kg_production_text','''## Produção por pacotes — somente após validar o notebook 05

Os pacotes de jurisprudência devem ser adicionados como **Kaggle Dataset privado**. Não envie o repositório inteiro, `.env`, credenciais ou originais anteriores ao mascaramento. Cada pacote contém apenas os chunks necessários e seu manifesto. O corpo dos documentos pode conter nomes; privado não significa anonimização integral.

O seletor fica desativado durante a configuração. Ao anexar um pacote validado, informe o identificador e habilite a execução. O limite padrão é de duas horas; os arquivos fechados viram checkpoints. Se a sessão acabar, salve os outputs e anexe-os como entrada na próxima sessão para retomar. Não dependa apenas do estado da sessão interativa.''')
    add('code','kg_production',r'''
EXECUTAR_PACOTE=False
JOB_ID='job_0000'
BATCH_SIZE=16
MAX_SECONDS=2*3600
PREVIOUS_OUTPUT=None # Ex.: Path('/kaggle/input/meu-output-anterior/lexia_embeddings')
def safe_child(root,relative):
    root=Path(root).resolve();target=(root/relative).resolve()
    assert target.is_relative_to(root), 'Caminho fora do pacote.'
    return target
def verify_output(input_rows,folder,cp):
    vf=safe_child(folder,cp['vetores_arquivo']);mf=safe_child(folder,cp['mapeamento_arquivo'])
    assert sha_file(vf)==cp['vetores_sha256'] and sha_file(mf)==cp['mapeamento_sha256']
    vv=np.load(vf,allow_pickle=False);mm=pq.read_table(mf).to_pylist()
    assert vv.shape==(len(input_rows),1024) and vv.dtype==np.float32 and np.isfinite(vv).all()
    assert np.allclose(np.linalg.norm(vv,axis=1),1,atol=1e-4) and len(mm)==len(input_rows)
    for i,(r,m) in enumerate(zip(input_rows,mm,strict=True)):
        assert m['row_index']==i and m['chunk_id']==r['chunk_id'] and m['registro_id']==r['registro_id']
        assert m['texto_sha256']==r['texto_sha256'] and m['vector_sha256']==hashlib.sha256(np.asarray(vv[i],dtype='<f4').tobytes()).hexdigest()
if EXECUTAR_PACOTE:
    import shutil
    found=[]
    for path in Path('/kaggle/input').rglob('manifesto_job.json'):
        candidate=json.loads(path.read_text(encoding='utf-8'))
        if candidate.get('job_id')==JOB_ID:found.append((path,candidate))
    assert len(found)==1, 'Anexe exatamente um pacote correspondente ao JOB_ID.'
    manifest_path,job=found[0];jobroot=manifest_path.parent
    assert job['corpus_validado'] is True and job['modelo_arquivos_sha256']==EXPECTED_FILES
    assert job['chunks_total']<=100000, 'Pacote maior que o limite desta configuração.'
    jobhash=sha_file(manifest_path);dest=OUTPUT/JOB_ID;dest.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();completed=[]
    for part in job['partes']:
        inp=safe_child(jobroot,part['arquivo']);assert sha_file(inp)==part['sha256']
        rows=pq.read_table(inp).to_pylist();assert len(rows)==part['chunks']
        for r in rows:assert text_sha(r['texto'])==r['texto_sha256']
        label=part['parte_id'];cpfile=dest/('checkpoint_'+label+'.json')
        prior=Path(PREVIOUS_OUTPUT)/JOB_ID if PREVIOUS_OUTPUT else None
        if not cpfile.exists() and prior and (prior/cpfile.name).exists():
            cp=json.loads((prior/cpfile.name).read_text(encoding='utf-8'))
            assert cp['job_sha256']==jobhash and cp['entrada_sha256']==part['sha256']
            verify_output(rows,prior,cp)
            for name in (cp['vetores_arquivo'],cp['mapeamento_arquivo'],cpfile.name):shutil.copy2(safe_child(prior,name),dest/name)
        if cpfile.exists():
            cp=json.loads(cpfile.read_text(encoding='utf-8'))
            assert cp['job_sha256']==jobhash and cp['entrada_sha256']==part['sha256']
            verify_output(rows,dest,cp);completed.append(cp);continue
        if time.monotonic()-started>=MAX_SECONDS:break
        unique={r['texto_sha256']:r['texto'] for r in rows};keys=list(unique);encoded={};interrupted=False
        for a in range(0,len(keys),BATCH_SIZE):
            if time.monotonic()-started>=MAX_SECONDS:interrupted=True;break
            kk=keys[a:a+BATCH_SIZE];texts=[unique[k] for k in kk]
            assert all(len(model.tokenizer.encode(t,add_special_tokens=True,truncation=False,verbose=False))<=502 for t in texts)
            vv=np.asarray(model.encode(texts,batch_size=BATCH_SIZE,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False),dtype=np.float32)
            for k,v in zip(kk,vv,strict=True):encoded[k]=v
        if interrupted:break # Apenas a parte aberta é refeita; checkpoints anteriores continuam válidos.
        vv=np.stack([encoded[r['texto_sha256']] for r in rows]);mapping=[]
        assert vv.shape==(len(rows),1024) and np.isfinite(vv).all() and np.allclose(np.linalg.norm(vv,axis=1),1,atol=1e-4)
        for i,r in enumerate(rows):mapping.append(dict(row_index=i,chunk_id=r['chunk_id'],registro_id=r['registro_id'],texto_sha256=r['texto_sha256'],vector_sha256=hashlib.sha256(np.asarray(vv[i],dtype='<f4').tobytes()).hexdigest()))
        vf=dest/('vetores_'+label+'.npy');mf=dest/('mapeamento_'+label+'.parquet')
        vt=vf.with_suffix('.partial.npy');np.save(vt,vv,allow_pickle=False);vt.replace(vf)
        mt=mf.with_suffix('.partial.parquet');pq.write_table(pa.Table.from_pylist(mapping),mt,compression='zstd');mt.replace(mf)
        cp=dict(job_sha256=jobhash,entrada_sha256=part['sha256'],parte_id=label,chunks=len(rows),
            vetores_arquivo=vf.name,vetores_sha256=sha_file(vf),mapeamento_arquivo=mf.name,mapeamento_sha256=sha_file(mf))
        verify_output(rows,dest,cp);atomic_json(cpfile,cp);completed.append(cp)
        print('Parte concluída:',label,len(rows),'chunks')
    total=sum(c['chunks'] for c in completed)
    atomic_json(dest/'resultado_job.json',dict(status='job_concluido' if total==job['chunks_total'] else 'job_parcial',
        job_id=JOB_ID,job_sha256=jobhash,chunks_concluidos=total,chunks_esperados=job['chunks_total'],perfil=PROFILE,partes=completed))
    print('Chunks concluídos:',total,'/',job['chunks_total'])
else:
    print('Somente configuração e benchmark. Nenhum corpus de jurisprudência foi vetorizado.')
''')
    add('markdown','kg_finish','''## Salvar a versão e os arquivos

Use **Save Version → Save & Run All**, mantendo o notebook privado, e confira os arquivos em Output. Preserve `compatibilidade_gpu.json`, `benchmark_gpu.json` e a pasta do job. Baixe os resultados ou anexe o output salvo como Input para uma retomada; arquivos temporários do modelo não entram nos resultados.

O limite deste notebook é 100 mil chunks por pacote: aproximadamente 410 MB de vetores float32, mais mapeamentos. A base inteira ultrapassa a capacidade de saída de uma única execução; processe e salve os pacotes separadamente. A importação final no pgvector será feita no computador após conferir hashes, contagens e compatibilidade de todos os resultados.''')
    book=dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3'),language_info=dict(name='python'),
        kaggle=dict(isGpuEnabled=False,isInternetEnabled=True,language='python',sourceType='notebook')),
        nbformat=4,nbformat_minor=5)
    save_notebook(path,book)
    for c in cells:
        if c['cell_type']=='code':compile(''.join(c['source']),c['id'],'exec')
    audit.write_json(folder/'manifesto_configuracao.json',dict(notebook=path.name,sha256=audit.hash_file(path),provas=3,
        modelo=preflight['backbone']['modelo'],revisao=preflight['backbone']['revisao'],inclui_jurisprudencia=False,inclui_credenciais=False))
    print(path)

if __name__=='__main__':main()
