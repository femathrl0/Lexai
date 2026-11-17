"""Executa as células de código de um notebook de jurisprudência e grava as saídas reais.

Mesmo mecanismo de scripts/run_preparacao_jurisprudencia.py: captura display/Markdown e gráficos do
matplotlib e salva com notebook_preservation.save_notebook(mode='execution'), que preserva o Markdown.

Uso: python scripts/executar_notebook_jurisprudencia.py 04_experimentos_chunking_jurisprudencia.ipynb
"""
from pathlib import Path
from contextlib import redirect_stdout
import base64
import io
import json
import os
import sys


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root))
    # Aceita o nome de um notebook de jurisprudência ou um caminho relativo à raiz do projeto.
    alvo = root / sys.argv[1] if '/' in sys.argv[1] else root / 'notebooks/02_jurisprudencia' / sys.argv[1]
    os.chdir(alvo.parent)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.figure
    import matplotlib.pyplot as plt
    import IPython.display
    from worker.ingestao.jurisprudencia.notebook_integration import output_text
    from worker.ingestao.jurisprudencia.notebook_preservation import save_notebook
    name = alvo.name
    path = alvo
    nb = json.loads(path.read_text(encoding='utf-8'))
    ns = {'__name__': '__main__'}
    original_display, original_show = IPython.display.display, plt.show
    try:
        count = 0
        for cell in nb['cells']:
            if cell['cell_type'] != 'code':
                continue
            count += 1
            outputs = []

            def display(*values, **kwargs):
                for value in values:
                    if isinstance(value, matplotlib.figure.Figure):
                        buf = io.BytesIO()
                        value.savefig(buf, format='png', dpi=110)
                        outputs.append({'output_type': 'display_data', 'data': {
                            'image/png': base64.b64encode(buf.getvalue()).decode(),
                            'text/plain': '<Figura>'}, 'metadata': {}})
                        plt.close(value)
                        continue
                    png = value._repr_png_() if hasattr(value, '_repr_png_') else None
                    if png:  # IPython.display.Image com PNG salvo nos relatórios.
                        outputs.append({'output_type': 'display_data', 'data': {
                            'image/png': png if isinstance(png, str) else base64.b64encode(png).decode(),
                            'text/plain': '<Figura>'}, 'metadata': {}})
                        continue
                    data = {'text/plain': str(value)}
                    if hasattr(value, '_repr_html_') and value._repr_html_():
                        data['text/html'] = value._repr_html_()
                    elif type(value).__name__ == 'Markdown':
                        data['text/markdown'] = value.data
                    for kind in ('text/markdown', 'text/plain', 'text/html'):
                        if isinstance(data.get(kind), str):
                            data[kind] = output_text(root, data[kind], name)
                    outputs.append({'output_type': 'display_data', 'data': data, 'metadata': {}})

            def show(*a, **k):
                for num in plt.get_fignums():
                    buf = io.BytesIO()
                    plt.figure(num).savefig(buf, format='png', dpi=110)
                    outputs.append({'output_type': 'display_data', 'data': {
                        'image/png': base64.b64encode(buf.getvalue()).decode(),
                        'text/plain': '<Figura>'}, 'metadata': {}})
                plt.close('all')

            IPython.display.display, plt.show = display, show
            ns['display'] = display
            stream = io.StringIO()
            print('Executando:', cell.get('id'), flush=True)
            with redirect_stdout(stream):
                exec(compile(''.join(cell['source']), cell.get('id') or f'celula_{count}', 'exec'), ns)
            show()
            if stream.getvalue():
                outputs.insert(0, {'output_type': 'stream', 'name': 'stdout', 'text': stream.getvalue()})
            cell.update(execution_count=count, outputs=outputs)
        save_notebook(path, nb, mode='execution')
        print('Notebook salvo:', path, flush=True)
    finally:
        IPython.display.display, plt.show = original_display, original_show


if __name__ == '__main__':
    main()
