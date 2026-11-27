# Model card — resultado do recurso e por pedido (regras)

- **Estágio:** regras em uso (`worker/modelos/resultado_pedido.py`, limiar de abstenção 0,5).
- **Uso pretendido:** dizer se o recurso foi provido, parcialmente provido, desprovido ou não conhecido (conclusão do voto) e, por tópico da ementa, se o direito foi reconhecido. Sem fórmula clara: `nao_identificado` (o app manda conferir), nunca palpite.
- **Dados:** 17.118 acórdãos de um recurso só; rótulo prata = fórmula do ACORDAM; divisão por processo.
- **Baseline comparado:** majoritária (F1 0,19) e TF-IDF + LR na conclusão (F1 0,977, 5 trocas).
- **Métricas (teste):** **regras F1 0,982**, 31 abstenções, **1 troca provido ↔ desprovido**. [Relatório](../../treino/relatorios/resultado_pedido.md).
- **Erro grave:** troca entre ganhar e perder. Medido no recurso; por pedido não há ouro ainda.
- **Robustez a OCR:** as regras caem de 0,92 para 0,70 com 2% de ruído; o candidato de caracteres com aumento de ruído fica em 0,94 mas troca mais provido/desprovido em ruído baixo ([relatório](../../treino/relatorios/ruido_ocr.md)).
- **Limitações:** "sentença mantida" não diz quem ganhou; nível pedido precisa do rótulo-ouro da Cientista de dados.
- **Aprovação da Curadoria:** pendente.
