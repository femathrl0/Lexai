# Robustez a ruído de OCR (sintético) — componentes em uso

2000 acórdãos de teste. Ruído sintético (aguarda o conjunto de fotos do grupo, #29). Limite proposto: queda ≤ 5%.

| Ruído por caractere | Tipo (acerto) | Tipo (abstenção) | Resultado (acerto) | Troca grave | Processo | Relator | Dentro do limite |
|---:|---:|---:|---:|---:|---:|---:|---|
| 0% | 0.985 | 0.001 | 0.923 | 0 | 0.985 | 0.964 | — |
| 2% | 0.965 | 0.009 | 0.697 | 1 | 0.731 | 0.745 | **não** |
| 5% | 0.913 | 0.046 | 0.488 | 1 | 0.452 | 0.490 | **não** |
| 10% | 0.834 | 0.110 | 0.222 | 0 | 0.208 | 0.221 | **não** |

## Ajuste com ruído — resultado do recurso no fim do acórdão

TF-IDF de caracteres + LR treinado com ruído sorteado em {0, 2%, 5%} (6000 acórdãos de treino, 1500 de teste), contra as regras no mesmo texto ruidoso.

| Ruído | Regras (acerto / troca grave) | Modelo com aumento (acerto / troca grave) |
|---:|---|---|
| 0% | 0.721 / 8 | 0.938 / 15 |
| 2% | 0.732 / 10 | 0.941 / 14 |
| 5% | 0.715 / 14 | 0.939 / 15 |
| 10% | 0.637 / 25 | 0.935 / 17 |
