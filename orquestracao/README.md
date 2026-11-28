# Orquestração (Apache Airflow 3.1)

O Airflow agenda e registra o que já existe no projeto. Ele não reimplementa nada:

| DAG | Agenda | O que roda |
|---|---|---|
| `lexai_treino_avaliacao` | segunda, 1h (Brasília) | baixa o lote → cada estágio do `dvc.yaml` (`dvc repro --single-item`, só refaz o que mudou) → portão de regressão → métricas finais |
| `lexai_monitoramento` | todo dia, 6h | relatório de deriva (Evidently) sobre o log de previsões do worker; com alerta, gera o lote de aprendizado ativo |
| `lexai_manutencao` | todo dia, 3h30 | apaga entradas de upload esquecidas (> 24 h) e originais com o prazo de guarda vencido (RNF01) |

**Como roda.** O Airflow fica no ambiente da imagem oficial. O projeto (grupos `treino` e `worker`) fica num venv separado, `/opt/lexai-venv`. As tarefas chamam `python -m …` e `dvc repro` nesse venv (`orquestracao/etapas.py`), então as dependências dos dois não precisam ser compatíveis. A promoção de modelo continua manual (`treino/promover.py`): o Airflow treina e mede, mas não promove.

**Subir.**
```bash
make airflow                       # dev, por cima do infra/docker-compose.yml
# produção, por cima do compose de produção:
docker compose -f infra/docker-compose.prod.yml -f infra/docker-compose.airflow.yml --env-file .env.prod up -d airflow
docker compose … logs airflow | grep -i password    # senha do admin (gerada no primeiro início)
```
A UI fica em `http://127.0.0.1:18080`, só local ou por túnel SSH. Usa o Postgres do Lexai (banco `airflow`, criado na partida) com o LocalExecutor (`airflow standalone`).

**Testar.** `make checar-dags` carrega as DAGs com a imagem oficial; o CI faz o mesmo (job "DAGs do Airflow"). `tests/orquestracao/` confere, sem Airflow, que as DAGs seguem os estágios do `dvc.yaml` na ordem das dependências. Para rodar uma DAG uma vez, sem agenda: `docker compose … exec airflow airflow dags test lexai_manutencao`.

**Limites conhecidos.** O treino roda na CPU do servidor: o BERTimbau + LoRA e o benchmark de NLI continuam no M4 (`make lora-tipo`, `make benchmark-nli DEVICE=mps`). Os relatórios que a DAG gera ficam no contêiner e no MLflow; levar um resultado ao Git continua sendo por PR.
