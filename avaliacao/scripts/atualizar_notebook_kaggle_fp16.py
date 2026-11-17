"""Atualiza o notebook portátil do Kaggle para cálculo em FP16 com salvaguardas e vários pacotes por sessão.

Decisão da pessoa usuária (16/11/2026), após benchmark na T4: FP16 com lote 32 (~47,7 chunks/s, ~15 h para
2,5 milhões de chunks) em vez de float32 (~10,7 chunks/s, ~65 h), com cosseno >= 0,999999 no teste.
Tolerância ajustada de 0,9999 para 0,9995 (16/11/2026), após uma parte real atingir 0,999865.
Salvaguardas: prova de compatibilidade com a legislação também em FP16 (cosseno >= 0,9995); em cada parte,
uma amostra de textos reais é recalculada em float32 e precisa atingir cosseno >= 0,9995. Os vetores são
renormalizados e gravados em float32. Uma cópia da versão anterior é preservada.
"""
from pathlib import Path
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
NB = ROOT / 'dados/output/kaggle/06_embeddings_gpu_kaggle.ipynb'

MODELO_MD = '''## Snapshot fixado e precisão

São utilizados os arquivos exatos do backbone já adotado em legislação: BGE-M3, saída densa, 1.024 dimensões e normalização L2. O modelo é baixado para `/tmp`, fora da pasta de resultados, e cada arquivo é confrontado com seu SHA-256 original. Os pesos permanecem em float32 e TF32 fica desabilitado.

**Precisão de cálculo:** por decisão registrada após o benchmark na T4, a produção usa **FP16 (autocast)**, cerca de 4,5 vezes mais rápido que float32, com cosseno mínimo de 0,999999 no teste. Os vetores são renormalizados e **gravados em float32**. A compatibilidade com a legislação é exigida também em FP16, e cada parte recalcula uma amostra em float32 como conferência.'''

COMPAT = r'''
TOLERANCIA_FP16=0.9995
def encode_vectors(texts,batch_size=32,fp16=True):
    """FP16 por autocast; saída renormalizada e gravada em float32."""
    with torch.autocast('cuda',dtype=torch.float16,enabled=fp16):
        v=model.encode(texts,batch_size=batch_size,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)
    v=np.asarray(v,dtype=np.float32)
    return v/np.linalg.norm(v,axis=1,keepdims=True)
for p in PROBES:
    assert text_sha(p['texto'])==p['sha256']
    assert model.tokenizer.encode(p['texto'],add_special_tokens=False,truncation=False,verbose=False)==p['tokens'], 'Tokenização incompatível.'
reference=np.frombuffer(base64.b64decode(PROBE_VECTORS_B64),dtype='<f4').reshape(3,1024)
actual=encode_vectors([p['texto'] for p in PROBES],fp16=False)
cosines=np.sum(reference*actual,axis=1);max_error=float(np.max(np.abs(reference-actual)))
assert np.isfinite(actual).all() and float(cosines.min())>=.99999 and max_error<=1e-4, 'Compatibilidade numérica não confirmada.'
actual16=encode_vectors([p['texto'] for p in PROBES],fp16=True)
cosines16=np.sum(reference*actual16,axis=1)
assert np.isfinite(actual16).all() and float(cosines16.min())>=TOLERANCIA_FP16, 'Compatibilidade em FP16 não confirmada.'
PROFILE=dict(modelo=MODEL,revisao=REVISION,arquivos_sha256=EXPECTED_FILES,dimensao=1024,dtype='float32',normalizacao_l2=True,
    precisao_calculo='fp16_autocast',armazenamento='float32_renormalizado',tolerancia_fp16=TOLERANCIA_FP16,
    device=DEVICE,gpu=torch.cuda.get_device_name(0),versoes=VERSIONS,cosine_min=float(cosines.min()),erro_max=max_error,
    cosine_min_fp16=float(cosines16.min()),erro_max_fp16=float(np.max(np.abs(reference-actual16))))
atomic_json(OUTPUT/'compatibilidade_gpu.json',PROFILE)
print('Compatibilidade float32:',float(cosines.min()),'erro máximo:',max_error)
print('Compatibilidade FP16:',float(cosines16.min()),'erro máximo:',PROFILE['erro_max_fp16'])
'''

PRODUCAO_MD = '''## Produção por pacotes — somente após validar o notebook 05

Os pacotes de jurisprudência devem ser adicionados como **Kaggle Dataset privado**. Não envie o repositório inteiro, `.env`, credenciais ou originais anteriores ao mascaramento. Cada pacote contém apenas `chunk_id`, `registro_id`, `texto` e `texto_sha256`, além do manifesto. O texto pode conter nomes; privado não significa anonimização integral.

Informe em `JOB_IDS` os pacotes desta sessão, em ordem, e habilite `EXECUTAR_PACOTE`. Eles são processados em sequência até `MAX_SECONDS` (11 h, com margem para salvar). Cada parte concluída vira um checkpoint. Se a sessão acabar, salve os outputs e anexe-os como Input da próxima sessão em `PREVIOUS_OUTPUT`: as partes já concluídas são conferidas e reaproveitadas.

Em cada parte, uma amostra de textos reais é recalculada em float32. Se o cosseno mínimo ficar abaixo de 0,9995, a execução para sem gravar a parte.'''

PRODUCAO = r'''
EXECUTAR_PACOTE=False
JOB_IDS=['job_0000']          # pacotes desta sessão, processados em sequência
BATCH_SIZE=32
MAX_SECONDS=11*3600           # margem para salvar antes do limite da sessão
AMOSTRA_FP32=8                # textos por parte recalculados em float32
PREVIOUS_OUTPUT=None          # Ex.: Path('/kaggle/input/meu-output-anterior/lexia_embeddings')
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
    started=time.monotonic();sem_tempo=False;sessao=[]
    manifestos={}
    for path in Path('/kaggle/input').rglob('manifesto_job.json'):
        candidate=json.loads(path.read_text(encoding='utf-8'));manifestos.setdefault(candidate.get('job_id'),[]).append((path,candidate))
    for JOB_ID in JOB_IDS:
        found=manifestos.get(JOB_ID,[])
        assert len(found)==1, 'Anexe exatamente um pacote correspondente a '+JOB_ID+'.'
        manifest_path,job=found[0];jobroot=manifest_path.parent
        assert job['corpus_validado'] is True and job['modelo_arquivos_sha256']==EXPECTED_FILES
        assert job['chunks_total']<=100000, 'Pacote maior que o limite desta configuração.'
        jobhash=sha_file(manifest_path);dest=OUTPUT/JOB_ID;dest.mkdir(parents=True,exist_ok=True);completed=[]
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
            if time.monotonic()-started>=MAX_SECONDS:sem_tempo=True;break
            unique={r['texto_sha256']:r['texto'] for r in rows};keys=list(unique);encoded={}
            for a in range(0,len(keys),BATCH_SIZE):
                if time.monotonic()-started>=MAX_SECONDS:sem_tempo=True;break
                kk=keys[a:a+BATCH_SIZE];texts=[unique[k] for k in kk]
                assert all(len(model.tokenizer.encode(t,add_special_tokens=True,truncation=False,verbose=False))<=502 for t in texts)
                vv=encode_vectors(texts,batch_size=BATCH_SIZE,fp16=True)
                for k,v in zip(kk,vv,strict=True):encoded[k]=v
            if sem_tempo:break # Apenas a parte aberta é refeita; checkpoints anteriores continuam válidos.
            amostra=keys[:AMOSTRA_FP32]
            ref32=encode_vectors([unique[k] for k in amostra],batch_size=BATCH_SIZE,fp16=False)
            cos_amostra=float(np.min(np.sum(ref32*np.stack([encoded[k] for k in amostra]),axis=1)))
            assert cos_amostra>=TOLERANCIA_FP16, f'Parte {label}: amostra FP16 diverge do float32 (cosseno {cos_amostra:.6f}).'
            vv=np.stack([encoded[r['texto_sha256']] for r in rows]);mapping=[]
            assert vv.shape==(len(rows),1024) and vv.dtype==np.float32 and np.isfinite(vv).all() and np.allclose(np.linalg.norm(vv,axis=1),1,atol=1e-4)
            for i,r in enumerate(rows):mapping.append(dict(row_index=i,chunk_id=r['chunk_id'],registro_id=r['registro_id'],texto_sha256=r['texto_sha256'],vector_sha256=hashlib.sha256(np.asarray(vv[i],dtype='<f4').tobytes()).hexdigest()))
            vf=dest/('vetores_'+label+'.npy');mf=dest/('mapeamento_'+label+'.parquet')
            vt=vf.with_suffix('.partial.npy');np.save(vt,vv,allow_pickle=False);vt.replace(vf)
            mt=mf.with_suffix('.partial.parquet');pq.write_table(pa.Table.from_pylist(mapping),mt,compression='zstd');mt.replace(mf)
            cp=dict(job_sha256=jobhash,entrada_sha256=part['sha256'],parte_id=label,chunks=len(rows),
                vetores_arquivo=vf.name,vetores_sha256=sha_file(vf),mapeamento_arquivo=mf.name,mapeamento_sha256=sha_file(mf),
                precisao_calculo='fp16_autocast',armazenamento='float32_renormalizado',amostra_fp32=len(amostra),cosseno_min_amostra_fp32=cos_amostra)
            verify_output(rows,dest,cp);atomic_json(cpfile,cp);completed.append(cp)
            print(JOB_ID,'| parte concluída:',label,len(rows),'chunks | cosseno amostra float32:',round(cos_amostra,6),flush=True)
        total=sum(c['chunks'] for c in completed)
        status='job_concluido' if total==job['chunks_total'] else 'job_parcial'
        atomic_json(dest/'resultado_job.json',dict(status=status,job_id=JOB_ID,job_sha256=jobhash,chunks_concluidos=total,
            chunks_esperados=job['chunks_total'],perfil=PROFILE,partes=completed))
        sessao.append(dict(job_id=JOB_ID,status=status,chunks_concluidos=total,chunks_esperados=job['chunks_total']))
        print(JOB_ID,'|',status,'|',total,'/',job['chunks_total'],'chunks',flush=True)
        if sem_tempo:break
    atomic_json(OUTPUT/'resumo_sessao.json',dict(jobs=sessao,segundos=time.monotonic()-started,limite_atingido=sem_tempo))
    print('Sessão:',sessao,'| tempo esgotado:' if sem_tempo else '| concluída em',round((time.monotonic()-started)/3600,2),'h')
else:
    print('Somente configuração e benchmark. Nenhum corpus de jurisprudência foi vetorizado.')
'''


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    copia = NB.with_name(NB.stem + '_float32.ipynb')
    if not copia.exists():
        shutil.copyfile(NB, copia)
    nb = json.loads(NB.read_text(encoding='utf-8'))
    novos = {'kg_model_text': MODELO_MD, 'kg_compat': COMPAT, 'kg_production_text': PRODUCAO_MD, 'kg_production': PRODUCAO}
    for c in nb['cells']:
        if c['id'] in novos:
            c['source'] = novos[c['id']].strip().splitlines(keepends=True)
            if c['cell_type'] == 'code':
                c['outputs'], c['execution_count'] = [], None
    for c in nb['cells']:
        if c['cell_type'] == 'code':
            compile(''.join(c['source']), c['id'], 'exec')
    NB.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('Notebook atualizado:', NB, '| versão anterior:', copia.name)


if __name__ == '__main__':
    main()
