# Baseline do classificador de tipo de documento e fase

Lote **repojus-trt10-2024** (RepoJus, revisão `91aa953b3c`, sha256 `453efb25ce42…`, CC BY 4.0). Divisão por processo, semente `lexai-divisao-v1`. **Rótulos provisórios**: classe processual publicada pelo tribunal, até o rótulo-ouro da Cientista de dados.

| Divisão | recurso_ordinario | agravo_peticao | embargos_declaracao | agravo_instrumento | acao_originaria |
|---|---:|---:|---:|---:|---:|
| treino | 9096 | 2864 | 3815 | 427 | 276 |
| validacao | 2004 | 602 | 857 | 93 | 71 |
| teste | 1952 | 550 | 799 | 84 | 78 |

Rótulos corrigidos para `embargos_declaracao` pelo cabeçalho (metadado do tribunal usa a classe do recurso embargado): acao_originaria: 55, agravo_instrumento: 34, agravo_peticao: 336, recurso_ordinario: 1740. A variante `regras_cabecalho` fica parcialmente circular nessa classe.

## Teste (divisão congelada por hash do processo)

| Variante | Acurácia | F1 macro | F1 recurso_ordinario | F1 agravo_peticao | F1 embargos_declaracao | F1 agravo_instrumento | F1 acao_originaria | Fase: acurácia | Fase trocada | ECE | Abstenção: cobertura / acurácia |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| majoritaria | 0.564 | 0.144 | 0.721 | 0.000 | 0.000 | 0.000 | 0.000 | 0.651 | 1209 | — | — |
| regras_cabecalho | 0.985 | 0.942 | 0.995 | 0.972 | 0.991 | 0.953 | 0.800 | 0.720 | 42 | — | — |
| tfidf_lr_texto_completo | 0.986 | 0.968 | 0.992 | 0.983 | 0.985 | 0.906 | 0.975 | 0.718 | 10 | 0.011 | 99.9% / 98.67% (limiar 0.49) |
| tfidf_lr_sem_cabecalho | 0.980 | 0.953 | 0.987 | 0.972 | 0.981 | 0.873 | 0.950 | 0.717 | 23 | 0.016 | 99.9% / 98.03% (limiar 0.44) |

## Matriz de confusão — tfidf_lr_sem_cabecalho, teste (linha = verdadeiro)

| | recurso_ordinario | agravo_peticao | embargos_declaracao | agravo_instrumento | acao_originaria |
|---|---:|---:|---:|---:|---:|
| recurso_ordinario | 1929 | 8 | 9 | 5 | 1 |
| agravo_peticao | 7 | 535 | 3 | 3 | 2 |
| embargos_declaracao | 11 | 3 | 781 | 1 | 3 |
| agravo_instrumento | 8 | 4 | 0 | 72 | 0 |
| acao_originaria | 1 | 1 | 0 | 0 | 76 |

Registrado no MLflow como `classificador_tipo_fase` v1, alias `candidato`.
