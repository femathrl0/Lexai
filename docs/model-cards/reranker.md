# Model card — reranker `BAAI/bge-reranker-v2-m3` (revisão `953dc6f6`)

- **Estágio:** em uso por fixação (`worker/modelos/em_uso.yml`); registrado no MLflow como `reranker` (alias `candidato`) por `treino/registrar_cross_encoders.py`. Pesos de terceiros, sem ajuste fino.
- **Uso pretendido:** reordenar os candidatos da busca híbrida (BM25 + BGE-M3, RRF) antes da Pesquisa escolher os trechos; a nota também decide se uma súmula/OJ toma a vaga de uma ementa (`nota_sumula` 0,5) e lê uma janela de 500 caracteres do trecho mais relevante.
- **Fora do escopo:** decidir sozinho se há fonte (isso é da Validação); textos em outro idioma.
- **Dados de avaliação:** perguntas de legislação aprovadas (dev 11, teste 9), conjunto de teste congelado (hash `7d094eddf4d3…`). Relevância **provisória** (referência aprovada = 2, demais = 0); a graduação 0–2 aguarda a Curadoria (`avaliacao/pares_ouro/reranker_legislacao_para_anotar.csv`).
- **Baseline comparado:** sem reranker (palavra-chave, denso, híbrido RRF) e dois rerankers menores.
- **Métricas (teste congelado):** nDCG@5 **0,956** (híbrido sem reranker 0,950; palavra-chave 0,419; mmarco 0,936; unicamp 0,885); Recall@3 1,00; MRR@10 0,929. Separação de pergunta sem resposta: AUC 1,00 na nota do 1º colocado (0,95 com resposta × 0,20 sem). [Relatório](../../treino/relatorios/benchmark_rerankers.md).
- **Calibração e limiar:** sem limiar de corte em uso (`nota_minima: null`); a nota separa bem as perguntas sem resposta, candidata a limiar de "sem fonte segura" depois da graduação.
- **Erros graves encontrados:** nenhum no teste de legislação; em jurisprudência a híbrida com reranker não supera a palavra-chave em hit@10 (0,18 × 0,24, decisão 0005).
- **Memória e latência no M4:** 568 M parâmetros, 3,75 GB após carga; 5,3 s p50 para 30 pares (MPS). É o segundo maior consumo do worker.
- **Limitações:** só legislação medida; 7 perguntas com resposta no teste; o ganho sobre o híbrido é pequeno (0,006 de nDCG@5).
- **Run do MLflow:** experimentos `benchmark_rerankers` e `registro_reranker`.
- **Aprovação da Curadoria:** pendente.
