# Origens informadas e verificação dos downloads

Os dois repositórios informados pela pessoa usuária foram consultados na API oficial do Hugging Face:

| Dataset | Revisão consultada | Licença declarada |
| --- | --- | --- |
| [celsowm/jurisprudencias_br_full](https://huggingface.co/datasets/celsowm/jurisprudencias_br_full) | `fc61bf96c3516b8d749d3376a84641e4eb7e34b5` | CC BY 4.0 |
| [celsowm/jurisprudencias_br](https://huggingface.co/datasets/celsowm/jurisprudencias_br) | `8df8ce3e629f490a0c82edca1dbe98ca73c5ecc3` | CC BY 4.0 |

README, metadados e inventário remoto foram preservados em `reports/jurisprudencia/origens_huggingface/`. A licença é uma declaração do publicador e não substitui a revisão de privacidade ou direitos de terceiros. A revisão consultada também não prova a revisão usada no download original.

## Correspondências

Os arquivos locais `train-00000.parquet`, `train-00001.parquet` e `train-00005.parquet` correspondem por tamanho e SHA-256 aos arquivos publicados em `jurisprudencias_br_full` e em `full/` de `jurisprudencias_br`. A listagem remota contém 16 shards, mas o lote local original contém apenas quatro `train-*`; não foram baixados automaticamente os demais.

Com as referências complementares, **18 de 20 arquivos** estão confirmados:

| Lote local | Fonte confirmada | Revisão consultada | Evidência |
| --- | --- | --- | --- |
| 14 `part-*` (TRT-10, TRT-17, TST) | [efaraneda/repojus](https://huggingface.co/datasets/efaraneda/repojus) | `91aa953b3c976a8688135dea49cf6644f7732243` | SHA-256, bytes e linhas do manifesto v3, esquema 3.0.0, de 30/10/2026 |
| `jurisprudencia_trt13.jsonl` | [zeraulalmeida/Jurisprudencia_TRT_13](https://huggingface.co/datasets/zeraulalmeida/Jurisprudencia_TRT_13) | `c75af60e9435d8d6b183f936c68a1d4d797d81b9` | SHA-256 e bytes do arquivo original `data/jurisprudencia_trt13.jsonl` |
| 3 `train-*` legíveis | Ambos os repositórios celsowm acima | Revisões acima | SHA-256 e bytes do inventário LFS |

O RepoJus declara CC BY 4.0 para seleção, organização, normalização, metadados e documentação. O TRT-13 declara MIT. A tabela por arquivo com caminho remoto, commit consultado, hash local e escopo de licença fica em `reports/jurisprudencia/origens_huggingface/rastreabilidade_atual.csv` e no JSON homônimo. As contagens por dataset se sobrepõem para os mesmos três arquivos celsowm.

Continuam sem correspondência exata `jurisprudencias_tst.json` e o `train-00002.parquet` local com falha. A referência [CEIA-COREJUR/processos](https://huggingface.co/datasets/CEIA-COREJUR/processos) retornou HTTP 401 na API; versão 2.1.0 permanece declarada pela pessoa usuária, sem confirmação de licença. [costadev00/stf-acordaos](https://huggingface.co/datasets/costadev00/stf-acordaos), revisão `43dd394cdf2a03696d7978de5013398fd18aa572`, declara CC BY 4.0 e exige aceite para acesso aos dados. Nenhum arquivo local coincidiu com seu inventário; não houve aceite ou acesso restrito.

## Cópia oficial validada

Foi baixado `train-00002.parquet` da revisão fixa de `jurisprudencias_br_full`. A cópia tem 122.977.661 bytes, SHA-256 `d0f5fc249168921cab5ba7e01d0425d0b9f32376937c33d98530fd9d1605ccae` e 50.000 registros STF lidos integralmente com PyArrow. Fica em `data/raw/jurisprudencia/recuperacao/`, ignorada pelo Git.

O arquivo local problemático tem 222.818.285 bytes, outro hash e trechos inicial/final diferentes. A equivalência não foi comprovada. O original não foi alterado, e a cópia oficial não entrou na base canônica nem nas métricas anteriores. Mesmo nome não demonstra mesmo conteúdo.

A seção de [fontes e proveniência do notebook 03](../notebooks/02_jurisprudencia/03_limpeza_estruturacao_jurisprudencia.ipynb#fontes-proveniencia) apresenta as evidências e validações executadas. A rastreabilidade atual também está registrada em `origens_declaradas.json` e `rastreabilidade_atual_resumo.json`, preservando o escopo estatístico da análise.

Para atualizar as evidências complementares e consolidar os arquivos:

```powershell
.\.venv\Scripts\python.exe scripts/coletar_origens_complementares.py
.\.venv\Scripts\python.exe scripts/registrar_rastreabilidade_jurisprudencia.py
.\.venv\Scripts\python.exe scripts/run_preparacao_jurisprudencia.py --etapa origens
```
