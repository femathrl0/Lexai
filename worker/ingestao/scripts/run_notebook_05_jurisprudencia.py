"""Atualiza as saídas de leitura do notebook 05, sem iniciar outra geração de chunks."""
from pathlib import Path
import base64,io,json,sys
from contextlib import redirect_stdout
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))


def main(notebook_name='05_chunking_definitivo_jurisprudencia.ipynb'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import IPython.display as ipd
    from worker.ingestao.jurisprudencia.notebook_preservation import save_notebook
    if notebook_name not in ('05_chunking_definitivo_jurisprudencia.ipynb','06_embeddings_indexacao_jurisprudencia.ipynb'):
        raise ValueError('Notebook fora das etapas autorizadas.')
    path=ROOT/'notebooks/02_jurisprudencia'/notebook_name
    original=path.read_bytes();book=json.loads(original);namespace={'__name__':'__main__'}
    old_display,old_show=ipd.display,plt.show
    try:
        count=0
        for cell in book['cells']:
            if cell['cell_type']!='code':continue
            count+=1;outputs=[]
            def display(*values,**kwargs):
                for value in values:
                    data={'text/plain':str(value)}
                    if type(value).__name__=='Markdown':data['text/markdown']=value.data
                    elif hasattr(value,'_repr_html_'):
                        html=value._repr_html_()
                        if html:data['text/html']=html
                    outputs.append(dict(output_type='display_data',data=data,metadata={}))
            def show(*args,**kwargs):
                for n in plt.get_fignums():
                    buf=io.BytesIO();plt.figure(n).savefig(buf,format='png',dpi=110)
                    outputs.append(dict(output_type='display_data',metadata={},data={'image/png':base64.b64encode(buf.getvalue()).decode(),'text/plain':'Andamento do chunking definitivo'}))
                plt.close('all')
            ipd.display,plt.show=display,show
            stream=io.StringIO();print('Executando:',cell['id'],flush=True)
            with redirect_stdout(stream):exec(compile(''.join(cell['source']),cell['id'],'exec'),namespace)
            if stream.getvalue():outputs.insert(0,dict(output_type='stream',name='stdout',text=stream.getvalue()))
            cell.update(execution_count=count,outputs=outputs)
            if path.read_bytes()!=original:raise RuntimeError('Notebook editado durante a execução; versão atual preservada.')
            save_notebook(path,book,mode='execution');original=path.read_bytes()
    finally:ipd.display,plt.show=old_display,old_show
    print('Notebook atualizado sem iniciar uma segunda geração:',notebook_name)

if __name__=='__main__':main()
