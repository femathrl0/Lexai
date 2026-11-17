"""Atualiza apresentação sem alterar protocolos ou dados da auditoria/estruturação."""
from pathlib import Path
import json
from . import audit,dataset,report

def audit_scope(root,folder,summary,profiles):
    """Escopo de apresentação solicitado; preserva inventário e checkpoints históricos."""
    import copy,shutil
    excluded={'train-00002.parquet'}
    inventory=json.loads((Path(folder)/'inventario.json').read_text(encoding='utf-8'))
    kept=[p for p in profiles if p['arquivo'] not in excluded]
    removed=[p for p in profiles if p['arquivo'] in excluded]
    if any(p['registros_lidos'] for p in removed):raise ValueError('Exclusão com registros requer recalcular os agregados.')
    result=copy.deepcopy(summary)
    result['arquivos_recebidos']=len(kept)
    result['arquivos_concluidos']=sum(p['status_leitura']=='concluido' for p in kept)
    result['arquivos_com_falha_ou_leitura_parcial']=sum(p['status_leitura']!='concluido' for p in kept)
    result['bytes_recebidos']=sum(e['bytes'] for e in inventory if e['arquivo'] not in excluded)
    view=Path(folder)/'escopo_ativo_notebook_01';view.mkdir(exist_ok=True)
    shutil.copyfile(Path(folder)/'duplicatas_resumo.csv',view/'duplicatas_resumo.csv')
    audit.write_json(view/'exclusoes_escopo.json',dict(arquivos_excluidos=sorted(excluded),
        motivo='Arquivo ilegível excluído do escopo ativo do notebook 01 por solicitação da pessoa usuária.',
        originais_preservados=True,registros_legiveis_inalterados=result['registros_lidos']))
    return result,kept,view

def context(root):
    root=Path(root).resolve();source=root/'dados/relatorios/jurisprudencia/origens_huggingface'
    def read(p):return json.loads(p.read_text(encoding='utf-8'))
    origins=read(source/'rastreabilidade_atual_resumo.json');matches=read(source/'rastreabilidade_atual.json')
    audit_dir,audited,_=report.load(root)
    inventory=read(audit_dir/'inventario.json')
    if {e['arquivo_id']:e['sha256'] for e in inventory}!={e['arquivo_id']:e['sha256_local'] for e in matches}:
        raise ValueError('Rastreabilidade não corresponde ao inventário auditado.')
    data,structure_dir=dataset.locations(root);structured=read(structure_dir/'resumo_estruturacao.json')
    active=read(root/'dados/relatorios/jurisprudencia/revisao/revisao_ativa.json')
    review_dir=(root/active['pasta']).resolve()
    if not review_dir.is_relative_to(root/'dados/relatorios/jurisprudencia/revisao'):raise ValueError('Relatório de revisão inválido.')
    reviewed=read(review_dir/'resumo_revisao.json');verification=read(review_dir/'verificacao_independente.json')
    if not (audited['registros_lidos']==structured['registros']==reviewed['registros']==verification['registros_verificados']):
        raise ValueError('Etapas não correspondem ao mesmo total de registros.')
    if reviewed['base_manifesto_sha256']!=audit.hash_file(structure_dir/'manifestos_arquivos.json'):
        raise ValueError('Revisão vinculada a outra base estruturada.')
    pending=[r['arquivo'] for r in matches if not r['correspondencias']]
    c=dict(root=root,origins=origins,reviewed=reviewed,verification=verification,
        pending=pending,audited=audited,structured=structured,review_dir=review_dir,source=source)
    if (root/'dados/processed/jurisprudencia/protecao_cpf/ativa.json').exists():
        from . import privacy
        _,protected=privacy.load(root)
        if protected['manifesto_base_sha256']!=audit.hash_file(structure_dir/'manifestos_arquivos.json'):
            raise ValueError('Derivada protegida vinculada a outra base.')
        c['cpf_protection']=protected
    if (root/'dados/processed/jurisprudencia/pln_leve/ativa.json').exists():
        from . import light_nlp
        _,pln=light_nlp.load(root)
        if pln['base_cpf_csv_sha256']!=c['cpf_protection']['csv_sha256'] or pln['registros']!=structured['registros']:
            raise ValueError('PLN leve vinculado a outra derivada ou quantidade de registros.')
        c['pln_leve']=pln
    return c

def status_markdown(c):
    o,v=c['origins'],c['reviewed']
    n=c['audited']['registros_lidos'];fmt=lambda x:f'{x:,}'.replace(',','.')
    pending=', '.join('`'+name+'`' for name in c['pending'])
    protected=c.get('cpf_protection')
    privacy_note=(f"\n\n**Proteção de CPFs:** foi gerada uma derivada separada em CSV e Parquet, com {fmt(protected['registros'])} registros e {fmt(protected['registros_com_mascaramento'])} registros alterados por mascaramento. O CSV foi relido integralmente, sem resíduos dos padrões tratados. Os originais continuam preservados; nomes e outros dados pessoais ainda exigem revisão. Esta derivada não é apresentada como integralmente anônima."
                  if protected else '')
    return f'''## Situação atual — atualização após os notebooks 04 e 05

O escopo estatístico continua sendo **{fmt(n)} registros legíveis dos 20 arquivos originais**, com 19 arquivos integralmente lidos e um em quarentena. Os 16 shards de celsowm são o inventário remoto; somente quatro `train-*` estavam no lote local original.

**Rastreabilidade:** {o['arquivos_locais_com_hash_confirmado']} de {o['arquivos_recebidos']} arquivos confirmados por SHA-256 e tamanho: 14 Parquet RepoJus (TRT-10, TRT-17 e TST), três Parquet celsowm e o JSONL TRT-13. O registro por arquivo contém caminho remoto, commit consultado, hash e licença declarada. Os três arquivos celsowm coincidem em dois repositórios; as contagens por dataset se sobrepõem. O commit consultado não prova a revisão histórica do download. Permanecem sem correspondência exata: {pending}.

**Licenças declaradas:** CC BY 4.0 nos dois repositórios celsowm; CC BY 4.0 no RepoJus para seleção, organização, normalização, metadados e documentação; MIT no TRT-13. Atribuição de licença não substitui revisão de privacidade, pertinência ou direitos de terceiros. CEIA-COREJUR e STF Acórdãos são referências candidatas, sem correspondência com os arquivos auditados; não se atribuem suas licenças automaticamente.

**STF na base atual:** {fmt(sum(x['registros_lidos'] for x in c['audited']['tribunais_observados'] if x['tribunal']=='STF'))} registros do STF com sinais de tema trabalhista integram a base, junto com TST e TRTs, nas mesmas etapas, critérios e partições, sem separação.

**Preparação e revisão:** a limpeza e estruturação estão concluídas, sem exclusões automáticas. O notebook 04 registrou {fmt(v['sinal_privacidade'])} registros com sinais de privacidade e {v['amostra_revisao']} IDs para revisão amostral. Ausência de sinal não prova anonimização; a revisão da amostra não aprova o restante da base. A proposta de partição por componentes relacionados foi conferida independentemente: {c['verification']['vinculos_atravessando_splits']} vínculos conhecidos atravessam splits. Não cobre relações semânticas não detectadas nem constitui avaliação do modelo.

**Pendências efetivas:** resolver a equivalência/escopo do arquivo em quarentena; confirmar a origem do JSON TST; revisar dados pessoais, pertinência temática (especialmente STF) e versões/repetições; aprovar uma seleção antes do chunking e da indexação. Não houve anonimização completa, treinamento, embeddings ou indexação.

Detalhes: [04 — Revisão de prontidão](04_revisao_prontidao_jurisprudencia.ipynb), [05 — Origens](05_origens_recuperacao_jurisprudencia.ipynb) e [tabela de rastreabilidade](../../reports/jurisprudencia/origens_huggingface/rastreabilidade_atual.csv).{privacy_note}
'''

def eda_status_markdown(c):
    n=f"{c['audited']['registros_lidos']:,}".replace(',','.')
    protected=c.get('cpf_protection')
    note=(f"Na etapa 03 foi concluído o mascaramento de CPFs em uma derivada CSV/Parquet de {n} registros: "
          f"{protected['registros_com_mascaramento']:,} registros alterados e {protected['sequencias_compativeis_mascaradas']:,} substituições. "
          "O CSV foi relido integralmente, sem resíduos dos padrões tratados. Os originais permanecem separados; outros dados pessoais ainda exigem revisão."
          if protected else 'A proteção de CPFs ainda não tem resultado concluído registrado.')
    return f'''## Escopo e proteção de dados

A EDA apresenta **19 arquivos ativos e {n} registros legíveis**, alinhados ao notebook 01. O arquivo local ilegível foi excluído da análise ativa; os 20 arquivos recebidos continuam documentados no inventário histórico. A exclusão não removeu registros legíveis nem alterou as proporções por tribunal.

Foram confirmadas por hash e tamanho as origens de **18 dos 19 arquivos ativos**. A origem individual de `jurisprudencias_tst.json` continua pendente. Os 6.926 registros do STF com sinais de tema trabalhista integram a base atual, junto com TST e TRTs, sem separação.

{note}

**Versão analisada:** os gráficos históricos descrevem os dados anteriores ao mascaramento. O painel automático adicional apresenta a cobertura e os tamanhos pós-PLN. Os vínculos e as partições foram recalculados e conferidos sobre essa versão.

A triagem temática usa metadados, sem classificar juridicamente o conteúdo dos textos. A pertinência trabalhista dos documentos STF permanece sujeita a revisão. Detalhes em [03 — Limpeza e proteção](03_limpeza_estruturacao_jurisprudencia.ipynb), [04 — Revisão](04_revisao_prontidao_jurisprudencia.ipynb) e [05 — Origens](05_origens_recuperacao_jurisprudencia.ipynb).
'''

def eda_scope(root,summary):
    """Atualiza somente o resumo de apresentação; estatísticas históricas preservadas."""
    import copy
    folder,_,profiles=report.load(root)
    excluded={'train-00002.parquet'}
    removed=[p for p in profiles if p['arquivo'] in excluded]
    if any(p['registros_lidos'] for p in removed):raise ValueError('Recalcule a EDA antes de excluir registros legíveis.')
    active=[p for p in profiles if p['arquivo'] not in excluded]
    result=copy.deepcopy(summary)
    result.update(arquivos_ativos=len(active),arquivos_recebidos_historico=len(profiles),
        arquivos_nao_integralmente_lidos=sum(p['status_leitura']!='concluido' for p in active),
        escopo='19 arquivos ativos; excluído o arquivo ilegível sem registros lidos; inventário histórico preservado.')
    if sum(p['registros_lidos'] for p in active)!=result['registros_legiveis']:
        raise ValueError('Registros ativos divergem da EDA histórica.')
    return result,[p['arquivo'] for p in active]

def eda_frame(path,active_files):
    import pandas as pd
    frame=pd.read_csv(path)
    if 'arquivo' in frame.columns:frame=frame[frame['arquivo'].isin(active_files)].copy()
    return frame

def structure_status_markdown(c):
    p=c['cpf_protection']
    fmt=lambda value:f'{value:,}'.replace(',','.')
    pln=c.get('pln_leve')
    pln_note=('\n\n**PLN leve concluído:** formatação/entidades HTML, NFC e separação de `ementa` e `inteiro_teor` foram auditados. O CSV final foi relido integralmente, e o mascaramento foi reaplicado aos textos decodificados. Candidatos a ruído e comparações antes/depois possuem verificações por regras; os trechos incertos permanecem preservados com alertas. Use `data/processed/jurisprudencia/pln_leve/ativa.json` para localizar a versão tratada.' if pln else '')
    return f'''## Escopo e versões dos dados

O escopo ativo contém **19 arquivos e {fmt(c['structured']['registros'])} registros**, em acordo com os notebooks 01 e 02. O arquivo ilegível foi excluído do escopo ativo; seu registro permanece somente no histórico. A origem de **18 dos 19 arquivos ativos** está confirmada por hash e tamanho; a origem individual do JSON TST continua pendente. Os 6.926 registros do STF com sinais de tema trabalhista integram a base atual, junto com TST e TRTs, sem separação.

**Base canônica original:** preserva os textos original e limpo, a linhagem e os sinais de revisão; pode conter dados pessoais. As tabelas de normalização e os sinais da auditoria referem-se a essa versão.

**Derivada protegida:** o CSV e os shards Parquet contêm texto/ementa com sequências compatíveis com CPF substituídas por `[CPF_REMOVIDO]`. Foram alterados **{fmt(p['registros_com_mascaramento'])} registros**, com **{fmt(p['sequencias_compativeis_mascaradas'])} substituições**. A releitura integral validou os **{fmt(p['registros'])} registros** do CSV, sem resíduos dos padrões tratados nos campos de conteúdo. Os textos originais não foram exportados nessa derivada.

O mascaramento de CPF está concluído. A verificação automática posterior registra alertas de privacidade, inferência de conteúdo e sinais temáticos; outros dados pessoais não são considerados integralmente anonimizados. Os grupos e as partições foram recalculados após o PLN e conferidos para os vínculos conhecidos. Não houve publicação, indexação ou treinamento.

Referências: [04 — Revisão](04_revisao_prontidao_jurisprudencia.ipynb), [05 — Origens](05_origens_recuperacao_jurisprudencia.ipynb) e [regras de proteção](../../docs/protecao_cpf_jurisprudencia.md).{pln_note}
'''

def conclusion(root,stage,original):
    c=context(root)
    if stage=='auditoria':
        start=original.find('Os campos `fonte`, `url`, `spider_name`')
        if start>=0:original=original[:start]
        else:original=original.split('## Parecer técnico e próximas etapas')[0]
        start=original.find('Os arquivos `train-00000`')
        end=original.find('## Esquemas, features e completude',start)
        if start>=0 and end>=0:
            original=original[:start]+'O escopo ativo inclui somente os arquivos legíveis selecionados; o inventário histórico dos arquivos recebidos foi preservado.\n\n'+original[end:]
    elif stage=='eda':
        original=original.split('## Decisões para limpeza e estruturação')[0]
        original='# Conclusão da EDA inicial\n\n## Composição e representatividade'+original.split('## Composição e representatividade',1)[1]
        return original.rstrip()+'\n\n'+eda_status_markdown(c)
    elif stage=='estrutura':
        original=original.split('## Próximos passos')[0]
        original=original.replace('Há **1 arquivo em manifesto de quarentena**, sem estimar sua quantidade de registros inacessíveis.',
            'O arquivo ilegível permanece somente no histórico, fora dos 19 arquivos ativos.')
        return original.rstrip()+'\n\n'+structure_status_markdown(c)
    else:raise ValueError('Etapa inválida.')
    if stage=='auditoria':
        o=c['origins']
        return original.rstrip()+f'''\n\n## Síntese e pendências

A auditoria ativa abrange 19 arquivos e os mesmos {f"{c['audited']['registros_lidos']:,}".replace(',','.')} registros legíveis. A origem de {o['arquivos_locais_com_hash_confirmado']} dos 19 arquivos ativos foi confirmada por SHA-256 e tamanho; permanece sem correspondência exata `jurisprudencias_tst.json`. O arquivo ilegível foi excluído do escopo ativo por solicitação da pessoa usuária, sem apagar o original. Os 6.926 registros do STF com sinais de tema trabalhista integram a base atual, junto com TST e TRTs, sem separação.

Os alertas de privacidade e as classificações computacionais estão registrados no [04 — Verificação automática](04_revisao_prontidao_jurisprudencia.ipynb); o [05 — Origens](05_origens_recuperacao_jurisprudencia.ipynb) contém as evidências de proveniência. Os métodos não comprovam mérito jurídico ou anonimização integral.
'''
    return original.rstrip()+'\n\n'+status_markdown(c)

def update_notebook(path):
    """Idempotente: também chamado pelos geradores para evitar regressão dos textos."""
    path=Path(path);nb=json.loads(path.read_text(encoding='utf-8'))
    stage='auditoria' if path.name.startswith('01_') else 'eda' if path.name.startswith('02_') else 'estrutura'
    overrides={
      'intro_eda':'''# 02 — EDA inicial de jurisprudência

Análise exploratória dos **179.812 registros legíveis dos 19 arquivos ativos**, alinhada ao notebook 01. Utiliza os agregados integrais da auditoria: tribunais, cobertura temporal, tamanhos de texto, completude, categorias declaradas e repetições, sem expor textos ou dados de partes.

O inventário histórico preserva os 20 arquivos recebidos, incluindo o arquivo ilegível excluído do escopo ativo. Os 6.926 registros do STF com sinais de tema trabalhista integram a base atual, junto com TST e TRTs, sem separação. A exclusão não altera os registros legíveis analisados.

Os indicadores de texto e duplicação referem-se à versão anterior ao mascaramento. A etapa 03 já gerou o CSV/Parquet com CPFs mascarados; esta EDA informa seus resultados sem reaplicar a transformação. STF não equivale automaticamente a conteúdo trabalhista, e `train` nos nomes dos arquivos não define a partição do experimento.''',
      'composicao_texto_eda':'''## 1. Composição, volume e representatividade

As proporções usam os registros legíveis dos 19 arquivos ativos, incluindo possíveis sobreposições entre fontes. O arquivo ilegível permanece apenas no inventário histórico. A composição reflete os arquivos disponíveis e não a frequência de conflitos na população ou uma amostra representativa das demandas trabalhistas.''',
      'intro_estrutura':'''# 03 — Limpeza e estruturação conservadora da jurisprudência

Esta etapa trabalha com **19 arquivos ativos e 179.812 registros legíveis**, preservando a linhagem. Há uma base canônica em Parquet e uma derivada separada em CSV/Parquet com CPFs mascarados na seção **Proteção de dados pessoais**. O processamento ocorre em lotes. O arquivo ilegível excluído permanece somente no histórico; os 6.926 registros do STF integram a base atual, sem separação.

Os textos originais e a base canônica anterior permanecem separados e podem conter dados pessoais. A derivada protegida não exporta as colunas de texto original. Mascarar CPFs não constitui anonimização integral: outros dados pessoais continuam exigindo revisão. Não há publicação automática, exclusão por duplicatas, treinamento ou indexação no RAG.''',
      'privacidade_texto_jur':'''## 6. Dados pessoais, origem, versão e licença

A triagem considera candidatos a CPF com checksum válido, e-mail e campos de partes/contato. Não há varredura completa de objetos serializados nem garantia de anonimização. Relatores são distinguidos de partes processuais. Os relatórios não reproduzem decisões ou nomes de partes.

A verificação posterior confirmou 18 de 20 arquivos por hash e tamanho. As referências e licenças declaradas estão no quadro de atualização e no notebook 05. Os dois casos sem correspondência permanecem identificados, sem atribuir licença por nome. A classificação temática do conteúdo, especialmente STF, ainda requer revisão.''',
      'conclusao_texto_jur':'''## 8. Conclusão atualizada

Os achados da auditoria permanecem no escopo dos registros originais. A conclusão incorpora a estruturação concluída, a revisão do notebook 04 e a rastreabilidade verificada no notebook 05. O shard adicional STF permanece fora das contagens.''',
      'graficos_texto_eda':'''## 5. Gráficos exploratórios

Os gráficos descrevem somente os 179.812 registros legíveis do lote original. A origem de 18 arquivos foi confirmada posteriormente, sem mudar essas contagens. Os 6.926 registros do STF com sinais de tema trabalhista integram a base atual, junto com TST e TRTs, sem separação. Limitações de coleta, privacidade e pertinência permanecem; barras de ausência não são uma nota jurídica.''',
      'conclusao_texto_eda':'''## 6. Conclusão e relação com as etapas posteriores

A etapa 03 criou a base canônica e as derivadas protegidas. O notebook 04 contém inferência de conteúdo, sinais temáticos e critérios versionados de seleção, além das partições recalculadas após o PLN. O 05 registra as origens confirmadas. As verificações são automáticas; seus limites de cobertura e os alertas estão documentados.''',
      'conclusao_texto_estrutura':'''## 6. Conclusão e próximos passos atualizados

A estruturação e o mascaramento de CPFs estão concluídos para os 179.812 registros dos 19 arquivos ativos. Os originais permanecem separados da derivada protegida. A origem de 18 arquivos ativos foi confirmada; a origem individual do JSON TST continua pendente. O arquivo ilegível está somente no histórico, e os 6.926 registros do STF integram a base atual, sem separação.

As verificações automáticas de conteúdo, privacidade, relações e partições estão no notebook 04. O JSON TST continua sem correspondência de origem e recebe um alerta computacional. A seleção de candidatos usa critérios documentados; os textos protegidos e seus próprios offsets são a referência para uma integração futura. Não houve treinamento ou alteração do RAG legislativo.''',
      'quarentena_texto_estrutura':'''## 3. Repetições e histórico de exclusão

O arquivo ilegível foi excluído do escopo ativo por solicitação da pessoa usuária, preservando o original e o manifesto histórico. Nenhum registro legível foi removido. O notebook apresenta os 19 arquivos efetivamente estruturados.

O índice `sinais_repeticao.parquet` e as contagens abaixo descrevem a versão anterior ao mascaramento, preservada como histórico. O painel automático posterior apresenta cópias candidatas e partições recalculadas após o PLN, mantendo todos os registros e suas origens.''',
      'graficos_texto_estrutura':'''## 5. Gráficos e diagnóstico da preparação

Os gráficos mostram a normalização e os sinais técnicos da base canônica anterior ao mascaramento. O diagnóstico da proteção de CPFs é apresentado na seção **Proteção de dados pessoais**. As contagens não são notas de qualidade jurídica, e os motivos de revisão podem se sobrepor.'''}
    for cell in nb['cells']:
        ident=cell.get('id')
        if ident in overrides:cell['source']=overrides[ident].splitlines(keepends=True)
        if ident=='conclusao_jur':
            cell['source']="from worker.ingestao.jurisprudencia import presentation\nconclusao_jur = presentation.conclusion(ROOT_JUR, 'auditoria', report.conclusion(REPORT_JUR_VIEW, resumo_jur, perfis_jur))\n(REPORT_JUR_VIEW/'conclusao_auditoria_atualizada.md').write_text(conclusao_jur,encoding='utf-8')\ndisplay(Markdown(conclusao_jur))\n".splitlines(keepends=True)
        if ident=='conclusao_eda':
            cell['source']="from worker.ingestao.jurisprudencia import presentation\nconclusao_eda_atual = presentation.conclusion(ROOT_JUR, 'eda', (EDA_DIR/'conclusao_eda.md').read_text(encoding='utf-8'))\n(EDA_DIR/'conclusao_eda_atualizada.md').write_text(conclusao_eda_atual,encoding='utf-8')\ndisplay(Markdown(conclusao_eda_atual))\n".splitlines(keepends=True)
        if ident=='conclusao_estrutura':
            cell['source']="from worker.ingestao.jurisprudencia import presentation\nconclusao_estrutura_atual = presentation.conclusion(ROOT_JUR, 'estrutura', dataset.conclusion(ROOT_JUR))\n(STRUCT_REPORT/'conclusao_estrutura_atualizada.md').write_text(conclusao_estrutura_atual,encoding='utf-8')\ndisplay(Markdown(conclusao_estrutura_atual))\n".splitlines(keepends=True)
    if stage=='auditoria':
        for cell in nb['cells']:
            source=''.join(cell['source']);ident=cell.get('id')
            if ident=='configuracao_jurisprudencia':
                source=source.split('\n# Escopo ativo do notebook 01')[0]
                source+="\n# Escopo ativo do notebook 01\nfrom worker.ingestao.jurisprudencia import presentation\nresumo_jur,perfis_jur,REPORT_JUR_VIEW=presentation.audit_scope(ROOT_JUR,REPORT_JUR,resumo_jur,perfis_jur)\n"
            if ident=='inventario_jur':
                needle="df_inventario_jur = pd.read_csv(REPORT_JUR/'inventario_arquivos.csv', keep_default_na=False)"
                if 'df_inventario_jur=df_inventario_jur[' not in source:
                    source=source.replace(needle,needle+"\ndf_inventario_jur=df_inventario_jur[df_inventario_jur['arquivo'].isin([p['arquivo'] for p in perfis_jur])].copy()")
            if ident=='graficos_jur':source=source.replace('report.figures(REPORT_JUR,','report.figures(REPORT_JUR_VIEW,')
            if ident=='titulo_auditoria_jurisprudencia':
                source=source.replace('**20 arquivos fornecidos**: JSONL do TRT-13, JSON aninhado do TST e 18 arquivos Parquet.','**19 arquivos no escopo ativo**: JSONL do TRT-13, JSON aninhado do TST e 17 arquivos Parquet. O arquivo ilegível foi excluído da análise ativa por solicitação da pessoa usuária; o original e o inventário histórico foram preservados.')
            if ident=='privacidade_texto_jur':
                source=source.replace('18 de 20 arquivos','18 dos 19 arquivos ativos').replace('no quadro de atualização e no notebook 05','no notebook 05').replace('Os dois casos sem correspondência permanecem identificados','O JSON TST permanece sem correspondência exata no escopo ativo')
            cell['source']=source.splitlines(keepends=True)
    if stage=='estrutura':
        nb['metadata']['kernelspec']=dict(display_name='Python (.venv lex_clt.ai)',language='python',name='lex-clt-ai')
        for cell in nb['cells']:
            if cell.get('id')=='config_estrutura':
                source=''.join(cell['source']).split('\n# Escopo ativo da estruturação')[0]
                source=source.replace("print('Dados protegidos:',DATA_DIR)","print('Base canônica original (sem mascaramento):',DATA_DIR)")
                source+="\n# Escopo ativo da estruturação\nresumo_estrutura=dict(resumo_estrutura)\nresumo_estrutura['arquivos_em_quarentena_historico']=resumo_estrutura['arquivos_em_quarentena']\nresumo_estrutura['arquivos_em_quarentena']=0\nresumo_estrutura['arquivos_ativos']=len(manifestos_estrutura)\nassert resumo_estrutura['arquivos_ativos']==19\nassert all(m['arquivo']!='train-00002.parquet' for m in manifestos_estrutura)\nassert sum(m['registros'] for m in manifestos_estrutura)==resumo_estrutura['registros']\n"
                cell['source']=source.splitlines(keepends=True)
            if cell.get('id')=='quarentena_estrutura':
                cell['source']="print('Escopo ativo:',len(manifestos_estrutura),'arquivos legíveis.')\nprint('Manifesto histórico preservado em:',STRUCT_REPORT/'quarentena_manifesto.json')\ndisplay(pd.read_csv(STRUCT_REPORT/'repeticoes_pos_limpeza.csv'))\ngrupos_processuais=dataset.build_process_groups(ROOT_JUR)\ndisplay(pd.Series(grupos_processuais,name='indice_processual_anterior_mascaramento').to_frame())\nprint('Grupos anteriores ao mascaramento; reavaliar coincidências na versão protegida antes da avaliação.')\n".splitlines(keepends=True)
        nb['cells']=[c for c in nb['cells'] if c.get('id') not in ('protecao_dados_pessoais_texto','protecao_dados_pessoais','pln_leve_texto_estrutura','pln_leve_estrutura')]
        markdown='''## Proteção de dados pessoais

Nesta etapa da limpeza, uma **derivada separada** substitui sequências compatíveis com CPF por `[CPF_REMOVIDO]`, antes de qualquer chunking, embedding ou envio ao modelo. São tratados CPF formatado, sem pontuação e com separadores reconhecidos, inclusive DV inválido. Outros números de 11 dígitos também podem ser mascarados de forma conservadora. O processo CNJ contínuo de 20 dígitos é preservado.

A base canônica apresentada nas tabelas anteriores permanece preservada e contém texto original/limpo. Ela **não é a exportação protegida**. O CSV e os novos shards Parquet usam somente `texto_protegido`, `ementa_protegida` e metadados selecionados, também mascarados. Não incluem `texto_original`, `texto_limpo`, `ementa_original`, partes, JSONs brutos ou URLs da origem. Há um ID de linhagem para localizar o original no armazenamento separado; não há mapa de CPF para reidentificação.

O CSV é UTF-8, com cabeçalho, campos entre aspas conforme necessário e quebras de linha preservadas dentro do texto. Sua validação relê todas as linhas, confere a quantidade de registros e procura resíduos do padrão nos textos e metadados de conteúdo. Os IDs técnicos são verificados separadamente pelo formato estrito (hash hexadecimal/código de arquivo), preservando a linhagem; sequências numéricas dentro de hashes não são tratadas como CPFs. As estatísticas não exibem CPFs reais. CSV pode ser grande; Parquet permite leitura em lotes. A derivada continua ignorada pelo Git.

**Limite:** este é mascaramento de CPFs, não anonimização completa. Nomes, endereços, e-mails e outras informações não são integralmente tratados por esta regra; formas por extenso ou ofuscações não reconhecidas podem escapar. A exportação não representa liberação automática de publicação ou indexação. Uma futura entrada do RAG deve partir da versão protegida, após as revisões restantes. O chunking deve recalcular offsets sobre `texto_protegido`, sem reutilizar offsets da versão anterior.

Para executar novamente a transformação completa: `.venv/Scripts/python.exe scripts/proteger_cpf_jurisprudencia.py`. A célula abaixo lê os resultados já processados; o parâmetro pesado fica desligado por padrão.
'''
        code="""from worker.ingestao.jurisprudencia import privacy
EXECUTAR_PROTECAO_CPF=False
if EXECUTAR_PROTECAO_CPF:
    PROTECTION_REPORT,resumo_protecao=privacy.run(ROOT_JUR)
else:
    PROTECTION_REPORT,resumo_protecao=privacy.load(ROOT_JUR)
assert resumo_protecao['registros']==resumo_estrutura['registros']
assert resumo_protecao['validacao']['registros_csv_relidos']==resumo_estrutura['registros']
assert resumo_protecao['validacao']['sequencias_compativeis_residuais']==0
assert not (set(resumo_protecao['colunas']) & privacy.FORBIDDEN)
print('Conferindo o hash do CSV protegido completo (aproximadamente 4,1 GB)...')
assert audit.hash_file(ROOT_JUR/resumo_protecao['csv'])==resumo_protecao['csv_sha256']
print('Integridade do CSV protegido confirmada.')
display(pd.Series({k:resumo_protecao[k] for k in ('registros','registros_com_mascaramento','sequencias_compativeis_mascaradas','csv_bytes','originais_preservados','anonimizado_integralmente')},name='protecao_cpf').to_frame())
display(pd.Series(resumo_protecao['mascaramentos_por_campo'],name='substituicoes_por_campo').to_frame())
display(pd.Series(resumo_protecao['validacao'],name='validacao_csv').to_frame())
print('CSV protegido:',ROOT_JUR/resumo_protecao['csv'])
print('Relatório:',PROTECTION_REPORT)
print('Colunas exportadas:',resumo_protecao['colunas'])
print(resumo_protecao['limites'])
"""
        index=next(i for i,c in enumerate(nb['cells']) if c.get('id')=='quarentena_texto_estrutura')
        nb['cells'][index:index]=[dict(cell_type='markdown',id='protecao_dados_pessoais_texto',metadata={},source=markdown.splitlines(keepends=True)),
            dict(cell_type='code',id='protecao_dados_pessoais',metadata={},source=code.splitlines(keepends=True),execution_count=None,outputs=[])]
        from .pln_presentation import DESCRIPTION,result_code
        index=next(i for i,c in enumerate(nb['cells']) if c.get('id')=='quarentena_texto_estrutura')
        pln_text='## Limpeza leve e normalização conservadora, preservando o texto jurídico (PLN)\n\n'+DESCRIPTION
        pln_text+='\n\nA transformação integral foi executada por `scripts/preprocessar_pln_leve_jurisprudencia.py`. A célula lê os resultados salvos, sem reprocessar o corpus.'
        nb['cells'][index:index]=[dict(cell_type='markdown',id='pln_leve_texto_estrutura',metadata={},source=pln_text.splitlines(keepends=True)),
            dict(cell_type='code',id='pln_leve_estrutura',metadata={},source=result_code().splitlines(keepends=True),execution_count=None,outputs=[])]
    ident='situacao_atual_'+stage
    nb['cells']=[c for c in nb['cells'] if c.get('id') not in (ident,'tema_atual_eda','privacidade_resultado_eda')]
    source="from worker.ingestao.jurisprudencia import presentation\ncontexto_atual = presentation.context(ROOT_JUR)\ndisplay(Markdown(presentation.status_markdown(contexto_atual)))\n"
    if stage!='auditoria':
        nb['cells'].insert(2,dict(cell_type='code',id=ident,metadata={},source=source.splitlines(keepends=True),execution_count=None,outputs=[]))
    if stage=='estrutura':
        nb['cells'][2]['source']="from worker.ingestao.jurisprudencia import presentation\ncontexto_atual=presentation.context(ROOT_JUR)\ndisplay(Markdown(presentation.structure_status_markdown(contexto_atual)))\n".splitlines(keepends=True)
    if stage=='eda':
        nb['metadata']['kernelspec']=dict(display_name='Python (.venv lex_clt.ai)',language='python',name='lex-clt-ai')
        for cell in nb['cells']:
            if cell.get('id')=='config_eda':
                source=''.join(cell['source']).split('\n# Resumo de apresentação do escopo ativo')[0]
                source=source.replace("display(pd.Series({k:v for k,v in resumo_eda.items() if not isinstance(v,dict)},name='resultado').to_frame())",'')
                source+="\n# Resumo de apresentação do escopo ativo\nfrom worker.ingestao.jurisprudencia import presentation\nresumo_eda,ARQUIVOS_ATIVOS_EDA=presentation.eda_scope(ROOT_JUR,resumo_eda)\ndisplay(pd.Series({k:v for k,v in resumo_eda.items() if not isinstance(v,dict)},name='resultado_escopo_ativo').to_frame())\n"
                cell['source']=source.splitlines(keepends=True)
            if cell.get('id')==ident:
                cell['source']="contexto_atual=presentation.context(ROOT_JUR)\ndisplay(Markdown(presentation.eda_status_markdown(contexto_atual)))\n".splitlines(keepends=True)
            if cell.get('id')=='composicao_eda':
                cell['source']="display(pd.read_csv(EDA_DIR/'composicao_tribunais.csv'))\ninventario_ativo_eda=pd.read_csv(AUDIT_DIR/'inventario_arquivos.csv')\ninventario_ativo_eda=inventario_ativo_eda[inventario_ativo_eda['arquivo'].isin(ARQUIVOS_ATIVOS_EDA)].copy()\nassert len(inventario_ativo_eda)==19\nassert inventario_ativo_eda['registros_lidos'].sum()==resumo_eda['registros_legiveis']\ndisplay(inventario_ativo_eda[['arquivo','status','registros_lidos','features_raiz']])\n".splitlines(keepends=True)
            if cell.get('id')=='texto_datas_eda':
                cell['source']="display(presentation.eda_frame(EDA_DIR/'texto_por_arquivo.csv',ARQUIVOS_ATIVOS_EDA))\ndisplay(pd.read_csv(EDA_DIR/'distribuicao_anual.csv'))\ndisplay(pd.read_csv(EDA_DIR/'histograma_texto.csv'))\n".splitlines(keepends=True)
            if cell.get('id')=='categorias_eda':
                cell['source']="display(presentation.eda_frame(EDA_DIR/'ausencias_logicas_por_arquivo.csv',ARQUIVOS_ATIVOS_EDA))\ndisplay(presentation.eda_frame(EDA_DIR/'categorias_top30_por_arquivo.csv',ARQUIVOS_ATIVOS_EDA).head(80))\ndisplay(pd.read_csv(EDA_DIR/'indicadores_agregados.csv'))\n".splitlines(keepends=True)
        privacy_code="""display(Markdown('**Proteção de CPFs concluída na etapa 03.** Estes resultados são da derivada protegida; os gráficos de texto desta EDA continuam descrevendo a versão original.'))
protecao_cpf_eda=contexto_atual['cpf_protection']
assert protecao_cpf_eda['registros']==resumo_eda['registros_legiveis']
assert protecao_cpf_eda['validacao']['sequencias_compativeis_residuais']==0
display(pd.Series({k:protecao_cpf_eda[k] for k in ('registros','registros_com_mascaramento','sequencias_compativeis_mascaradas','originais_preservados','anonimizado_integralmente')},name='resultado_protecao_cpf').to_frame())
display(pd.Series(protecao_cpf_eda['validacao'],name='validacao_csv_protegido').to_frame())
"""
        index=next(i for i,c in enumerate(nb['cells']) if c.get('id')=='conclusao_texto_eda')
        nb['cells'].insert(index,dict(cell_type='code',id='privacidade_resultado_eda',metadata={},source=privacy_code.splitlines(keepends=True),execution_count=None,outputs=[]))
        source="""# Triagem temática por metadados; não é classificação jurídica do conteúdo.
tema_atual=pd.read_csv(contexto_atual['review_dir']/'tribunais_tema.csv')
assert int(tema_atual['registros'].sum())==contexto_atual['audited']['registros_lidos']
display(Markdown('**Triagem temática por metadados — aprofundamento inicial.** Jurisdição trabalhista e ramo declarado são evidências para revisão, não aprovação do conteúdo. Documentos STF sem evidência temática permanecem pendentes. Não foi feita classificação semântica dos textos.'))
display(tema_atual)
print('STF no lote original:')
display(tema_atual[tema_atual['tribunal'].eq('STF')])
fig,ax=plt.subplots(figsize=(10,4))
totais_tema=tema_atual.groupby('triagem_tematica')['registros'].sum().sort_values()
nomes={'jurisdicao_trabalhista_revisar_conteudo':'Jurisdição trabalhista: revisar conteúdo','ramo_trabalhista_declarado_revisar':'Ramo trabalhista declarado: revisar','pertinencia_nao_confirmada':'Pertinência não confirmada'}
ax.barh([nomes.get(k,k) for k in totais_tema.index],totais_tema.values,color='#4477aa')
ax.set_xlabel('Registros do lote original');ax.set_title('Triagem temática por metadados — não é parecer jurídico')
fig.tight_layout();fig.savefig(EDA_DIR/'triagem_tematica_metadados.png',dpi=140);plt.show()
"""
        index=next(i for i,c in enumerate(nb['cells']) if c.get('id')=='sobreposicoes_texto_eda')
        nb['cells'].insert(index,dict(cell_type='code',id='tema_atual_eda',metadata={},source=source.splitlines(keepends=True),execution_count=None,outputs=[]))
    if stage=='eda':
        from .notebook_layout import eda_layout
        nb=eda_layout(nb)
    from .automation_presentation import add_panel
    nb=add_panel(nb,stage)
    from .notebook_preservation import save_notebook
    save_notebook(path,nb)
