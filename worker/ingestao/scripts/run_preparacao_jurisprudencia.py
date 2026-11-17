"""Executa as células de apresentação dos notebooks 02/03 com resultados reais."""
import argparse,base64,hashlib,io,json,sys,time
from pathlib import Path
from contextlib import redirect_stdout
from datetime import datetime,timezone


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--etapa',choices=['eda','estrutura','revisao','origens','todas'],default='todas');args=parser.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import IPython.display
    original_display,original_show=IPython.display.display,plt.show
    paths={'eda':'02_eda_jurisprudencia.ipynb','estrutura':'03_limpeza_estruturacao_jurisprudencia.ipynb','revisao':'04_revisao_prontidao_jurisprudencia.ipynb','origens':'05_origens_recuperacao_jurisprudencia.ipynb'}
    from worker.ingestao.jurisprudencia.notebook_integration import load_state,output_text
    if load_state(root):
        paths={k:v for k,v in paths.items() if k in ('eda','estrutura')}
        if args.etapa in ('revisao','origens'):
            print('Conteúdo integrado ao notebook 03; executando a preparação consolidada.',flush=True)
            args.etapa='estrutura'
    try:
        for stage,name in paths.items():
            if args.etapa!='todas' and args.etapa!=stage:continue
            path=root/'notebooks/02_jurisprudencia'/name;nb=json.loads(path.read_text(encoding='utf-8'));ns={'__name__':'__main__'};count=0
            for cell in nb['cells']:
                if cell['cell_type']!='code':continue
                source=''.join(cell['source']);count+=1;outputs=[]
                if cell['id']=='config_estrutura' and 'EXECUTAR_ESTRUTURACAO=False' not in source:raise ValueError('Use a CLI de preparação para executar a leitura das origens.')
                def display(*values,**kwargs):
                    for value in values:
                        data={'text/plain':str(value)}
                        if hasattr(value,'_repr_html_') and value._repr_html_():data['text/html']=value._repr_html_()
                        elif type(value).__name__=='Markdown':data['text/markdown']=value.data
                        for kind in ('text/markdown','text/plain','text/html'):
                            if isinstance(data.get(kind),str):data[kind]=output_text(root,data[kind],name)
                        outputs.append({'output_type':'display_data','data':data,'metadata':{}})
                def show(*a,**k):
                    for num in plt.get_fignums():
                        buf=io.BytesIO();plt.figure(num).savefig(buf,format='png',dpi=110)
                        outputs.append({'output_type':'display_data','data':{'image/png':base64.b64encode(buf.getvalue()).decode(),'text/plain':'<Gráfico de preparação de jurisprudência>'},'metadata':{}})
                    plt.close('all')
                IPython.display.display,plt.show=display,show;stream=io.StringIO()
                print('Executando:',stage,cell['id'],flush=True)
                with redirect_stdout(stream):exec(compile(source,cell['id'],'exec'),ns)
                if stream.getvalue():outputs.insert(0,{'output_type':'stream','name':'stdout','text':stream.getvalue()})
                cell.update(execution_count=count,outputs=outputs)
            from worker.ingestao.jurisprudencia.notebook_preservation import save_notebook
            save_notebook(path,nb,mode='execution')
            folder=ns['EDA_DIR'] if stage=='eda' else ns['STRUCT_REPORT'] if stage=='estrutura' else ns['REVIEW_DIR'] if stage=='revisao' else ns['SOURCE_DIR']
            manifest={'executado_em_utc':datetime.now(timezone.utc).isoformat(),'notebook_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'codigo_atualizacao_apresentacao_sha256':hashlib.sha256((root/'src/jurisprudencia/presentation.py').read_bytes()).hexdigest(),
                'celulas_executadas':count,'executor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
            (folder/'manifesto_notebook.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print('Notebook salvo:',path,flush=True)
    finally:IPython.display.display,plt.show=original_display,original_show


if __name__=='__main__':main()
