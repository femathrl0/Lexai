"""Encadeamento autorizado: só avança após a auditoria do 05 e definição do recurso."""
from pathlib import Path
import json,shutil,subprocess,time
from urllib.parse import urlsplit
from . import chunking_definitivo as chunks,chunking_definitivo_relatorio as panel


POLICY='dados/relatorios/jurisprudencia/embeddings/politica_execucao.json'


def input_ready(root,identity):
    state=panel.load(root)
    if state['identity']!=identity:raise ValueError('O corpus ativo mudou; encadeamento não será transferido silenciosamente.')
    verified=state['report']/'verificacao_notebook_05.json'
    return (state['report']/'concluido.json').exists() and verified.exists() and json.loads(verified.read_text(encoding='utf-8')).get('corpus_completo') is True


def ensure_database(root):
    from .embeddings_backbone import database_preflight
    result=database_preflight(root)
    if result['disponivel']:return result
    from worker.evidencia.indices.pgvector_store import load_database_url
    try:
        parsed=urlsplit(load_database_url(Path(root)/'.env.pgvector.local'))
        if parsed.hostname not in ('localhost','127.0.0.1','::1') or parsed.port!=15432 or not shutil.which('docker'):
            return result
        # Reutiliza o serviço e volume existentes; não baixa imagens nem remove dados.
        completed=subprocess.run(['docker','compose','--env-file','.env.pgvector.local','-f','compose.pgvector.yaml','up','-d','--pull','never'],
            cwd=root,capture_output=True,timeout=120)
        if completed.returncode:return result
        for _ in range(5):
            result=database_preflight(root)
            if result['disponivel']:return result
            time.sleep(3)
    except Exception:return dict(disponivel=False,observacao='Falha técnica sem exposição de credenciais.')
    return result


def run(root,watch_policy=False):
    root=Path(root);path=root/POLICY
    policy=json.loads(path.read_text(encoding='utf-8'))
    if not input_ready(root,policy['corpus_chunking']):raise ValueError('Notebook 05 ainda não concluiu a auditoria e a atualização final.')
    output=root/'dados/relatorios/jurisprudencia/embeddings/encadeamento.json'
    while policy['estado'] in ('aguardando_escolha_recurso','aguardando_ambiente_gpu'):
        chunks.atomic_json(output,dict(estado='notebook_05_concluido_aguardando_recurso',geracao_embeddings_iniciada=False,
            motivo=policy.get('espera','Aguardar definição do recurso computacional.')))
        if not watch_policy:return
        time.sleep(30);policy=json.loads(path.read_text(encoding='utf-8'))
    if policy['estado']!='autorizado' or policy.get('device') not in ('cpu','cuda'):
        raise ValueError('Política de recurso não habilita geração em escala neste ambiente.')
    if not input_ready(root,policy['corpus_chunking']):raise ValueError('Mudança de corpus antes do início da próxima etapa.')
    chunks.atomic_json(output,dict(estado='embeddings_iniciados',device=policy['device'],corpus_chunking=policy['corpus_chunking']))
    from . import embeddings_definitivos as embeddings
    from worker.evidencia.indices.jurisprudencia_pgvector import import_verified
    try:
        state,result=embeddings.run(root,device=policy['device'])
        db=ensure_database(root)
        if db['disponivel']:
            result=import_verified(state)
            chunks.atomic_json(output,dict(estado='etapa_06_concluida',resultado=result))
        else:
            chunks.atomic_json(output,dict(estado='embeddings_concluidos_banco_indisponivel',resultado=result,
                observacao='Vetores e checkpoints preservados. Importação no pgvector requer disponibilidade da conexão já configurada.'))
    except Exception as e:
        chunks.atomic_json(output,dict(estado='etapa_06_interrompida_retomavel',erro_tipo=type(e).__name__,
            observacao='Cache e lotes preservados; detalhes de conexão não são registrados.'))
        raise RuntimeError('Etapa 06 interrompida; tipo='+type(e).__name__) from None
    finally:
        subprocess.run([str(root/'.venv/Scripts/python.exe'),str(root/'scripts/run_notebook_06_jurisprudencia.py')],cwd=root,check=False)
