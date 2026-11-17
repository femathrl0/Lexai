"""Disponibilidade de amostra de URLs oficiais; não comprova equivalência documental."""
from pathlib import Path
from urllib.request import Request,urlopen,HTTPRedirectHandler,build_opener
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
import json,sys,hashlib


def main():
    root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
    from worker.ingestao.jurisprudencia import automatic_review,audit
    folder,result=automatic_review.load(root)
    rows=json.loads((root/result['pasta_dados']/'fontes_oficiais_amostra.json').read_text(encoding='utf-8'))
    class OfficialRedirect(HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            if not automatic_review.official_host(newurl):raise ValueError('Redirecionamento fora da política de domínio oficial.')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    def check(row):
        base=dict(registro_id=row['registro_id'],host=row['host'],url_sha256=hashlib.sha256(row['url'].encode()).hexdigest(),
            conteudo_documental_comparado=False)
        try:
            opener=build_opener(OfficialRedirect())
            try:
                response=opener.open(Request(row['url'],method='HEAD',headers={'User-Agent':'LexIA-auditoria-fontes/1.0'}),timeout=12)
            except HTTPError as e:
                if e.code!=405:raise
                response=opener.open(Request(row['url'],headers={'User-Agent':'LexIA-auditoria-fontes/1.0','Range':'bytes=0-4095'}),timeout=12)
            with response:
                if not automatic_review.official_host(response.geturl()):raise ValueError('Host final fora da política.')
                return dict(base,status='acessivel_http',http_status=response.status)
        except HTTPError as e:return dict(base,status='resposta_http',http_status=e.code)
        except Exception as e:return dict(base,status='indisponivel_na_consulta',tipo_erro=type(e).__name__)
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(check,rows))
    report=dict(urls_consultadas=len(results),resultados=results,metodo='HTTPS público *.jus.br, sem credenciais; HEAD, GET limitado quando HEAD retorna 405; redirecionamentos restritos.',
        limite='Disponibilidade HTTP não comprova identidade do texto, atualidade jurídica ou autenticidade de cada decisão. Comparação documental com fonte oficial não implementada neste módulo.')
    audit.write_json(folder/'fontes_oficiais_verificadas.json',report)
    print('URLs oficiais consultadas:',len(results),'|',[(r['host'],r['status'],r.get('http_status')) for r in results])

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
