# Model card — classificador_tipo_fase v1 (baseline)

- **Estágio:** `candidato` no MLflow (`classificador_tipo_fase`, versão 1, experimento `classificador_tipo_fase`, run `tfidf_lr_sem_cabecalho`). Não está `em-uso`: os rótulos são provisórios e a Curadoria não aprovou.
- **Uso pretendido:** identificar o tipo de acórdão trabalhista (recurso ordinário, agravo de petição, embargos de declaração, agravo de instrumento, ação originária) e, a partir dele, a fase (conhecimento ou execução), com abstenção abaixo do limiar (RNF04). Baseline para o BERTimbau + LoRA ([decisão 0004](../decisoes/0004-baselines-por-tarefa.md)).
- **Fora do escopo:** sentença de 1º grau, ata, petição, foto de documento e decisões de outros tribunais. O lote de treino tem só acórdãos do TRT-10, e esses tipos não foram vistos.
- **Dados:** RepoJus `efaraneda/repojus`, revisão `91aa953b3c`, TRT-10 2024, sha256 `453efb25ce42…`, CC BY 4.0. 23.568 acórdãos rotulados; divisão 70/15/15 por hash do número do processo (semente `lexai-divisao-v1`). O rótulo é a classe processual do tribunal; 2.165 acórdãos de embargos que o tribunal rotulou com a classe do recurso embargado foram corrigidos pelo cabeçalho.
- **Pré-processamento:** remove o bloco de identificação até EMENTA e mascara nomes de classe e papéis processuais ("recorrente", "agravante", "embargante"…), para o modelo não ler o rótulo no cabeçalho. Primeiros 30 mil caracteres.
- **Modelo:** TF-IDF de palavras (1–2-gramas, sem acento, `min_df=3`, até 300 mil termos) + regressão logística balanceada, `C=16` escolhido na validação.

## Métricas no teste (3.463 acórdãos)

| Variante | Acurácia | F1 macro | F1 agravo de instrumento | Fase trocada (erro grave) |
|---|---:|---:|---:|---:|
| Classe majoritária | 0,564 | 0,144 | 0,000 | 1.209 |
| Regras no cabeçalho | 0,985 | 0,942 | 0,953 | 42 |
| TF-IDF + LR, texto completo | 0,986 | 0,968 | 0,906 | 10 |
| **TF-IDF + LR, sem cabeçalho (este)** | **0,980** | **0,953** | **0,873** | **23** |

Relatório completo e matriz de confusão: [`treino/relatorios/classificador_tipo_baseline.md`](../../treino/relatorios/classificador_tipo_baseline.md).

- **Calibração e limiar de abstenção:** ECE 0,016 no teste. Limiar de 0,44 escolhido na validação para 98% de acurácia nas previsões aceitas: cobertura de 99,9% e acurácia de 98,0% nas aceitas no teste.
- **Erros graves encontrados:** 23 acórdãos com a fase trocada (conhecimento ↔ execução), a maioria entre agravo de petição e recurso ordinário. É a confusão que o manual manda olhar primeiro.
- **Memória e latência no MacBook M4 (medidas em 19/11):** 25 MB serializado; +0,18 GB no processo ao carregar, incluindo o scikit-learn; CPU, 2,4 ms p50 e 5,5 ms p95 por documento (50 acórdãos). Desprezível no orçamento do worker ([relatório](../../treino/relatorios/memoria_latencia_m4.md)), contra 1,35 GB do BERTimbau base.
- **Limitações:** a acurácia da fase (0,72) inclui as abstenções em embargos e agravo de instrumento, cuja fase depende do recurso de origem. O vocabulário do TF-IDF pode conter nomes de advogados e magistrados que aparecem com frequência (`min_df=3`); o artefato fica no MLflow local e não deve ser publicado. Rótulo provisório: as métricas medem a concordância com o metadado do tribunal corrigido, não com o rótulo-ouro.
- **Aprovação da Curadoria:** pendente.
