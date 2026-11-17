# Verificação automática e prontidão da jurisprudência

A seção de [verificação automática do notebook 03](../notebooks/02_jurisprudencia/03_limpeza_estruturacao_jurisprudencia.ipynb#verificacao-automatica) consolida as verificações executadas após o PLN: critérios de uso/recorte, tipos declarados e inferidos, alertas, amostras por estrato, cópias textuais candidatas, partições e consulta de URLs oficiais.

O fluxo atual está descrito em [Verificação automática da preparação](verificacao_automatica_jurisprudencia.md). `reports/jurisprudencia/automacao/ativa.json` aponta para os relatórios atuais e o índice lateral de 609.872 registros. A base textual tratada permanece separada, em `data/processed/jurisprudencia/pln_leve/`.

Foram identificados 456.784 candidatos pelos critérios automáticos e 456.750 na proposta consolidada. Todos os registros e proveniências permanecem preservados. O índice contém 63 grupos estritos de cópias candidatas, e as partições pós-PLN passaram na checagem independente dos vínculos conhecidos.

A análise inclui 509 referências de amostras curtas, longas ou com alertas; 17 campos JSON serializados foram amostrados. A comparação antes/depois do PLN verificou os marcadores documentados. Os limites são computacionais: sinais heurísticos não comprovam mérito jurídico, identidade de acórdão ou anonimização completa.

As oito consultas a URLs oficiais registram apenas disponibilidade HTTP. Comparação integral do documento remoto, avaliação de respostas de um modelo e indexação são integrações adicionais não executadas por este módulo. O arquivo ilegível está apenas no histórico, fora dos 19 arquivos ativos.
