# treino/ — Eng. de ML e MLOps

Todo treino é rastreado no MLflow (`MLFLOW_TRACKING_URI`) com a versão DVC dos dados e o commit do código.
Baseline primeiro (TF-IDF + regressão logística ou regras); BERTimbau + LoRA só entra se vencer na validação.
Registro com estágios: candidato → aprovado → em uso (alias `em-uso`, lido por `worker/modelos/registro.py`).
