# Verificação automática da preparação de jurisprudência

O fluxo dos três notebooks ativos usa regras executáveis, evidências e alertas computacionais. A seção de [verificação automática do notebook 03](../notebooks/02_jurisprudencia/03_limpeza_estruturacao_jurisprudencia.ipynb#verificacao-automatica) consolida o diagnóstico atual, incluindo o conteúdo do antigo 04. As evidências de origem do antigo 05 estão na seção de [fontes e proveniência](../notebooks/02_jurisprudencia/03_limpeza_estruturacao_jurisprudencia.ipynb#fontes-proveniencia). Os originais e as versões anteriores continuam preservados; não há exclusão física de registros ou publicação externa.

## Critérios e objetivos

`criterios_uso_recorte.json` registra o objetivo de RAG trabalhista, os critérios de inclusão e as propostas de avaliação. TST/TRTs são priorizados. Para STF, são exigidos pelo menos dois grupos de sinais lexicais em até 8.000 caracteres. O mínimo textual é de 80 caracteres. Rótulos de inteiro teor com menos de 500 caracteres são sinalizados. Os períodos observados são preservados; datas ausentes/futuras geram alertas, sem um corte cronológico arbitrário. O ajuste fino está desabilitado porque não foi solicitado.

Os critérios são técnicos e heurísticos. Não comprovam integralidade do documento ou pertinência jurídica. O tipo declarado pela fonte é separado do tipo inferido por tamanho e marcadores no prefixo.

## Resultados executados

- 609.872 registros verificados.
- 456.784 candidatos segundo os critérios automáticos; 456.750 na proposta consolidada de candidatos.
- 63 grupos estritos de cópias textuais candidatas, com 65 ocorrências excedentes; 10 grupos ligam arquivos distintos. Os registros e proveniências continuam disponíveis.
- 526.985 componentes de avaliação pós-PLN. A conferência independente não encontrou vínculos conhecidos de texto ou processo atravessando splits.
- 509 referências de amostras curtas, longas ou com alertas, selecionadas deterministicamente por arquivo/estrato.
- 17 campos JSON serializados auditados em até 32 registros por campo/arquivo, sem exibir valores internos.
- Oito URLs oficiais consultadas automaticamente: duas respostas HTTP 200; quatro HTTP 403; duas HTTP 405. O status HTTP não comprova equivalência documental.
- 104 testes do projeto passaram, e os cinco notebooks foram executados sem erros.

## Artefatos

`reports/jurisprudencia/automacao/ativa.json` aponta para os relatórios atuais. O índice de candidatos, tipos declarados/inferidos, alertas, cópias e partições fica em `data/processed/jurisprudencia/automacao/`, ignorado pelo Git. Ele é um índice lateral para join por `registro_id`, não outro conjunto de textos.

Os relatórios incluem política, cobertura de conteúdo, distribuição de tamanhos, recorte por tribunal, alertas, amostras por IDs, estrutura JSON serializada e consulta de fontes oficiais. A conferência independente está em `verificacao_independente_pos_pln.json`. Os hashes da base e do índice vinculam a execução à versão dos dados.

## Executar

```powershell
.\.venv\Scripts\python.exe scripts/verificar_jurisprudencia_automaticamente.py
.\.venv\Scripts\python.exe scripts/verificar_fontes_oficiais_jurisprudencia.py
```

O primeiro comando executa também as checagens independentes e a auditoria JSON por `src.jurisprudencia.automated_checks`. Em seguida, atualize os painéis. `scripts/revisar_jurisprudencia.py` também aponta para o fluxo automático atual.

## Estado das integrações

Há dataset local tratado, índices laterais e candidatos técnicos. Indexação, embeddings, publicação externa, comparação integral com conteúdo remoto e métricas de respostas de um modelo não foram executados por este módulo. Classificação semântica abrangente e avaliação com gabaritos são integrações adicionais. As limitações são registradas como alcance dos métodos, sem substituir evidência ausente por aprovação presumida.
