"""Preserva a edição atual dos notebooks ao atualizar código ou saídas."""
from pathlib import Path
from datetime import datetime,timezone
import copy,hashlib,json,time,uuid

NAMES=(
    '01_auditoria_jurisprudencia.ipynb','02_eda_jurisprudencia.ipynb',
    '03_limpeza_estruturacao_jurisprudencia.ipynb','04_revisao_prontidao_jurisprudencia.ipynb',
    '05_origens_recuperacao_jurisprudencia.ipynb')


def sha(data):return hashlib.sha256(data).hexdigest()


def snapshot(root):
    """Copia os cinco arquivos byte a byte, sem reserializar ou executar células."""
    root=Path(root).resolve();directory=root/'notebooks/02_jurisprudencia'
    from .notebook_integration import source_path,PREFIXES
    paths={name:source_path(root,name) for name in NAMES}
    # Notebooks arquivados no histórico de integração são opcionais (não versionados no repositório).
    paths={name:p for name,p in paths.items() if name not in PREFIXES or p.exists()}
    originals={name:paths[name].read_bytes() for name in paths}
    aggregate=sha(''.join(name+sha(data) for name,data in originals.items()).encode())
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target=root/'dados/relatorios/jurisprudencia/versoes_notebooks'/(stamp+'_'+aggregate[:12])
    target.mkdir(parents=True,exist_ok=False)
    entries=[]
    for name,data in originals.items():
        nb=json.loads(data.decode('utf-8-sig'));destination=target/name
        destination.write_bytes(data)
        if sha(destination.read_bytes())!=sha(data):raise ValueError('Cópia divergente.')
        entries.append(dict(arquivo=name,origem=str(paths[name].relative_to(root)),
            copia=str(destination.relative_to(root)),sha256=sha(data),bytes=len(data),
            celulas_markdown=[dict(posicao=i,id=c.get('id'),source_sha256=sha(json.dumps(c.get('source',[]),ensure_ascii=False).encode()))
                for i,c in enumerate(nb['cells']) if c['cell_type']=='markdown']))
    manifest=dict(criado_em_utc=datetime.now(timezone.utc).isoformat(),tipo='copia_integral_sem_alteracao',
        hash_conjunto=aggregate,arquivos=entries)
    (target/'manifesto.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Não considerar uma captura completa se houve edição concorrente.
    if any(paths[name].read_bytes()!=data for name,data in originals.items()):
        raise RuntimeError('Um notebook foi alterado durante a captura; capture novamente a versão mais recente.')
    return target,manifest


def merge_current(current,generated,mode='generation',allow_new_cell_ids=()):
    if mode not in ('generation','execution'):raise ValueError('Modo inválido.')
    result=copy.deepcopy(current)
    generated_codes=[c for c in generated['cells'] if c['cell_type']=='code']
    if len({c.get('id') for c in generated_codes})!=len(generated_codes):raise ValueError('IDs de código gerados repetidos.')
    proposed={c.get('id'):c for c in generated_codes}
    for c in result['cells']:
        # Markdown, células próprias, ordem e metadados locais são autoritativos.
        if c['cell_type']!='code' or c.get('id') not in proposed:continue
        new=proposed[c['id']]
        if mode=='generation':
            if c.get('source')!=new.get('source'):
                c['source']=copy.deepcopy(new['source']);c['execution_count']=None;c['outputs']=[]
        elif c.get('source')==new.get('source'):
            # Não atribuir resultados antigos a código editado durante a execução.
            c['execution_count']=new.get('execution_count');c['outputs']=copy.deepcopy(new.get('outputs',[]))
        else:raise RuntimeError('Código editado durante a execução; resultados antigos não serão atribuídos à nova versão.')
    allowed=set(allow_new_cell_ids);existing={c.get('id') for c in result['cells']}
    for position,new in enumerate(generated['cells']):
        if new.get('id') not in allowed or new.get('id') in existing:continue
        anchor=next((p.get('id') for p in reversed(generated['cells'][:position]) if p.get('id') in existing),None)
        insert=next((i+1 for i,c in enumerate(result['cells']) if c.get('id')==anchor),len(result['cells']))
        result['cells'].insert(insert,copy.deepcopy(new));existing.add(new.get('id'))
    return result


def save_notebook(path,generated,mode='generation',allow_new_cell_ids=(),integration_source_sha256=None,editorial_source_sha256=None):
    path=Path(path).resolve()
    protected=(path.name in NAMES or path.name in ('04_experimentos_chunking_jurisprudencia.ipynb','05_chunking_definitivo_jurisprudencia.ipynb','06_embeddings_indexacao_jurisprudencia.ipynb')) and path.parent.name=='02_jurisprudencia'
    original=path.read_bytes() if path.exists() else None
    current=json.loads(original.decode('utf-8-sig')) if original is not None else None
    if editorial_source_sha256 is not None:
        if not protected or path.name!='04_experimentos_chunking_jurisprudencia.ipynb' or original is None or sha(original)!=editorial_source_sha256:
            raise ValueError('A reformulação editorial exige o hash exato do notebook de chunking atual.')
        # Somente para reformulação integral explicitamente solicitada, com backup abaixo.
        result=generated
    elif integration_source_sha256 is not None:
        if not protected or path.name!=NAMES[2] or original is None or sha(original)!=integration_source_sha256:
            raise ValueError('A integração exige o hash exato da versão atual do notebook 03.')
        result=generated
    else:result=merge_current(current,generated,mode,allow_new_cell_ids) if protected and current is not None else generated
    if current==result:return False  # Preservação byte a byte inclusive da formatação JSON.
    if protected and original is not None:
        root=path.parent.parent.parent
        backup=root/'dados/relatorios/jurisprudencia/versoes_notebooks/automaticas'/sha(original)
        backup.mkdir(parents=True,exist_ok=True)
        saved=backup/path.name
        if not saved.exists():saved.write_bytes(original)
        if sha(saved.read_bytes())!=sha(original):raise ValueError('Backup automático divergente.')
    # Evita sobrescrever uma alteração feita no editor durante a preparação do salvamento.
    if original is not None and path.read_bytes()!=original:raise RuntimeError('Arquivo alterado durante o salvamento; tente novamente.')
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.preservacao.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for attempt in range(20):
        if original is not None and path.read_bytes()!=original:
            temp.unlink(missing_ok=True)
            raise RuntimeError('Arquivo editado durante o salvamento; a versão atual foi preservada.')
        try:temp.replace(path);return True
        except PermissionError:
            if attempt==19:raise
            time.sleep(.5)
