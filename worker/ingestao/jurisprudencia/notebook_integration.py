"""Integração editorial explícita, com origem de cada célula e arquivos históricos."""
from pathlib import Path
import copy,json,re
from .notebook_preservation import NAMES,sha,save_notebook

TARGET=NAMES[2]
PREFIXES={NAMES[3]:'rev04_',NAMES[4]:'ori05_'}
ANCHORS={NAMES[3]:'verificacao-automatica',NAMES[4]:'fontes-proveniencia'}


def load_state(root):
    root=Path(root).resolve();path=root/'notebooks/02_jurisprudencia/integracao.json'
    if not path.exists():return None
    state=json.loads(path.read_text(encoding='utf-8'))
    if state.get('destino')!=TARGET or state.get('estado')!='concluido':raise ValueError('Estado de integração inválido.')
    directory=root/'notebooks/02_jurisprudencia'
    for name in PREFIXES:
        archive=(root/state['historico'][name]).resolve()
        if not archive.is_relative_to(directory/'historico') or archive.name!=name:raise ValueError('Arquivo histórico fora do local permitido.')
    return state


def source_path(root,name):
    root=Path(root).resolve();state=load_state(root)
    return root/state['historico'][name] if state and name in PREFIXES else root/'notebooks/02_jurisprudencia'/name


def rewrite_references(text,current_name=TARGET):
    for name,anchor in ANCHORS.items():
        href=('#'+anchor) if current_name==TARGET else TARGET+'#'+anchor
        pattern=r'\[([^\]]+)\]\((?:\./)?'+re.escape(name)+r'(?:#[^)]*)?\)'
        def replace(m):
            label=re.sub(r'^(?:04|05)\s*[—–-]\s*','',m[1])
            return '['+label+']('+href+')'
        text=re.sub(pattern,replace,text)
    text=re.sub(r'\bnotebook\s+0?4\b','seção de verificação automática',text,flags=re.I)
    text=re.sub(r'\bnotebook\s+0?5\b','seção de fontes e proveniência',text,flags=re.I)
    return text


def output_text(root,text,current_name):
    return rewrite_references(text,current_name) if load_state(root) else text


def rename_heading(source,number=None,level=2,title=None):
    text=''.join(source) if isinstance(source,list) else source
    lines=text.splitlines(keepends=True)
    index=next((i for i,s in enumerate(lines) if re.match(r'^#{1,6}\s',s)),None)
    if index is not None:
        old=re.sub(r'^#{1,6}\s+','',lines[index].rstrip('\r\n'))
        old=re.sub(r'^\d+(?:\.\d+)*\s*[.—–-]?\s*','',old)
        lines[index]='#'*level+' '+((str(number)+'. ') if number is not None else '')+(title or old)+'\n'
    elif title:lines.insert(0,'#'*level+' '+title+'\n\n')
    return rewrite_references(''.join(lines)).splitlines(keepends=True)


def compose(books):
    result=copy.deepcopy(books[TARGET]);cells=[];trace=[]
    split=next(i for i,c in enumerate(result['cells']) if c.get('id')=='quarentena_texto_estrutura')
    headings={
        'intro_estrutura':(None,1,'03 — Limpeza, estruturação e verificação automática da jurisprudência'),
        'contrato_texto_estrutura':('1',2,None),'regras_texto_estrutura':('2',2,None),
        'protecao_dados_pessoais_texto':('3',2,None),'pln_leve_texto_estrutura':('4',2,None),
        'quarentena_texto_estrutura':('7',2,None),'validacao_texto_estrutura':('8',2,None),
        'graficos_texto_estrutura':('9',2,None),'verificacao_automatica_estrutura_texto':('10',2,None),
        'conclusao_texto_estrutura':('11',2,None),
        'intro_origens':('5',2,'Fontes, proveniência e integridade dos arquivos'),
        'licenca_origens_texto':('5.1',3,None),'recuperacao_origens_texto':('5.2',3,None),
        'fontes_oficiais_texto_origens':('5.3',3,None),'conclusao_origens':('5.4',3,None),
        'intro_revisao':('6',2,'Verificação automática e prontidão da base'),
        'recorte_texto':('6.1',3,None),'conteudo_texto':('6.2',3,None),
        'qualidade_texto':('6.3',3,None),'relacoes_texto':('6.4',3,None),
        'fontes_texto':('6.5',3,None),'conclusao_texto':('6.6',3,None)}
    def add(cell,name):
        original=copy.deepcopy(cell);c=copy.deepcopy(cell);old_id=c['id']
        c['id']=PREFIXES.get(name,'')+old_id
        if len(c['id'])>64:c['id']=c['id'][:52]+'_'+sha(c['id'].encode())[:10]
        c.setdefault('metadata',{})['lexia_integracao']=dict(notebook_origem=name,celula_origem=old_id)
        if c['cell_type']=='markdown':
            if old_id in headings:c['source']=rename_heading(c['source'],*headings[old_id])
            else:c['source']=rewrite_references(''.join(c['source']) if isinstance(c['source'],list) else c['source']).splitlines(keepends=True)
        cells.append(c)
        trace.append(dict(notebook_origem=name,celula_origem=old_id,celula_destino=c['id'],tipo=c['cell_type'],
            source_origem_sha256=sha(json.dumps(original.get('source'),ensure_ascii=False).encode()),
            source_destino_sha256=sha(json.dumps(c.get('source'),ensure_ascii=False).encode()),
            alteracao='titulos_e_referencias' if c['cell_type']=='markdown' else 'codigo_preservado'))
    for c in result['cells'][:split]:add(c,TARGET)
    # Sumário novo sem substituir os parágrafos editados da introdução.
    cells.insert(1,dict(cell_type='markdown',id='roteiro_integrado',metadata={},source=[
        '## Roteiro do notebook integrado\n\n',
        'Este notebook reúne a preparação e a verificação da base, preservando os conteúdos anteriormente separados.\n\n',
        '1. Limpeza estrutural e normalização conservadora.\n2. Proteção de dados pessoais e PLN leve.\n',
        '3. [Fontes, versões, licenças e integridade](#fontes-proveniencia).\n',
        '4. [Verificações automáticas, conteúdo, recorte e partições](#verificacao-automatica).\n',
        '5. Reconciliação, gráficos, diagnóstico final e integração.\n']))
    for name,anchor in [(NAMES[4],'fontes-proveniencia'),(NAMES[3],'verificacao-automatica')]:
        cells.append(dict(cell_type='markdown',id='ancora_'+PREFIXES[name].rstrip('_'),metadata={},source=['<a id="'+anchor+'"></a>\n']))
        for c in books[name]['cells']:add(c,name)
    for c in result['cells'][split:]:add(c,TARGET)
    if len({c['id'] for c in cells})!=len(cells):raise ValueError('IDs repetidos na integração.')
    for c in cells:
        if c['cell_type']=='code':compile(''.join(c['source']),c['id'],'exec')
    result['cells']=cells
    result['metadata']['kernelspec']=dict(display_name='Python (.venv lex_clt.ai)',language='python',name='lex-clt-ai')
    result['metadata']['lexia_integracao']=dict(origens=[TARGET,NAMES[3],NAMES[4]],versao=1)
    return result,trace


def redirect_generated(root,origin,generated):
    """Geradores legados atualizam apenas o código já incorporado ao 03."""
    root=Path(root).resolve()
    if not load_state(root):return False
    if origin not in PREFIXES:raise ValueError('Origem não integrada.')
    proposed=copy.deepcopy(generated)
    for c in proposed['cells']:c['id']=PREFIXES[origin]+c['id']
    save_notebook(root/'notebooks/02_jurisprudencia'/TARGET,proposed)
    return True
