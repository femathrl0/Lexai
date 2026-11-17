"""Prepara a base reduzida para o pipeline: arquivo em quarentena e rastreabilidade derivada.

1. Copia byte a byte o arquivo ilegível (train-00002.parquet) para a pasta da base reduzida, para que o
   inventário reduzido continue com 20 arquivos recebidos, 19 ativos e 1 em quarentena.
2. Gera reports/jurisprudencia/origens_huggingface/rastreabilidade_atual.{json,csv} para os arquivos
   reduzidos: cada arquivo herda as correspondências do arquivo completo de onde foi recortado,
   registrando o hash do arquivo completo e o vínculo de derivação. A versão da base completa é
   preservada em reports/jurisprudencia/base_completa_ponteiros/.
"""
from pathlib import Path
import csv
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from worker.ingestao.jurisprudencia import audit  # noqa: E402

ORIGINAIS = Path.home() / 'Downloads'
REDUZIDA = ROOT / 'dados/raw/jurisprudencia/base_reduzida'
MANIFESTO = ROOT / 'dados/relatorios/jurisprudencia/base_reduzida/manifesto_base_reduzida.json'
ORIGENS = ROOT / 'dados/relatorios/jurisprudencia/origens_huggingface'
BACKUP = ROOT / 'dados/relatorios/jurisprudencia/base_completa_ponteiros'
QUARENTENA = 'train-00002.parquet'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    manifesto = json.loads(MANIFESTO.read_text(encoding='utf-8'))
    derivados = {a['arquivo']: a for a in manifesto['arquivos']}
    origem_q, destino_q = ORIGINAIS / QUARENTENA, REDUZIDA / QUARENTENA
    if not destino_q.exists() or audit.hash_file(destino_q) != audit.hash_file(origem_q):
        shutil.copyfile(origem_q, destino_q)
    if audit.hash_file(destino_q) != audit.hash_file(origem_q):
        raise RuntimeError('Cópia do arquivo em quarentena divergente.')
    print('Arquivo em quarentena copiado sem alteração:', destino_q)

    BACKUP.mkdir(parents=True, exist_ok=True)
    for nome in ('rastreabilidade_atual.json', 'rastreabilidade_atual.csv'):
        guardado = BACKUP / ('origens_huggingface__' + nome)
        if not guardado.exists():
            shutil.copyfile(ORIGENS / nome, guardado)
    completa = json.loads((BACKUP / 'origens_huggingface__rastreabilidade_atual.json').read_text(encoding='utf-8'))

    saida = []
    for r in completa:
        novo = dict(r)
        if r['arquivo'] in derivados:
            d = derivados[r['arquivo']]
            if d['origem_sha256'] != r['sha256_local']:
                raise RuntimeError(f"{r['arquivo']}: arquivo completo diverge da rastreabilidade.")
            novo.update(sha256_local=d['sha256'], bytes_local=d['bytes'],
                        status=r['status'] + '_derivado_recorte' if r['correspondencias'] else r['status'],
                        derivado_de=dict(arquivo=r['arquivo'], sha256=r['sha256_local'], bytes=r['bytes_local'],
                                         registros_mantidos=d['registros'], protocolo=manifesto['protocolo']))
        elif r['arquivo'] != QUARENTENA:
            raise RuntimeError(f"{r['arquivo']} ausente da base reduzida.")
        saida.append(novo)
    audit.write_json(ORIGENS / 'rastreabilidade_atual.json', saida)

    with (BACKUP / 'origens_huggingface__rastreabilidade_atual.csv').open(encoding='utf-8-sig', newline='') as f:
        linhas = list(csv.DictReader(f))
    por_arquivo = {r['arquivo']: r for r in saida}
    campos = list(linhas[0]) + [c for c in ('sha256_arquivo_completo', 'registros_mantidos') if c not in linhas[0]]
    for linha in linhas:
        r = por_arquivo[linha['arquivo_local']]
        if 'sha256_local' in linha:
            linha['sha256_local'] = r['sha256_local']
        if 'bytes_local' in linha:
            linha['bytes_local'] = r['bytes_local']
        if 'status' in linha:
            linha['status'] = r['status']
        linha['sha256_arquivo_completo'] = r.get('derivado_de', {}).get('sha256', r['sha256_local'])
        linha['registros_mantidos'] = r.get('derivado_de', {}).get('registros_mantidos', '')
    audit.write_csv(ORIGENS / 'rastreabilidade_atual.csv', linhas, campos)
    print('Rastreabilidade derivada gravada para', len(saida), 'arquivos.')


if __name__ == '__main__':
    main()
