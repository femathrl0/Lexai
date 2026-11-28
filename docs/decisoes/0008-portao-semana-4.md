# 0008 — Portão da semana 4: sistema multiagentes (proposta para a reunião)

Data: 27/11/2026 · Conduz: Felipe, issue #28 · **Status: decidido em 27/11/2026 (sem reunião).**

**Contexto.** Critério: *um PDF entra pela fila e o app recebe, frase a frase, uma explicação com fontes, ponta a ponta, rodando no CI sobre o conjunto de teste.*

| Critério | Evidência | Situação |
|---|---|---|
| PDF pela fila até as frases | `worker/pipelines.processar_documento`: leitura → segmentos → tipo/fase, campos e resultado → frases sobre o documento com o trecho literal → explicação da lei dos pedidos pelo multiagente (verificador como último portão) | Atende |
| Rodando no CI | `tests/worker/test_fluxo_documento.py` (PDF real, Redis falso, agentes simulados) no CI de todo PR; `tests/integracao/` com RQ e Redis reais no workflow `integracao.yml` | Atende |
| "Sobre o conjunto de teste" | O teste usa um acórdão sintético; os 3.504 acórdãos de teste entram nas avaliações do extrator, do resultado e do segmentador | Parcial |
| App recebendo por SSE | O backend repassa o pub/sub por SSE; a tela de envio e resumo (#26) e a retomada do SSE pelo banco ainda não existem | **Pendente (#26)** |
| Entregas de ML (#24) | Extrator de campos ([relatório](../../treino/relatorios/extrator_campos.md)), resultado do recurso e por pedido, intenção (regras seguem em uso, [relatório](../../treino/relatorios/intencao.md)), registro em uso com MLflow e rollback (`worker/modelos/registro.py`, `treino/promover.py`) | Atende; calibração por temperatura não foi necessária no tipo (ECE 0,016) e fica para o modelo de resultado quando ele entrar |

**Decisão proposta.** **Aprovado com desvio**: o fluxo do documento roda ponta a ponta no CI; falta a tela (#26) e a persistência em `resultados` para o SSE retomar. Pedidos e resultado por pedido seguem com rótulo prata até o 2º lote anotado (#15).

**Alternativa descartada.** Esperar a tela do app para aprovar: o critério é sobre o fluxo pela fila, e a tela não muda o que o worker publica.

### Registro da decisão

**Sem reunião de portão (orientação do grupo, 27/11/2026):** a decisão abaixo foi registrada pelo responsável pelos portões, Felipe (Eng. de ML e MLOps), com base na evidência desta página.

- Semana 4 (#28): **aprovado com desvio** — o PDF passa pela fila e vira frases com fonte no CI. Desvio: tela do app e retomada do SSE pelo banco ficam com a #26.
