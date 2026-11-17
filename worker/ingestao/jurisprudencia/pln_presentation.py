"""Descrição e painéis agregados do PLN leve; amostras reais permanecem locais."""

DESCRIPTION='''### Critérios da limpeza leve e normalização conservadora (PLN)

| Etapa | Procedimento e preservação |
| --- | --- |
| **Limpar a formatação** | Remover HTML reconhecido e converter entidades, inclusive `&nbsp;` sem tags. Corrigir espaços repetidos, mantendo limites de parágrafos, listas e títulos; conservar a numeração das listas ordenadas reconhecidas. |
| **Normalizar caracteres** | Aplicar Unicode **NFC** e uniformizar quebras de linha. Preservar acentos, pontuação, números e referências como `art. 482`, `§ 2º` e `Súmula 331`. |
| **Tratar ruído de extração** | Identificar linhas recorrentes de início/fim como candidatas a cabeçalho/rodapé, sem removê-las automaticamente. Sinalizar palavras partidas. Unir partes somente com origem PDF confirmada e palavra aprovada; preservar hífens legítimos, como em `pré-judicial`. Neste lote, a origem PDF não está confirmada, portanto não há junção automática. |
| **Auditar o resultado** | Contar vazios, ausências e duplicatas exatas. Comparar amostras antes/depois por invariantes e marcadores jurídicos. Preservar `ementa` e `inteiro_teor` separados; texto de busca e variantes também ficam identificados. |

**Evitar remover stopwords, acentos ou pontuação.** “Não” e “salvo” podem mudar o sentido da decisão. Esta etapa não faz lematização, stemming, classificação temática ou reescrita jurídica.

O processamento parte da derivada com CPFs mascarados. A decodificação HTML pode revelar números antes codificados, por isso o mascaramento é reaplicado aos textos normalizados. O original e a derivada anterior permanecem separados. As amostras reais são salvas somente em dados processados ignorados pelo Git: podem conter nomes ou outros dados pessoais, e não são exibidas nos relatórios do notebook.

Os candidatos a cabeçalho/rodapé são repetições exatas nas duas primeiras/últimas linhas, entre 8 e 200 caracteres, presentes em pelo menos 10 documentos. Isso é triagem, não prova de ruído. As regras preservam esses trechos e registram alertas computacionais, sem exclusão automática de repetições.
'''


def result_code():
    return """from worker.ingestao.jurisprudencia import light_nlp
PLN_REPORT,resumo_pln=light_nlp.load(ROOT_JUR)
assert resumo_pln['registros']==contexto_atual['structured']['registros']
assert resumo_pln['base_cpf_csv_sha256']==contexto_atual['cpf_protection']['csv_sha256']
assert resumo_pln['validacao_csv']['registros_csv_relidos']==resumo_pln['registros']
assert resumo_pln['validacao_csv']['residuos_padrao_cpf']==0
assert 'ementa' in resumo_pln['colunas'] and 'inteiro_teor' in resumo_pln['colunas']
assert (ROOT_JUR/resumo_pln['csv']).exists()
from worker.ingestao.jurisprudencia.pln_dataset import open_dataset as open_pln_dataset
assert open_pln_dataset(ROOT_JUR).count_rows()==resumo_pln['registros']
display(pd.Series(resumo_pln['indicadores'],name='auditoria_pln_leve').to_frame())
display(pd.Series(resumo_pln['operacoes'],name='campos_com_operacao').to_frame())
display(pd.read_csv(PLN_REPORT/'duplicatas_exatas.csv'))
bordas_pln=pd.read_csv(PLN_REPORT/'cabecalhos_rodapes_candidatos.csv')
display(bordas_pln.head(20))
print('Candidatos recorrentes por fingerprint, sem texto ou nomes; não removidos:',len(bordas_pln))
print('Amostras comparadas automaticamente:',resumo_pln['amostras'],'| reduções dos marcadores monitorados:',resumo_pln['indicadores']['amostras_com_marcadores_juridicos_reduzidos_revisar'])
print('Amostra antes/depois (não exibida):',ROOT_JUR/resumo_pln['amostra_local'])
print('CSV após PLN:',ROOT_JUR/resumo_pln['csv'])
print('Leitura somente dos shards: open_pln_dataset(ROOT_JUR); amostra antes/depois excluída do corpus.')
print('Relatório:',PLN_REPORT)
print(resumo_pln['politica_pdf'])
print('Limites: PLN de formato e regras documentadas; não comprova mérito jurídico, integralidade de documentos ou anonimização completa.')
# Exemplos sintéticos: sem nomes, números de processo ou CPFs reais.
exemplos_pln=['Na\\u0303o&nbsp;  aplicar art. 482; § 2º. Salvo Súmula 331.',
              '<h2>Título</h2><p>Não retirar.</p><ul><li>Salvo exceção.</li></ul>',
              'pré-judicial\\ntra-\\nbalhista']
display(Markdown('**Exemplos sintéticos antes/depois** — a amostra real permanece no arquivo local para revisão.'))
display(pd.DataFrame([{'antes':t,'depois':light_nlp.clean_light(t)[0]} for t in exemplos_pln]))
"""
