# Métricas finais — conjuntos de teste congelados

Commit `e270f3a28384` · conjunto de teste de legislação: **inalterado** · portão de regressão: **aprovado**.

| Modelo | Estágio | Versão | Métrica principal | Erro grave | Relatório |
|---|---|---|---|---|---|
| classificador_tipo_fase | em uso | `classificador_tipo_fase@regras_cabecalho@0004` | f1_macro 0.942 | fase_trocada 10 | [classificador_tipo_baseline.md](classificador_tipo_baseline.md) |
| classificador_tipo_fase.candidato_tfidf | candidato | `TF-IDF + LR v1 sem cabeçalho (candidato)` | f1_macro 0.951, ece 0.015 | fase_trocada 14 | [classificador_tipo_baseline.md](classificador_tipo_baseline.md) |
| segmentador.candidato_tfidf | candidato | `TF-IDF + LR com posição (candidato, 3.000 acórdãos)` | f1_macro 0.924 | — | [segmentador.md](segmentador.md) |
| resultado_pedido | em uso | `resultado_pedido@formula-dispositivo@2026-11-27` | f1_macro 0.982 | troca_grave 1 | [resultado_pedido.md](resultado_pedido.md) |
| reranker | em uso | `BAAI/bge-reranker-v2-m3@953dc6f6` | ndcg@5 0.956 | — | [benchmark_rerankers.md](benchmark_rerankers.md) |
| extrator_campos.numero_processo | em uso | `extrator_campos@regex-campos@2026-11-27` | acerto 0.985, inventado 0.007 | — | [extrator_campos.md](extrator_campos.md) |
| extrator_campos.relator | em uso | `extrator_campos@regex-campos@2026-11-27` | acerto 0.966, inventado 0.021 | — | [extrator_campos.md](extrator_campos.md) |
| extrator_campos.data_julgamento | em uso | `extrator_campos@regex-campos@2026-11-27` | acerto 0.820, inventado 0.035 | — | [extrator_campos.md](extrator_campos.md) |
| intencao_guarda | em uso | `intencao_guarda@guardas.verificar_entrada` | f1_macro 1.000 | erros_graves 0 | [intencao.md](intencao.md) |

Rótulos: prata (metadados e fórmulas do tribunal) ou rascunho, até o rótulo-ouro da Cientista de dados e o aceite da Curadoria. O verificador NLI está no relatório de calibração (pares-ouro v1).
