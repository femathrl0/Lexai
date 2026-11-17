"""EDA inicial dos agregados integrais da auditoria, sem republicar decisões."""
from pathlib import Path
from collections import Counter
import json
from datetime import datetime, timezone

from .audit import hash_file, write_json, write_csv
from .report import load


def run(root):
    root = Path(root)
    audit_folder, summary, profiles = load(root)
    n = summary['registros_lidos']
    if sum(p['registros_lidos'] for p in profiles) != n or sum(c['registros_lidos'] for c in summary['tribunais_observados']) != n:
        raise ValueError('Agregados de auditoria inconsistentes.')
    folder = root/'dados/relatorios/jurisprudencia/eda'/summary['inventario_sha256']/hash_file(__file__)
    folder.mkdir(parents=True, exist_ok=True)
    courts = [{**c, 'proporcao_registros_legiveis': c['registros_lidos']/n if n else None} for c in summary['tribunais_observados']]
    years, quality, hist = Counter(), Counter(), Counter()
    categories, coverage, texts = [], [], []
    weighted_chars = 0
    for p in profiles:
        size = p['registros_lidos']
        years.update({int(k):v for k,v in p.get('datas_ano',{}).items()})
        quality.update(p['qualidade'])
        hist.update(p.get('histograma_chars',{}))
        stats = p.get('tamanho_texto',{})
        if stats.get('n'):
            weighted_chars += stats['media']*stats['n']
        texts.append({'arquivo_id':p['arquivo_id'],'arquivo':p['arquivo'],'status':p['status_leitura'],
                      'registros':size, **stats})
        for key in ('sem_texto_principal','identificador_documental_ausente','processo_ausente',
                    'julgamento_ou_assinatura_ausente','publicacao_ausente'):
            coverage.append({'arquivo_id':p['arquivo_id'],'arquivo':p['arquivo'],'indicador':key,
                             'registros_com_ausencia':p['qualidade'].get(key,0), 'denominador':size,
                             'proporcao_ausencia':p['qualidade'].get(key,0)/size if size else None})
        for field, counts in p.get('categorias',{}).items():
            for value, count in counts.items():
                categories.append({'arquivo_id':p['arquivo_id'],'feature':field,'categoria_declarada':value,
                                   'ocorrencias':count,'escopo':'Top 30 por arquivo; não representa domínio completo'})
    year_rows = [{'ano':year,'registros':years[year]} for year in sorted(years)]
    quality_rows = [{'indicador':k,'ocorrencias':v,'denominador_registros_legiveis':n} for k,v in sorted(quality.items())]
    write_csv(folder/'composicao_tribunais.csv',courts)
    write_csv(folder/'distribuicao_anual.csv',year_rows,['ano','registros'])
    write_csv(folder/'ausencias_logicas_por_arquivo.csv',coverage)
    write_csv(folder/'texto_por_arquivo.csv',texts)
    write_csv(folder/'categorias_top30_por_arquivo.csv',categories,['arquivo_id','feature','categoria_declarada','ocorrencias','escopo'])
    write_csv(folder/'indicadores_agregados.csv',quality_rows)
    write_csv(folder/'histograma_texto.csv',[{'faixa_caracteres':k,'registros':hist[k]} for k in ('vazio','<80','80-499','500-1999','2000-9999','>=10000')])
    numeric_courts = [c for c in courts if c['tribunal']!='não identificado']
    dominant = max(numeric_courts,key=lambda c:c['registros_lidos']) if numeric_courts else None
    output = {'executado_em_utc':datetime.now(timezone.utc).isoformat(),'inventario_sha256':summary['inventario_sha256'],
              'codigo_eda_sha256':hash_file(__file__),'registros_legiveis':n,
              'arquivos_nao_integralmente_lidos':summary['arquivos_com_falha_ou_leitura_parcial'],
              'media_caracteres_global_ponderada':weighted_chars/n if n else None,
              'tribunal_mais_frequente':dominant, 'registros_com_ano_interpretavel':sum(years.values()),
              'julgamento_ou_assinatura':'Ano de assinatura é alternativa identificada da auditoria; não é promovido a julgamento.',
              'quantis_globais':'Não calculados: quantis por arquivo não podem ser promediados para formar quantis globais.',
              'categorias':'Top 30 declarado por arquivo; sem normalização temática ou classificação trabalhista automática.',
              'base_arquivos_sha256':{name:hash_file(audit_folder/name) for name in
                  ('resumo_auditoria.json','perfis_arquivos.json','inventario.json','duplicatas_resumo.csv')}}
    write_json(folder/'resumo_eda.json',output)
    declaration = root/'dados/raw/jurisprudencia/origens_declaradas.json'
    if declaration.exists():
        write_json(folder/'origem_declarada.json',json.loads(declaration.read_text(encoding='utf-8')))
    note = f'''# Conclusão da EDA inicial

Foram explorados os agregados dos **{n:,} registros legíveis** da auditoria. Os arquivos de origem não foram relidos nem alterados nesta etapa. Há **{summary['arquivos_com_falha_ou_leitura_parcial']} arquivo com leitura não concluída**; sua quantidade real não é conhecida.

## Composição e representatividade

{f"O tribunal mais frequente é {dominant['tribunal']}, com {dominant['registros_lidos']:,} registros ({dominant['proporcao_registros_legiveis']:.1%} das linhas legíveis)." if dominant else 'Não foi possível determinar o tribunal predominante.'} A concentração reflete a composição dos arquivos recebidos e não a distribuição de todas as demandas trabalhistas. Registros de arquivos diferentes podem representar versões ou textos repetidos. Não se deve comparar grupos como amostras equivalentes.

O STF abrange temas variados. A jurisdição declarada não substitui classificação temática. O campo ramo_direito, quando disponível, é informação da origem, não uma classificação revisada pelo projeto.

## Textos, datas e completude

Os tamanhos são medidos em caracteres. A média global é ponderada pelas quantidades de registros de cada arquivo; as medianas/p95 continuam por arquivo, sem produzir um quantil global fictício. Há {quality['sem_texto_principal']:,} registros sem texto principal segundo as prioridades da auditoria e {quality['texto_com_html']:,} com marcação HTML detectada.

O ano está disponível em {sum(years.values()):,} registros, usando julgamento ou assinatura conforme a origem. Falhas e ausências de datas devem ser examinadas antes de estudar tendências temporais. As categorias exportadas são top 30 por campo/arquivo; a omissão de uma classe nesse recorte não comprova sua ausência no corpus.

## Decisões para limpeza e estruturação

1. Unificar nomes e tipos de metadados preservando as diferenças entre julgamento, publicação e assinatura.
2. Preservar o texto original e criar uma versão limpa separada; remover somente artefatos de apresentação, sem retirar negações, números ou dispositivos legais.
3. Manter repetições sinalizadas. Mesmo processo não significa documento duplicado; não apagar registros automaticamente por texto ou processo.
4. Tratar registros sem texto, tribunal não identificado, formato RTF e origem pendente como casos a revisar, com motivos explícitos.
5. Não apresentar a base estruturada como anonimizada, licenciada para redistribuição ou aprovada juridicamente. Antes do RAG, definir privacidade, pertinência temática e particionamento por grupos relacionados.

Esta EDA é inicial e usa estatísticas auditadas, não mineração de mérito jurídico nem confirmação de representatividade. A etapa 03 criará uma base padronizada rastreável com flags de qualidade, sem indexação automática.
'''
    (folder/'conclusao_eda.md').write_text(note,encoding='utf-8')
    write_json(root/'dados/relatorios/jurisprudencia/eda/eda_ativa.json',{'pasta':str(folder.relative_to(root))})
    return folder, output


def figures(folder):
    import pandas as pd
    import matplotlib.pyplot as plt
    folder = Path(folder)
    courts=pd.read_csv(folder/'composicao_tribunais.csv')
    years=pd.read_csv(folder/'distribuicao_anual.csv')
    hist=pd.read_csv(folder/'histograma_texto.csv')
    missing=pd.read_csv(folder/'ausencias_logicas_por_arquivo.csv')
    fig,axes=plt.subplots(2,2,figsize=(15,10))
    axes[0,0].barh(courts['tribunal'],courts['proporcao_registros_legiveis']*100,color='#4477aa')
    axes[0,0].set_title('Composição por tribunal — linhas antes de deduplicação')
    axes[0,0].set_xlabel('% dos registros legíveis')
    if len(years): axes[0,1].bar(years['ano'],years['registros'],color='#228866')
    axes[0,1].set_title('Distribuição anual — julgamento ou assinatura')
    axes[0,1].set_ylabel('Registros com data interpretável')
    axes[1,0].bar(hist['faixa_caracteres'],hist['registros'],color='#cc9944')
    axes[1,0].set_title('Tamanho do texto disponível')
    axes[1,0].set_xlabel('Caracteres; ementa pode ser o texto disponível')
    axes[1,0].tick_params(axis='x',rotation=20)
    aggregate=missing.groupby('indicador')[['registros_com_ausencia','denominador']].sum()
    values=100*aggregate['registros_com_ausencia']/aggregate['denominador']
    names={'sem_texto_principal':'Texto principal','identificador_documental_ausente':'ID documental de origem',
           'processo_ausente':'Processo','julgamento_ou_assinatura_ausente':'Julgamento/assinatura','publicacao_ausente':'Publicação'}
    axes[1,1].barh([names.get(i,i) for i in values.index],values.values,color='#cc5544')
    axes[1,1].set_title('Ausência de informações lógicas (não nota jurídica)')
    axes[1,1].set_xlabel('% dos registros legíveis')
    fig.tight_layout();fig.savefig(folder/'eda_inicial.png',dpi=150)
    return [fig]
