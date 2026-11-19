# 0003 — Baseline de cada tarefa de ML

Data: 19/11/2026 · Responsável: Eng. de ML e MLOps (Felipe) · Par: Cientista de dados (Laisa) · Issue #3

**Contexto.** O manual exige "baseline sempre primeiro; o modelo maior só entra se vencer na validação". Antes de treinar qualquer coisa é preciso fixar, para cada tarefa do worker, qual é o baseline, contra quem ele será comparado, com que métrica e qual erro é grave. Sem isso cada candidato novo é comparado a um alvo móvel. A taxonomia de rótulos e o rótulo-ouro são da Cientista de dados (#2, #9); enquanto não existem, os baselines rodam em rótulos provisórios, marcados como tal no MLflow (`dados.provisorio`).

**Decisão.** Cada tarefa tem um baseline simples, um candidato maior e uma regra de promoção comum: o candidato só substitui o baseline se ganhar **≥ 2 pontos de F1 macro (ou da métrica principal) na validação** e **não aumentar nenhum erro grave**. Empate fica com o mais simples, que é mais barato em memória (orçamento em [`treino/relatorios/memoria_latencia_m4.md`](../../treino/relatorios/memoria_latencia_m4.md)).

| Tarefa | Baseline | Candidato maior | Métrica principal | Erro grave (meta zero) | Dados para começar |
|---|---|---|---|---|---|
| Tipo de documento e fase (RF03) | Regras sobre o cabeçalho (classe processual) **e** TF-IDF + regressão logística | BERTimbau + LoRA | F1 por classe e macro; acurácia da fase | Fase trocada (execução ↔ conhecimento) | Acórdãos públicos do TRT-10 (RepoJus), rótulo = classe processual, até o rótulo-ouro. Resultado: [`classificador_tipo_baseline.md`](../../treino/relatorios/classificador_tipo_baseline.md) |
| Extração de campos (partes, datas, valores, pedidos) | Regras: número CNJ, datas `dd/mm/aaaa`, valores `R$`, linhas `RECLAMANTE:`/`RECLAMADO:` | BERTimbau para reconhecimento de entidades | Acerto por campo; cobertura | Prazo ou data errados | Acervo anotado no Label Studio (Eng. de dados + Cientista) |
| Resultado por pedido | Regras no dispositivo ("julgo procedente/improcedente", "dou/nego provimento") + quem recorreu | TF-IDF + LR por frase do dispositivo; depois BERTimbau | Acurácia por pedido; nº de resultados invertidos | Resultado invertido (procedente ↔ improcedente) | Dispositivos anotados por pedido; casos armadilha da Cientista |
| Intenção (guarda de escopo) | Padrões ("devo", "vale a pena recorrer", "o que eu faço") + TF-IDF de caracteres + LR | BERTimbau | Recall de pedido de aconselhamento com precisão mínima | Aconselhamento não desviado | Casos de `avaliacao/dados/integracao/casos_guardrails_entrada.jsonl` + casos armadilha |
| Segmentação (relatório, fundamentação, dispositivo) | Regras do Eng. de dados (`worker/leitura/segmentador.py`) | Rotulação de frases (TF-IDF + LR com posição; depois BERTimbau) | Acerto por parte | Dispositivo cortado (o resultado fica sem fonte) | Documentos com as partes marcadas |
| Reranker (RF06) | Sem reranker: ordem do RRF (híbrido) | Cross-encoders pré-treinados; ajuste fino só com ganho nos pares-ouro | nDCG@5 nos pares-ouro | — (custo: latência por pergunta) | Perguntas de legislação aprovadas até os pares-ouro. Resultado: [`benchmark_rerankers.md`](../../treino/relatorios/benchmark_rerankers.md) |
| Verificador (RNF03/RNF04) | Sobreposição lexical (frase × trecho citado) com limiar | Cross-encoder NLI pré-treinado (mDeBERTa-v3 XNLI) | F1 por classe (sustenta, contradiz, não trata) | Frase sem apoio aprovada | ~30 pares (frase, trecho) da Cientista (#52) |

Toda avaliação é por classe, com a matriz de confusão no MLflow; o limiar de abstenção é escolhido na validação para uma precisão-alvo nas previsões aceitas e aplicado no teste (RNF04: abaixo do limiar o app diz "não identificado").

**Alternativa descartada.** Começar direto pelo BERTimbau com LoRA em todas as tarefas: daria o modelo "mais forte" sem saber se ele é necessário. Ocupa memória que o orçamento do worker reserva para a LLM, e um ganho de F1 sem baseline não pode ser atribuído ao modelo nem ao rótulo.
