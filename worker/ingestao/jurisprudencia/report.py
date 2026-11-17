"""Tabelas, gráficos e conclusão da auditoria; não recebe conteúdo bruto."""
from pathlib import Path
import json
from collections import Counter
import csv
import hashlib


DEFINITIONS = {
    'tribunal': 'Tribunal declarado pelo produtor; confrontar com campos estruturados de órgão.',
    'base': 'Coleção ou base de coleta declarada; não representa uma partição de avaliação do nosso projeto.',
    'unique_key': 'Chave candidata do documento no produtor; namespace e unicidade exigem conferência.',
    'doc_id': 'Identificador candidato do documento; não confundir com número do processo.',
    'documento_id': 'Identificador documental informado pela origem.',
    'pje_id': 'Identificador PJe declarado na coleta; não foi consultado no sistema de origem.',
    'dg_unique': 'Chave alternativa declarada; sem garantia automática de equivalência a outras chaves.',
    'normalized_hash': 'Fingerprint de normalização declarado; algoritmo depende de documentação da origem.',
    'numero_processo': 'Número de processo informado; formato é analisado sem validar dígito verificador.',
    'processo': 'Referência ao processo; pode haver diversas decisões legítimas por processo.',
    'processo_normalizado': 'Número de processo normalizado pelo produtor; preservado sem alteração.',
    'orgao_julgador': 'Órgão julgador informado; pode haver valores ausentes ou convenções diferentes.',
    'orgao_julgador_colegiado': 'Órgão colegiado declarado na coleta.',
    'relator': 'Agente público indicado como relator, distinto das partes processuais.',
    'nomRelator': 'Nome do agente público relator declarado pela fonte.',
    'data_julgamento': 'Data de julgamento declarada; formatos e consistência são auditados.',
    'data_publicacao': 'Data de publicação declarada; não confundir com data de captura.',
    'data_assinatura': 'Data de assinatura; utilizada como alternativa identificada, sem equiparação automática ao julgamento.',
    'ano_assinatura': 'Ano de assinatura informado pelo produtor; campo mantido como recebido.',
    'data_julgamento_provavel': 'Data provável estimada pelo produtor; não substitui automaticamente a data de julgamento.',
    'data_julgamento_complementar': 'Data complementar informada pelo produtor; requer documentação semântica.',
    'dtaJulgamento': 'Data de julgamento no esquema aninhado do TST.',
    'dtaPublicacao': 'Data de publicação no esquema aninhado do TST.',
    'ementa': 'Resumo/ementa do julgado. Não implica disponibilidade de inteiro teor.',
    'inteiro_teor': 'Texto integral declarado; pode conter marcação ou conteúdo a estruturar.',
    'texto_integral': 'Texto integral no esquema normalizado fornecido.',
    'texto_busca': 'Texto preparado para busca pelo produtor; não é necessariamente o inteiro teor.',
    'txtInteiroTeor': 'Inteiro teor declarado no JSON aninhado do TST.',
    'inteiroTeorHtml': 'Versão HTML do inteiro teor; marcação é preservada na auditoria.',
    'texto_chars': 'Tamanho de texto informado pelo produtor; o relatório mede independentemente o texto selecionado.',
    'texto_sha256': 'Hash declarado de texto; confrontado com candidatos brutos sem presumir algoritmo de normalização.',
    'sha256_ementa': 'Hash declarado da ementa; confrontado com os bytes UTF-8 do campo recebido.',
    'sha256_arquivo_fonte': 'Hash da fonte referenciada pelo produtor; não é necessariamente o hash deste container recebido.',
    'classe': 'Classe processual declarada; padronização de categorias fica para estruturação/EDA.',
    'tipo': 'Tipo declarado; pode ser escalar ou objeto conforme a origem.',
    'tipo_decisao': 'Tipo de decisão declarado pelo produtor.',
    'partes': 'Dados de partes processuais; exige revisão de privacidade antes de exposição ou indexação.',
    'data_json': 'Objeto serializado como string; campos internos não foram expandidos nesta auditoria.',
    'metadata_extra_json': 'Metadados serializados como string; não expandidos nesta etapa.',
    'scraped_at': 'Instante de coleta declarado; não equivale à data de julgamento/publicação.',
    'captured_at': 'Instante de captura declarado; depende do relógio e método do coletor.',
    'spider_name': 'Nome do coletor informado; não identifica, sozinho, repositório, versão ou licença.',
    'url': 'Endereço declarado da fonte; não acessado nem autenticado automaticamente.',
    'fonte': 'Origem declarada; pode ser URL ou descrição da fonte.',
    'arquivo_fonte': 'Nome da fonte anterior informado pelo produtor; preservar para linhagem.',
    'registro': 'Contêiner principal de um registro no JSON do TST.',
    'destaques': 'Contêiner de destaques da resposta de coleta; não é uma decisão independente.',
    'schema_version': 'Versão de esquema declarada no registro; não é versão/commit do dataset.',
    'registro.orgao.sigla': 'Sigla do tribunal no objeto de órgão do TST; usada na identificação estrutural.',
    'registro.orgao.nome': 'Nome do tribunal declarado no objeto de órgão.',
    'fonte_tabela': 'Tabela/coleção de origem declarada; não é garantia de identificação do repositório.',
}


def enrich_dictionary(folder):
    path = Path(folder)/'dicionario_features.csv'
    with path.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        leaf = row['feature'].split('.')[-1]
        row['descricao_tecnica'] = DEFINITIONS.get(row['feature'], DEFINITIONS.get(leaf,
            'Campo original preservado; confirmar definição, domínio e unidade com a documentação do produtor.'))
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def schema_families(folder, profiles):
    rows=[]
    for p in profiles:
        signature=p.get('leitura',{}).get('schema_parquet') or json.dumps([
            {'feature':f['feature'],'tipos':sorted(f['tipos_observados'])} for f in p['features']],sort_keys=True)
        key=hashlib.sha256(signature.encode()).hexdigest()[:12] if p['features'] else 'indeterminado'
        rows.append({'arquivo_id':p['arquivo_id'],'arquivo':p['arquivo'],'familia_estrutural':key,
                     'features_raiz':p.get('quantidade_features_raiz',0),'registros_lidos':p['registros_lidos'],
                     'status':p['status_leitura']})
    with (Path(folder)/'familias_esquema.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return rows


def load(root):
    root = Path(root)
    pointer = json.loads((root/'dados/relatorios/jurisprudencia/auditoria/auditoria_ativa.json').read_text(encoding='utf-8'))
    folder = (root/pointer['pasta']).resolve()
    if not folder.is_relative_to((root/'dados/relatorios/jurisprudencia/auditoria').resolve()):
        raise ValueError('Caminho de relatório fora da pasta de auditoria.')
    return folder, json.loads((folder/'resumo_auditoria.json').read_text(encoding='utf-8')), json.loads((folder/'perfis_arquivos.json').read_text(encoding='utf-8'))


def conclusion(folder, summary, profiles):
    courts = ', '.join(f"{r['tribunal']}: {r['registros_lidos']:,}" for r in summary['tribunais_observados'])
    quality = Counter()
    for p in profiles:
        quality.update(p['qualidade'])
    failed = [p['arquivo'] for p in profiles if p['status_leitura'] != 'concluido']
    total = summary['registros_lidos']
    text = f'''# Conclusão da auditoria de jurisprudência

## Escopo e volume observado

Foram recebidos **{summary['arquivos_recebidos']} arquivos**, com **{summary['bytes_recebidos']/1024**3:.2f} GiB de bytes originais. A leitura percorreu integralmente **{summary['arquivos_concluidos']} arquivos**. Há **{summary['arquivos_com_falha_ou_leitura_parcial']} arquivos ausentes, com erro ou leitura parcial**.

Foram auditados **{total:,} registros legíveis**. Após comparar o registro inteiro em JSON canônico, foram observadas **{summary['registros_canonicos_distintos']:,} representações distintas**. Isso não representa uma seleção de decisões jurídicas únicas: registros diferentes podem pertencer ao mesmo processo ou reproduzir o mesmo texto.

Tribunais encontrados nos dados: **{courts}**. A identificação prioriza campos estruturados, incluindo `registro.orgao.sigla` no JSON aninhado do TST. Menções ao STF, TST ou a um TRT no corpo da decisão e o tribunal de origem no número do processo não identificam automaticamente o tribunal julgador. Hipóteses provenientes somente do nome do arquivo ficam identificadas no perfil.

## Integridade e arquivos com problemas

{'É necessário recuperar ou reenviar: **'+', '.join(failed)+'**.' if failed else 'Não houve erro impeditivo na leitura dos arquivos fornecidos.'} Registros inacessíveis não foram estimados pela quantidade de outros shards. Um arquivo Parquet com assinatura PAR1 pode, ainda assim, ter metadados ou páginas inválidos. Os originais não foram modificados nem reparados silenciosamente.

Os arquivos `train-00000`, `train-00001`, `train-00002` e `train-00005` são apenas os shards recebidos. A numeração não comprova que o split original esteja completo. Sufixos como `(1)` e `(2)` são nomes locais de download e não identificam datasets diferentes por si só.

## Esquemas, features e completude

Os esquemas são descritos por arquivo em `inventario_arquivos.csv`, `dicionario_features.csv` e nos perfis JSON. O JSON do TST contém objetos aninhados; features de raiz e caminhos aninhados são contabilizados separadamente para evitar uma comparação enganosa com colunas planas do Parquet.

Ausência da chave, valor nulo e valor vazio são medidos separadamente. Zero e `False` são dados preenchidos. A cardinalidade é exata somente até o limite operacional informado; quando o limite é atingido, a contagem é um limite inferior da amostra inicial, não uma estimativa do total.

Campos com conteúdo JSON armazenado como string, como `data_json` e `metadata_extra_json`, permanecem strings nesta auditoria; seus campos internos exigem uma etapa de estruturação própria. Listas e relações de partes também não são explodidas em novas linhas.

## Qualidade textual e datas

Há **{quality['sem_texto_principal']:,} registros sem texto principal utilizável** segundo a prioridade de campos documentada; **{quality['texto_curto_menor_80_chars']:,} textos não vazios com menos de 80 caracteres**, e **{quality['texto_com_html']:,} textos com marcação HTML detectada**. Esses indicadores são triagens e não regras automáticas de exclusão.

O campo de inteiro teor tem prioridade; quando ausente, a ementa pode ser usada como texto disponível. A disponibilidade de ementa não significa que exista inteiro teor. Os gráficos de tamanho incluem todos os registros legíveis e informam explicitamente caracteres, não tokens.

Datas de julgamento e publicação são avaliadas com os campos disponíveis. No TRT-13, `data_assinatura` é usada como alternativa identificada, sem afirmar que seja a data de julgamento. Datas futuras, datas não interpretáveis e publicação anterior ao julgamento/assinatura são alertas para conferência, não provas automáticas de erro jurídico.

Hash de texto declarado que não coincida com candidatos brutos pode resultar de algoritmo ou normalização não documentados. É necessário conferir o produtor antes de concluir que o texto está corrompido.

## Duplicação e risco de vazamento entre avaliações

São separados: registros integralmente idênticos após serialização canônica; textos iguais após normalizar espaços; chaves documentais candidatas repetidas; e múltiplos documentos do mesmo processo. O mesmo processo pode ter várias decisões válidas. As chaves de provedores distintos também podem usar namespaces diferentes. Nenhuma dessas verificações remove registros nesta etapa.

Os relatórios de grupos apresentam somente fingerprints e contagens, sem texto ou número de processo. Antes de dividir desenvolvimento e teste do RAG, revisar sobreposições de texto, documento e processo entre fontes. Os nomes `train` dos arquivos de origem não determinam a partição do nosso experimento.

## Dados pessoais e origem

A triagem detectou **{quality['texto_com_cpf_checksum_valido']:,} registros com sequência compatível com CPF de dígitos verificadores válidos** no texto e **{quality['texto_com_email_candidato']:,} com candidato a e-mail**. Podem existir falsos positivos e falsos negativos. Há também campos de partes ou contatos que exigem revisão específica. Relatores são agentes públicos identificados na fonte; não devem ser confundidos com partes processuais.

Não foi realizada anonimização. Hashes e fingerprints não garantem anonimato. A varredura considera o texto principal selecionado e campos explicitamente identificados; não substitui análise de todos os objetos e metadados embutidos. O notebook e os relatórios não reproduzem decisões, CPFs ou nomes de partes.

Os campos `fonte`, `url`, `spider_name`, os domínios e os hashes auxiliam a rastreabilidade, mas não comprovam a cadeia de coleta, autenticidade, licença, atualização ou representatividade. A pessoa usuária informou o Hugging Face como plataforma de origem dos Parquet. Faltam os nomes autor/dataset, URLs dos repositórios/dataset cards, licença e versão/commit da coleta para atestar a procedência dos datasets. O fato de serem decisões públicas não define, sozinho, as condições de redistribuição do conjunto.

## Parecer técnico e próximas etapas

**O conjunto está inventariado e auditado nos registros legíveis; ainda exige preparação antes da indexação em RAG.** A auditoria não autoriza juntar todos os arquivos sem resolver sobreposições, privacidade e diferenças de esquema.

1. Recuperar os arquivos de leitura problemática e solicitar os manifestos de origem, versão e licença de cada conjunto.
2. Definir um esquema comum com tribunal julgador, identificador documental, processo, órgão julgador, relator, datas, ementa, inteiro teor e origem. Preservar os campos originais e a linhagem.
3. Revisar HTML, vazios, possíveis problemas de codificação e divergências de hashes, mantendo textos brutos preservados.
4. Distinguir cópias, versões e decisões diferentes do mesmo processo antes da deduplicação. Não apagar por número de processo.
5. Definir tratamento de dados pessoais e condições de publicação antes de compartilhar textos ou índices.
6. Executar EDA temática e temporal para verificar pertinência trabalhista. **STF não equivale automaticamente a conteúdo trabalhista**; não foi feita classificação temática nesta auditoria.
7. Só depois preparar chunking, embeddings e avaliação. Agrupar documentos relacionados no particionamento para evitar vazamento de informação entre desenvolvimento e teste.
'''
    (Path(folder)/'conclusao_auditoria.md').write_text(text, encoding='utf-8')
    return text


def figures(folder, summary, profiles):
    import matplotlib.pyplot as plt
    import pandas as pd
    import numpy as np
    folder = Path(folder)
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    court_frame = pd.DataFrame(summary['tribunais_observados'])
    if not court_frame.empty:
        bars = axes[0, 0].bar(court_frame['tribunal'], court_frame['registros_lidos'], color='#4477aa')
        for bar, value in zip(bars, court_frame['registros_lidos']):
            axes[0, 0].text(bar.get_x()+bar.get_width()/2, value, f'{value:,}', ha='center', va='bottom', fontsize=9)
        axes[0, 0].margins(y=.18)
    axes[0, 0].set_title('Tribunais nos registros legíveis')
    axes[0, 0].set_ylabel('Registros; inclui possíveis sobreposições entre arquivos')
    labels = [p['arquivo_id'] for p in profiles]
    axes[0, 1].bar(labels, [p['registros_lidos'] for p in profiles], color=['#228866' if p['status_leitura']=='concluido' else '#cc5544' for p in profiles])
    axes[0, 1].set_title('Registros auditados por arquivo (IDs no inventário)')
    axes[0, 1].tick_params(axis='x', rotation=60)
    axes[0, 1].set_ylabel('Zero em arquivo ilegível significa quantidade desconhecida')
    years = Counter()
    lengths = Counter()
    for p in profiles:
        years.update({int(k): v for k,v in p.get('datas_ano', {}).items()})
        lengths.update(p.get('histograma_chars', {}))
    if years:
        axes[1, 0].bar(sorted(years), [years[k] for k in sorted(years)], color='#4477aa')
    axes[1, 0].set_title('Ano de julgamento ou assinatura disponível')
    axes[1, 0].set_ylabel('Registros com data interpretável')
    bins = ['vazio','<80','80-499','500-1999','2000-9999','>=10000']
    axes[1, 1].bar(bins, [lengths[k] for k in bins], color='#cc9944')
    axes[1, 1].set_title('Tamanho do texto principal selecionado')
    axes[1, 1].set_xlabel('Caracteres; ementa quando não há inteiro teor')
    axes[1, 1].tick_params(axis='x', rotation=20)
    fig.tight_layout()
    fig.savefig(folder/'auditoria_volume_tribunais.png', dpi=150)

    fig2, axes = plt.subplots(1, 2, figsize=(15, 7))
    quality = Counter()
    for p in profiles: quality.update(p['qualidade'])
    indicators = [('Sem texto principal','sem_texto_principal'), ('Texto com HTML','texto_com_html'),
                  ('Unicode de substituição','texto_com_replacement_unicode'), ('Sinal de mojibake','texto_com_sinal_mojibake'),
                  ('Data não interpretável','julgamento_ou_assinatura_nao_interpretavel'),
                  ('Data de julgamento/assinatura futura','julgamento_ou_assinatura_futura')]
    axes[0].barh([x[0] for x in indicators], [quality[x[1]] for x in indicators], color='#cc9944')
    axes[0].set_title('Sinais de qualidade — não são exclusões automáticas')
    axes[0].set_xlabel('Registros com o sinal; categorias podem se sobrepor')
    duplicates = pd.read_csv(folder/'duplicatas_resumo.csv')
    names = ['Registro canônico idêntico', 'Texto com espaços normalizados', 'Chave documental candidata', 'Mesmo processo (pode ser legítimo)']
    axes[1].barh(names, duplicates['repeticoes_excedentes'], color=['#cc5544','#cc9944','#4477aa','#9caab3'])
    axes[1].set_title('Repetições excedentes por critério — não somar critérios')
    axes[1].set_xlabel('n − 1 em cada grupo repetido')
    fig2.tight_layout()
    fig2.savefig(folder/'auditoria_qualidade_duplicatas.png', dpi=150)
    return [fig, fig2]
