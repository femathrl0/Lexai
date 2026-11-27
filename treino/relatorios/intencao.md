# Intenção da guarda de entrada: regras × TF-IDF de caracteres + LR

Rascunho por molde: 486 casos (346 treino / 140 teste, divisão por molde) · 35 casos reais do repositório. **Rótulos do rascunho aguardam aceite.**

| Conjunto | Variante | F1 macro | Acurácia | Erros graves |
|---|---|---:|---:|---:|
| rascunho_teste | regras | 0.908 | 0.907 | 1 |
| rascunho_teste | tfidf_char_lr | 0.415 | 0.443 | 18 |
| casos_reais | regras | 1.000 | 1.000 | 0 |
| casos_reais | tfidf_char_lr | 0.555 | 0.600 | 1 |

**Decisão (0004):** regras continuam em uso (o modelo não vence nos casos reais).

Erro grave: caso concreto ou consulta individual tratado como pergunta informativa.
