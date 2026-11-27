# Model card — segmentador (regras de marcadores; candidato TF-IDF + LR)

- **Estágio:** regras **em uso** (`worker/leitura/segmentador.py`); TF-IDF + LR com faixa de posição é **candidato** para texto sem títulos.
- **Uso pretendido:** separar relatório, fundamentação, dispositivo e outro (cabeçalho, ementa, declaração de voto) para o resultado ser lido do dispositivo e a explicação citar a parte certa.
- **Dados:** 3.000 acórdãos do RepoJus TRT-10 (2.465 com rótulo fraco confiável), divisão por processo. **Rótulo prata** pelos títulos das seções.
- **Métricas (teste, sem os títulos):** majoritária F1 0,18; regra de posição 0,60; **TF-IDF + LR 0,92** (acerto no dispositivo 0,88). Com títulos, a regra reproduz o rótulo por construção. [Relatório](../../treino/relatorios/segmentador.md).
- **Erro grave:** parágrafo do dispositivo lido como fundamentação ou o contrário (718 de 24.643 parágrafos no candidato).
- **Limitações:** sem sentenças de 1º grau no lote; rótulo prata. A Cientista de dados valida uma amostra antes de virar ouro.
- **Run do MLflow:** experimento `segmentador`.
- **Aprovação da Curadoria:** pendente.
