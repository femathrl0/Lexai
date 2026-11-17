"""Atualiza o notebook com resultados e gráficos da auditoria já executada."""
import base64
import io
import json
import sys
import time
import hashlib
import importlib.metadata
from datetime import datetime, timezone
from contextlib import redirect_stdout
from pathlib import Path


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import IPython.display
    path = root/'notebooks/02_jurisprudencia/01_auditoria_jurisprudencia.ipynb'
    nb = json.loads(path.read_text(encoding='utf-8'))
    ns = {'__name__':'__main__'}
    original_display, original_show = IPython.display.display, plt.show
    try:
        count = 0
        for cell in nb['cells']:
            if cell['cell_type'] != 'code': continue
            count += 1
            source = ''.join(cell['source'])
            if cell['id']=='configuracao_jurisprudencia' and 'EXECUTAR_AUDITORIA = False' not in source:
                raise RuntimeError('Use o auditor em linha de comando para executar a varredura antes de salvar os painéis.')
            output = []
            def capture(*values, **kwargs):
                for value in values:
                    data = {'text/plain':str(value)}
                    if hasattr(value,'_repr_html_') and value._repr_html_(): data['text/html']=value._repr_html_()
                    elif type(value).__name__=='Markdown': data['text/markdown']=value.data
                    from worker.ingestao.jurisprudencia.notebook_integration import output_text
                    for kind in ('text/markdown','text/plain','text/html'):
                        if isinstance(data.get(kind),str):data[kind]=output_text(root,data[kind],path.name)
                    output.append({'output_type':'display_data','data':data,'metadata':{}})
            def show(*args, **kwargs):
                for num in plt.get_fignums():
                    buffer=io.BytesIO();plt.figure(num).savefig(buffer,format='png',dpi=110)
                    output.append({'output_type':'display_data','data':{'image/png':base64.b64encode(buffer.getvalue()).decode(),
                        'text/plain':'<Gráfico da auditoria de jurisprudência>'},'metadata':{}})
                plt.close('all')
            IPython.display.display, plt.show = capture, show
            stream=io.StringIO()
            print('Executando:',cell['id'],flush=True)
            with redirect_stdout(stream): exec(compile(source,cell['id'],'exec'),ns)
            if stream.getvalue(): output.insert(0,{'output_type':'stream','name':'stdout','text':stream.getvalue()})
            cell.update(execution_count=count,outputs=output)
        from worker.ingestao.jurisprudencia.notebook_preservation import save_notebook
        save_notebook(path,nb,mode='execution')
        versions={name:importlib.metadata.version(name) for name in ('pyarrow','ijson','pandas','numpy','matplotlib')}
        manifest={'executado_em_utc':datetime.now(timezone.utc).isoformat(),'python':sys.version,
            'pacotes':versions,'notebook_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'executor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'codigo_relatorios_sha256':hashlib.sha256((root/'src/jurisprudencia/report.py').read_bytes()).hexdigest(),
            'codigo_atualizacao_apresentacao_sha256':hashlib.sha256((root/'src/jurisprudencia/presentation.py').read_bytes()).hexdigest(),
            'relatorios_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                for p in ns['REPORT_JUR'].iterdir() if p.is_file() and p.suffix in ('.csv','.md','.png')}}
        (ns['REPORT_JUR']/'manifesto_execucao_notebook.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Notebook salvo com a auditoria executada. Relatórios:',ns['REPORT_JUR'])
    finally:
        IPython.display.display, plt.show=original_display,original_show


if __name__=='__main__': main()
