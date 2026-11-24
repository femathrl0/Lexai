# corpus/jurisprudencia — recorte anonimizado para o buscador local

Recorte pequeno de jurisprudência trabalhista usado pelo `BuscadorLocal` do sistema multiagente
(`worker/evidencia/agentes/buscadores.py`) quando não há o banco pgvector. A demo e a bateria o carregam por padrão.

| Arquivo | O que é |
|---|---|
| `recorte_demo.jsonl` | Uma linha por documento: `id`, `tipo_fonte` (`sumula` ou `ementa`), `fonte` (rótulo citado ao lado da frase), `texto`, `versao` e, nas ementas, `tema` |
| `relatorio_recorte.json` | Origem e hash de cada fonte, contagens por tema, descartes por motivo e máscaras aplicadas (só contagens, nunca valores) |

Gerado por `uv run --group worker python -m worker.ingestao.jurisprudencia.recorte_demo` (precisa dos artigos em
`dados/processed` para montar o vocabulário do filtro de nomes). Os originais baixados ficam em
`dados/raw/jurisprudencia/`, fora do Git.

## Fontes

| Fonte | Versão | Licença | O que entra |
|---|---|---|---|
| Livro de Súmulas do TST (PDF oficial, `tst.jus.br/documents/10157/63003/Livro-Internet.pdf`) | sha256 `46321b2d8d04…`, edição de jul/2018 | Texto oficial (ato público) | 349 súmulas vigentes; canceladas e histórico de redações saem |
| RepoJus (`efaraneda/repojus`), partição TRT-10 2024 | revisão `91aa953b3c97…` | CC BY 4.0 | Só a **ementa** de recursos ordinários dos temas da bateria; até 25 por tema (203 no total) |

## Anonimização

1. **Cabeçalho nunca entra.** Do inteiro teor sai só o bloco da ementa; partes, advogados, relator e número do
   processo ficam de fora. O rótulo da fonte é `TRT-10, <classe>, julgado em <data> (ementa <hash curto>)`.
2. **Descarte por indício de dado pessoal.** A ementa inteira sai quando tem iniciais de nome ("L. V. H. S."),
   sufixo de empresa (LTDA, S.A., EIRELI), sigla de empregador conhecida (lista `ENTIDADES`), CID ou palavra com
   inicial maiúscula fora do vocabulário da legislação (provável nome próprio).
3. **Máscara** de CPF, CNPJ, número de processo, e-mail e telefone (`worker.evidencia.guardas.mascarar`) no que sobra.
4. Teste `tests/agentes/test_recorte_jurisprudencia.py` confere ids únicos, campos e zero resíduo desses padrões.

## Limitações

- O livro de súmulas é de 2018: súmulas editadas ou alteradas depois disso não estão aqui. Antes de uso fora da
  demo, trocar pela consulta oficial atual (fila `ingestao_juridica`, com aprovação da Curadoria).
- O filtro de nomes é conservador e baseado em regras: descarta muito (ver `relatorio_recorte.json`) e não prova
  ausência de dado pessoal. A amostra precisa da revisão da Curadoria antes de ir para o índice em uso.
- Ementa é resumo do caso concreto: o Agente de Análise a usa como exemplo de entendimento, não como regra geral.
