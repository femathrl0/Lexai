"""Executa as etapas de dados dos notebooks 01–03 sobre a base reduzida (opção D).

Ordem: auditoria (01) -> EDA (02) -> estruturação, proteção de CPF, PLN leve, revisão e verificação
automática (03). Cada etapa grava em pastas novas versionadas por hash e atualiza seu ponteiro ativo;
os resultados da base completa permanecem em disco e seus ponteiros estão copiados em
reports/jurisprudencia/base_completa_ponteiros/.

Bloqueios do Windows/OneDrive ao renomear os CSVs grandes são tratados com os finalizadores do projeto,
em processos separados (scripts/finalizar_csv_cpf_jurisprudencia.py e scripts/retomar_auditoria_pln_leve.py).

Uso: python scripts/rodar_pipeline_base_reduzida.py [--desde ETAPA]
"""
from pathlib import Path
import argparse
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
REDUZIDA = ROOT / 'dados/raw/jurisprudencia/base_reduzida'
ETAPAS = ['auditoria', 'eda', 'estrutura', 'protecao_cpf', 'pln_leve', 'revisao', 'automacao']


def script(nome, *args):
    print('>>', nome, *args, flush=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts' / nome), *args], check=True)


def com_finalizador(acao, finalizadores):
    try:
        acao()
    except PermissionError as exc:
        print('Renomeação bloqueada; usando o finalizador em processo separado:', exc, flush=True)
        *preparo, (nome_final, args_final) = finalizadores
        for nome, args in preparo:
            script(nome, *args)
        # Este processo mantém referência ao CSV após o erro; a renomeação só funciona depois que ele termina.
        print(f'FINALIZAR_FORA_DO_PROCESSO: scripts/{nome_final} {" ".join(args_final)}', flush=True)
        raise SystemExit(3)


def revisao():
    import json
    import matplotlib
    matplotlib.use('Agg')
    from worker.ingestao.jurisprudencia import readiness, review_checks
    folder, result = readiness.run(ROOT)
    print('Verificação independente:', review_checks.verify(ROOT), flush=True)
    readiness.figures(folder, json.loads((folder / 'resumo_revisao.json').read_text(encoding='utf-8')))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--desde', choices=ETAPAS, default='auditoria')
    args = parser.parse_args()
    from worker.ingestao.jurisprudencia import audit, eda, structure, privacy, light_nlp, automatic_review
    acoes = {
        'auditoria': lambda: audit.run(ROOT, [REDUZIDA / n for n in audit.FILES]),
        'eda': lambda: eda.run(ROOT),
        'estrutura': lambda: structure.run(ROOT),
        'protecao_cpf': lambda: com_finalizador(lambda: privacy.run(ROOT), [
            ('finalizar_csv_cpf_jurisprudencia.py', ['--validar']), ('finalizar_csv_cpf_jurisprudencia.py', [])]),
        'pln_leve': lambda: com_finalizador(lambda: light_nlp.run(ROOT), [
            ('retomar_auditoria_pln_leve.py', []), ('retomar_auditoria_pln_leve.py', ['--finalizar'])]),
        'revisao': revisao,
        'automacao': lambda: (automatic_review.run(ROOT), script('finalizar_automacao_base_reduzida.py')),
    }
    for etapa in ETAPAS[ETAPAS.index(args.desde):]:
        inicio = time.time()
        print(f'===== {etapa}', flush=True)
        acoes[etapa]()
        print(f'===== {etapa} concluída em {time.time() - inicio:.0f}s', flush=True)


if __name__ == '__main__':
    main()
