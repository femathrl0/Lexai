# Proteção de dados pessoais na limpeza

O notebook `notebooks/02_jurisprudencia/03_limpeza_estruturacao_jurisprudencia.ipynb` inclui a seção **Proteção de dados pessoais**, após as regras de limpeza. A transformação produz uma derivada separada em Parquet e um CSV UTF-8 consolidado, mantendo o texto original e a base canônica anteriores separados. Nenhum original é sobrescrito.

## Executar

```powershell
.\.venv\Scripts\python.exe scripts/proteger_cpf_jurisprudencia.py
.\.venv\Scripts\python.exe scripts/run_preparacao_jurisprudencia.py --etapa estrutura
```

O primeiro comando processa os 19 shards canônicos em lotes, com checkpoints identificados pelo hash do código e do manifesto de entrada. O segundo atualiza as saídas do notebook com o relatório final. A célula do notebook permite executar a transformação definindo `EXECUTAR_PROTECAO_CPF=True`; por padrão, lê o resultado já salvo.

## Regras

Sequências compatíveis com CPF são substituídas por `[CPF_REMOVIDO]`, incluindo 11 dígitos sem pontuação, a forma pontuada e separadores de espaço/hífen reconhecidos. A regra não exige dígitos verificadores válidos: números inválidos que pareçam CPF também são ocultados. Por ser conservadora, pode mascarar outros números de 11 dígitos, como telefones. CNJ contínuo de 20 dígitos não é mascarado por essa regra.

Todos os campos de conteúdo selecionados são tratados, incluindo texto, ementa e metadados textuais como relator/órgão/classe. `registro_id` e `arquivo_id` são identificadores técnicos; seus formatos estritos são validados separadamente e permanecem estáveis para joins de linhagem. Uma sequência de dígitos dentro de um hash não é interpretada como CPF. Não é produzido um mapa que associe números pessoais aos marcadores.

O CSV exporta `texto_protegido`, `ementa_protegida` e metadados selecionados. Exclui textos originais, colunas de texto limpo sem mascaramento, partes, processo original livre, URLs e objetos brutos serializados. `processo_cnj` é preservado como texto. O CSV deve ser consumido com suporte a campos entre aspas e quebras de linha internas; linhas físicas não equivalem a registros. Para processamento em lotes, prefira os shards Parquet. Textos extensos podem exceder o limite de caracteres de uma célula do Excel.

## Localização e validação

Na execução concluída, foram exportados e relidos **609.872 registros**. Houve **13.294 substituições** de sequências compatíveis em **5.695 registros**, somando os campos tratados; isso não é a quantidade de CPFs distintos ou de pessoas. A validação final encontrou **zero resíduos dos padrões documentados** nos campos de conteúdo. O CSV tem 12.951.131.339 bytes (aproximadamente 13 GB). A suíte do projeto passou com 93 testes, incluindo quatro testes de proteção. O código exato da transformação executada foi preservado junto ao relatório.

`data/processed/jurisprudencia/protecao_cpf/ativa.json` aponta para o diretório protegido e os relatórios. O CSV se chama `jurisprudencia_cpf_protegido.csv`. Os dados processados são ignorados pelo Git; não houve publicação.

O CSV inteiro é relido para conferir quantidade e procurar resíduos dos padrões tratados nos textos/metadados de conteúdo. Identificadores técnicos são validados separadamente. O relatório registra contagens por campo, hashes, origem da base e limitações, sem expor CPFs reais. O ponteiro ativo só é gravado depois da validação final; arquivos parciais não são uma entrega concluída.

## Limites e uso posterior

Mascarar CPF não é anonimizar integralmente um documento. Nomes, endereços, e-mails e informações que permitam identificar pessoas continuam exigindo revisão. CPFs por extenso ou com ofuscação não reconhecida podem escapar. Ausência de resíduos do padrão documentado não prova ausência de todos os CPFs possíveis. Os originais separados continuam contendo os dados recebidos.

Uma futura entrada do RAG deve partir da versão protegida, após as demais revisões. O chunking precisa calcular offsets nessa versão. Os grupos/partições da triagem inicial são anteriores ao mascaramento; coincidências textuais criadas pelas substituições precisam ser reavaliadas antes de usar a derivada em um experimento. Não houve criação de embeddings, indexação ou avaliação do modelo nesta etapa.
