# Segmentador: regras × modelo (acórdãos sem os títulos das seções)

2465 de 3000 acórdãos com rótulo fraco confiável; parágrafos treino 113299, validacao 23086, teste 24643. **Rótulo prata** (títulos das seções); a Curadoria e a Cientista de dados validam uma amostra antes de virar ouro.

| Variante | F1 macro | Acurácia | Acerto outro | Acerto relatorio | Acerto fundamentacao | Acerto dispositivo | Dispositivo trocado |
|---|---:|---:|---:|---:|---:|---:|---:|
| majoritaria | 0.184 | 0.582 | 0.000 | 0.000 | 1.000 | 0.000 | 3314 |
| regra_posicao | 0.596 | 0.806 | 0.763 | 0.000 | 0.949 | 0.655 | 1612 |
| tfidf_lr_texto_posicao | 0.924 | 0.934 | 0.904 | 0.941 | 0.955 | 0.883 | 718 |

Cortes da regra de posição (ajustados no treino): (0.2, 0.2, 0.9).

Com os títulos presentes, a regra de marcadores (`worker/leitura/segmentador.py`) reproduz o rótulo por construção; ela continua em uso para documento com títulos, e o modelo é o candidato para documento sem.
