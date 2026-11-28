# Model card — extrator de campos (regras)

- **Estágio:** em uso (`worker/modelos/extrator_campos.py`, versão `regex-campos@2026-11-27`).
- **Uso pretendido:** número CNJ, classe, relator, turma, data do julgamento, papéis das partes, quem recorreu, valores citados e pedidos (tópicos da ementa).
- **Privacidade:** nunca extrai nome de parte nem de advogado (RNF01); das partes sai só o papel. Testado em `tests/modelos/test_extrator_resultado.py`.
- **Métricas (3.504 acórdãos de teste, referência prata = metadados do RepoJus):** número do processo 0,985 de acerto (0,7% inventado); relator 0,966 (2,1%); data do julgamento 0,820 (3,5%). Campos sem metadado só têm cobertura (classe 94%, pedidos 66%, valores 47%). [Relatório](../../treino/relatorios/extrator_campos.md).
- **Robustez a OCR:** com 2% de ruído por caractere o número do processo cai para 0,73 ([relatório](../../treino/relatorios/ruido_ocr.md)).
- **Limitações:** pedidos e valores sem rótulo-ouro (2º lote anotado, #15); só acórdãos.
- **Aprovação da Curadoria:** pendente.
