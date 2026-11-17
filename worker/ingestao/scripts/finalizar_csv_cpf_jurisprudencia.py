"""Finaliza uma exportação interrompida somente na renomeação, sem remascarar."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import json,sys,time,gc


def main():
    root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
    from worker.ingestao.jurisprudencia import audit,dataset,privacy
    _,base_reports=dataset.locations(root)
    base_hash=audit.hash_file(base_reports/'manifestos_arquivos.json');code_hash=audit.hash_file(privacy.__file__)
    protocol=audit.digest((code_hash+base_hash).encode())
    folder=root/'dados/relatorios/jurisprudencia/protecao_cpf'/protocol
    out=root/'dados/processed/jurisprudencia/protecao_cpf'/protocol
    csv=out/'jurisprudencia_cpf_protegido.csv';partial=csv.with_suffix('.csv.partial')
    source=partial if partial.exists() else csv
    expected=json.loads((base_reports/'resumo_estruturacao.json').read_text(encoding='utf-8'))['registros']
    if '--validar' in sys.argv:
        validation=privacy.validate_csv(source,expected)
        gc.collect()
        audit.write_json(folder/'validacao_csv_recuperacao.json',dict(validacao=validation,csv_sha256=audit.hash_file(source),csv_bytes=source.stat().st_size))
        print('Releitura completa validada; processo encerrará todos os leitores.',flush=True);return
    verified=json.loads((folder/'validacao_csv_recuperacao.json').read_text(encoding='utf-8'))
    if source.stat().st_size!=verified['csv_bytes'] or audit.hash_file(source)!=verified['csv_sha256']:
        raise ValueError('CSV mudou após validação.')
    outputs=[];totals=Counter();fields=Counter()
    for m in json.loads((base_reports/'manifestos_arquivos.json').read_text(encoding='utf-8')):
        old=json.loads((folder/(m['arquivo_id']+'.json')).read_text(encoding='utf-8'))
        if old['origem_sha256']!=m['saida_sha256'] or audit.hash_file(root/old['arquivo'])!=old['sha256']:
            raise ValueError('Checkpoint inválido.')
        outputs.append(old);totals.update(old['totais']);fields.update(old['por_campo'])
    if totals['registros']!=expected:raise ValueError('Quantidade divergente.')
    if partial.exists():
        for attempt in range(20):
            try:partial.replace(csv);break
            except PermissionError:
                if attempt==19:raise
                time.sleep(1)
    result=dict(protocolo='cpf-mascaramento-v1',executado_em_utc=datetime.now(timezone.utc).isoformat(),
        codigo_sha256=code_hash,manifesto_base_sha256=base_hash,**dict(totals),
        mascaramentos_por_campo=dict(fields),validacao=verified['validacao'],csv=str(csv.relative_to(root)),
        csv_sha256=verified['csv_sha256'],csv_bytes=verified['csv_bytes'],arquivos_protegidos=outputs,
        colunas=list(privacy.FIELDS.values())+['cpf_mascarado','privacidade_status'],marcador=privacy.TOKEN,
        padrao_re2=privacy.PATTERN,originais_preservados=True,anonimizado_integralmente=False,indexacao_realizada=False,
        finalizador_sha256=audit.hash_file(__file__),
        limites='Mascaramento de sequências compatíveis com CPF, inclusive DV inválido. Pode mascarar outros números de 11 dígitos. Não cobre formas por extenso, todas as ofuscações, nomes, endereços ou outros dados pessoais. Não libera publicação ou indexação.',
        offsets='Chunking deve usar texto_protegido e seus próprios offsets, sem reutilizar offsets anteriores.')
    audit.write_json(folder/'resumo_protecao.json',result)
    audit.write_json(root/'dados/processed/jurisprudencia/protecao_cpf/ativa.json',dict(pasta_dados=str(out.relative_to(root)),pasta_relatorios=str(folder.relative_to(root))))
    print('CSV final validado:',csv,flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
