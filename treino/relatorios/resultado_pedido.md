# Resultado: regras × modelo (resultado do recurso a partir da conclusão do voto)

Acórdãos usados/descartados: {'usado': 17118, 'sem_conclusao': 997, 'acordam_misto_ou_sem_formula': 2977, 'sem_acordam': 2678}. **Rótulo prata**: fórmula do ACORDAM, por recurso.

| Variante | F1 macro | Acurácia | F1 provido | F1 parcialmente_provido | F1 desprovido | F1 nao_conhecido | Abstenções | Troca provido ↔ desprovido |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| majoritaria | 0.186 | 0.594 | 0.000 | 0.000 | 0.745 | 0.000 | 0 | 265 |
| regras_conclusao | 0.982 | 0.980 | 0.962 | 0.981 | 0.993 | 0.991 | 31 | 1 |
| tfidf_lr_conclusao | 0.977 | 0.984 | 0.956 | 0.974 | 0.993 | 0.985 | 0 | 5 |

Teste = divisão congelada por hash do processo. A regra abstém quando a conclusão mistura resultados; o modelo nunca abstém (o limiar de abstenção é calibrado em `treino/calibracao.py`).
