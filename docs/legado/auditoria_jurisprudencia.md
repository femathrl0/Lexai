# Auditoria inicial de jurisprudência

O notebook está em `notebooks/02_jurisprudencia/01_auditoria_jurisprudencia.ipynb`. Ele apresenta a auditoria dos vinte arquivos fornecidos: JSONL do TRT-13, JSON aninhado do TST e dezoito arquivos Parquet. O escopo é estrutural e descritivo; não há limpeza destrutiva, anonimização, treinamento ou indexação.

## Executar

```powershell
python -m pip install -r requirements-jurisprudencia.txt
python scripts/auditar_jurisprudencia.py --origem <pasta com os arquivos originais>
python scripts/run_auditoria_jurisprudencia.py
```

Base reduzida (opção D), usada atualmente pelos notebooks 01 a 04: os mesmos nomes de arquivo ficam em `data/raw/jurisprudencia/base_reduzida/` (gerados por `scripts/criar_base_reduzida_jurisprudencia.py`), e todo o pipeline dos notebooks 01–03 é executado por `scripts/rodar_pipeline_base_reduzida.py`.

A pasta de origem pode ser substituída por um armazenamento definitivo que conserve os nomes/bytes dos arquivos. O leitor utiliza somente a lista explícita dos vinte nomes em `src/jurisprudencia/audit.py`, sem ler outros documentos da pasta Downloads. Os dados são tratados como conteúdo, nunca como instruções executáveis.

## Saídas e reprodutibilidade

Os relatórios ficam em `reports/jurisprudencia/auditoria/<inventario>/<codigo>/`. O apontador `auditoria_ativa.json` é gravado somente após a conclusão. O inventário guarda tamanho, SHA-256 e localização dos originais. Cada arquivo tem um checkpoint de perfil; a retomada confere o inventário e as contagens no índice local.

O índice temporário SQLite fica em `tmp/jurisprudencia_auditoria/`. Ele contém fingerprints, tribunal, posição de linha e tamanhos, sem texto nem número de processo em claro. Não deve ser publicado como dado anonimizado. Não versione os originais nem índices sem definir origem, licença, privacidade e armazenamento apropriado. A auditoria não copia vários gigabytes de dados para o repositório.

Relatórios principais:

- `inventario_arquivos.csv` e `inventario.json`: arquivos, hashes, volume, status de leitura e esquemas.
- `tribunais.csv`: tribunal e registros legíveis. A identificação usa campos estruturados; hipóteses baseadas em nome ficam discriminadas nos perfis.
- `dicionario_features.csv`: caminhos, tipos, completude, cardinalidade observada e descrições técnicas, que precisam ser confirmadas com a origem.
- `qualidade_dados.csv`: vazios, texto, datas, hashes declarados e sinais de dados pessoais.
- `duplicatas_resumo.csv`, `duplicatas_por_arquivo.csv`, `duplicatas_grupos_fingerprints.csv`: critérios separados, sem exclusão automática.
- `perfis_arquivos.json`: perfil completo por arquivo, incluindo esquema, tribunal, campo textual selecionado, datas, categorias e domínios declarados.
- PNGs dos gráficos e `conclusao_auditoria.md`: evidências e ações para a próxima etapa.

## Limites de interpretação

A contagem de um arquivo ilegível é desconhecida, não uma base vazia. Arquivos com leitura parcial ficam destacados. Os registros legíveis podem conter cópias e sobreposições entre os arquivos recebidos; somar linhas não equivale a contar decisões únicas. Mesmo processo pode ter diversos documentos legítimos. Identificadores de produtores diferentes podem ter namespaces distintos.

Campos de raiz e caminhos aninhados são distinguidos. Strings contendo JSON não são automaticamente expandidas. Cardinalidade é exata até o limite operacional de 2.000 valores distintos; acima disso, o relatório mostra um limite inferior, não estimativa do total. Quantis de tamanho são exatos sobre os textos selecionados de todos os registros lidos.

Detecção de CPF/e-mail e presença de campos de partes são triagens; não comprovam anonimização. Hash textual divergente pode refletir normalização não documentada. Datas e formatos antigos de processo exigem contexto. O corpus do STF não deve ser presumido integralmente trabalhista.

Solicitar URLs dos repositórios originais, dataset cards, licenças, versões/commits e manifestos de coleta antes de atestar procedência e redistribuição. O notebook distingue as informações declaradas nos dados das verificações técnicas realizadas; não certifica autenticidade, vigência, mérito jurídico ou representatividade.

A pessoa usuária informou que os Parquet vieram do Hugging Face. Essa declaração está preservada em `data/raw/jurisprudencia/origens_declaradas.json`; os nomes `autor/dataset`, links, versões e licenças ainda não foram fornecidos. O TRT-13 JSONL e o TST JSON não tiveram sua origem confirmada por essa declaração sobre os Parquet.

A auditoria concluída leu 609.872 registros em 19 arquivos. Um arquivo (`train-00002.parquet`) teve erro de leitura. Os relatórios, as células de apresentação e os gráficos da auditoria foram executados e salvos no notebook.
