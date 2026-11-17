# Avaliação avançada de chunking

O notebook 04 preserva as três bases (janela de 500 tokens, parágrafo, seção/tema) e acrescenta três híbridas determinísticas: agrupamento mínimo de parágrafos, teto por seção/tema e expansão do parágrafo para sua seção. Não há LLM ou geração de embeddings nesta execução. O recuperador comum é BM25.

## Métrica principal: Cobertura@T

Consumir o ranking em ordem até T, cortando o último trecho se exceder o orçamento. A cobertura é a fração dos caracteres da evidência esperada presente no contexto entregue. Usam-se T=500, 1.000, 2.500 e 5.000; o resumo principal é a **média por pergunta em T=2.500**. Uma seção enorme no primeiro resultado consome T com seu prefixo, sem pular para outro resultado mais conveniente ao gabarito. As curvas podem se cruzar: a preferência depende do orçamento de uso.

`cobertura_por_pergunta_orcamento.csv` guarda cada ponto; `cobertura_2500_resumo.json` e `.csv` guardam o resumo principal. O nome anterior do arquivo de curvas é mantido como compatibilidade. `suporte_fracao` e `cobertura_T` representam a mesma fração contínua; suporte completo@5 e documento@5 são secundários.

## Evidências e coordenadas

O gabarito usa intervalos `[inicio, fim)` sobre o documento-base inteiro **antes do chunking**, na versão protegida utilizada no experimento. O corpus inteiro é preservado em `documentos_base.parquet`. Cada documento e o arquivo do corpus têm SHA-256. `original_reference(documento, inicio, fim, secao)` registra o hash integral, o hash da fatia e o espaço de coordenadas. As posições não são offsets locais de chunks.

Os arquivos brutos anteriores ao PLN podem conter HTML, normalização e dados pessoais com posições diferentes. Seus offsets não são tratados como se fossem da derivada protegida. Referências nesse espaço são rejeitadas sem um mapa explícito de transformação; o protocolo não inventa tal correspondência.

A fração de suporte é a cobertura dos caracteres da evidência pela união dos intervalos recuperados. Sobreposições do contexto e do próprio gabarito são unidas antes da contagem. Evidências múltiplas são ponderadas pelo comprimento; basta a melhor alternativa válida. A métrica binária de suporte completo continua disponível separadamente.

## Contexto com o mesmo orçamento

Os budgets são 500, 1.000, 2.500 e 5.000 tokens BGE-M3. A busca considera até 50 candidatos positivos. A montagem segue o ranking, entrega primeiro o núcleo do trecho e depois eventual expansão, deduplica intervalos e conta o texto realmente concatenado, incluindo separadores. Quando não cabe, usa um prefixo explícito e registra o corte. Não há seleção de contexto com base no gabarito.

Um corpus com poucos resultados pode fornecer menos tokens que o orçamento; ambos os números são registrados. Essa curva não é a mesma coisa que a recuperação direta do top 5. Cortar para montar o contexto também não é truncamento por encoder.

## Unidades e híbridas

- Parágrafo mínimo: alvo de 128 tokens dentro da mesma seção reconhecida. Sobras podem ficar menores; parágrafos grandes não são truncados.
- Seção com teto: blocos divididos em até 500 tokens, com preferência por fronteiras textuais.
- Expansão: os mesmos parágrafos são indexados; a seção é apenas contexto adicional, sem vetores de pais.

A auditoria registra unidades acima de 512/8.192 tokens, risco incluindo tokens especiais, método de fronteira, temas ambíguos e seções/temas não identificados. Ausência de classificação é distinta de ambiguidade. As frações são por unidade; estratégias que não classificam esses campos têm valor não aplicável, não zero.

Todas as unidades indexadas devem reconstruir exatamente o documento-base. A contagem de vetores planejados é igual à quantidade de unidades indexáveis; a contagem efetivamente gerada é zero porque a execução é lexical.

## Pareamento e falhas

Vitórias, empates e derrotas usam a diferença de suporte por pergunta, estratégia e orçamento. O bootstrap percentil usa 2.000 reamostragens de perguntas inteiras, com seed `20261114`; os dois resultados de cada par são mantidos juntos. O intervalo de 95% não tem correção por múltiplas comparações e não elimina dependências semânticas entre perguntas.

Os diagnósticos distinguem documento errado, trecho sem evidência no documento correto, evidência atravessando fronteira, perda de suporte sob corte **simulado** em 512/8.192 e seção incompatível com um rótulo esperado. Sem anotação de seção, esse erro não é inferido. Como nenhum encoder roda, o truncamento real fica não aplicável. Os controles fictícios exercitam as fórmulas e não estimam qualidade no corpus real.

`fragmentacao_unidades_truncamento.json` resume as taxas. Fragmentação é a proporção de perguntas cuja alternativa suficiente escolhida contém pelo menos um intervalo contínuo atravessando várias unidades. Duas evidências independentes em parágrafos diferentes podem exigir duas unidades sem que haja fragmentação. As unidades mínimas são calculadas por cobertura de intervalos; o tamanho do prefixo necessário no ranking é registrado separadamente e inclui os distratores anteriores à prova.

A taxa simulada de truncamento conta perguntas anotadas com perda de alguma evidência após o corte em 512/8.192, não simplesmente unidades maiores que o limite. A fração perdida também é guardada. Uma evidência no prefixo retido não sofre truncamento, mesmo se a unidade for longa. `taxa_truncamento_encoder_real` é nula na execução BM25. `evidencias_por_pergunta.json` permite auditar os denominadores e os casos individuais.

## Ajuste, congelamento e teste

A divisão determinística por famílias temáticas usa aproximadamente 80% das 30 perguntas para ajuste e 20% para teste. O modo padrão consulta apenas ajuste. Como as 30 perguntas já foram expostas exploratoriamente antes deste protocolo, o histórico é registrado: a reserva prospectiva não é apresentada como teste cego inédito.

```powershell
.\.venv\Scripts\python.exe scripts/run_chunking_jurisprudencia.py
.\.venv\Scripts\python.exe scripts/run_chunking_jurisprudencia.py --congelar-protocolo
.\.venv\Scripts\python.exe scripts/run_chunking_jurisprudencia.py --teste-final
```

O congelamento exige uma execução de ajuste concluída. O teste final exige o protocolo congelado, evidências para todas as perguntas reservadas e identidade de código, corpus, tokenizador, CSV e parâmetros. Um marcador impede executar novamente o teste, inclusive depois de interrupção, sem apagar o registro histórico. O notebook não congela nem avalia o final automaticamente.

As saídas atuais são selecionadas por `reports/jurisprudencia/chunking_avancado/ativa.json`. O CSV de perguntas recebido não fornece evidências de referência, portanto as curvas e comparações de qualidade reais ainda não são mensuráveis. Isso não é erro de execução nem empate entre estratégias.
