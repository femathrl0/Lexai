# 0009 — Portão da semana 5: multimodalidade (proposta para a reunião)

Data: 27/11/2026 · Conduz: Felipe, issue #35 · **Status: proposta; a decisão é do grupo.**

**Contexto.** Critério: *queda entre PDF e foto dentro do limite combinado; foto ruim recusada com pedido de nova foto.* O conjunto de fotos do grupo (#29) e os casos armadilha de foto (#30) não existem; a medição usou ruído de OCR sintético.

| Critério | Evidência | Situação |
|---|---|---|
| Foto ruim recusada com pedido de nova foto | `worker/leitura/imagem.py`: nitidez (Laplaciano) recusa antes do OCR; OCR com confiança < 0,6 ou sem texto também; o pipeline publica `Aviso(nova_foto)`. Testes com imagens sintéticas | Atende (limiares a calibrar nas fotos reais) |
| Queda PDF → foto no limite | Ruído sintético ([relatório](../../treino/relatorios/ruido_ocr.md)): com 2% de erro por caractere o resultado do recurso cai de 0,92 para 0,70 e o número do processo de 0,99 para 0,73; tipo cai 2 pontos | **Não atende** o limite proposto de 5 pontos |
| Ajuste com ruído | TF-IDF de caracteres com aumento de ruído: 0,94 de 0% a 10%, mas troca provido/desprovido 15 vezes contra 8 das regras em ruído baixo | Candidato; não entra pela 0004 sem decisão |
| Monitoramento (Evidently) | `treino/deriva.py` + workflow semanal; no log de exemplo com fotos simuladas, 57% das colunas derivam e o alerta dispara | Atende |

**Decisão proposta.** **Reprovado para foto** até: (1) o grupo tirar o conjunto de fotos (#29) e medir a taxa de erro de caracteres real; (2) combinar o limite de queda; (3) decidir entre regras e o candidato com aumento de ruído **só para documento de origem OCR**. Enquanto isso, documento lido por OCR com qualidade abaixo de 0,8 deve trazer o aviso de incerteza e o resultado do recurso como "confira no documento".

**Alternativa descartada.** Aprovar porque a recusa da foto ruim funciona: a queda medida mostra que uma foto *aceita* com ruído leve já troca o resultado, e esse é o erro grave do cargo.

### Registro da reunião (preencher)
- Data: ___ · Presentes: ___ · [ ] Aprovado · [ ] Aprovado com desvio · [ ] Reprovado — observações: ___
