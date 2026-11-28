"""Configuração do backend (pydantic-settings): lê o ambiente/.env e valida na partida.

Em produção (`LEXAI_AMBIENTE=producao`) a partida falha se um segredo ficou com o valor de exemplo do `.env.example`.
"""
from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VALORES_DE_EXEMPLO = {"troque-esta-senha", "troque-esta-senha-minio", "troque-este-segredo", ""}


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    lexai_ambiente: str = "desenvolvimento"
    redis_url: str = "redis://127.0.0.1:16379/0"
    database_url: str = ""
    sessao_minutos: int = 60
    segredo_sessao: str = "troque-este-segredo"
    # Entrada do documento: com MinIO o arquivo vai para o bucket de entrada e a fila leva a chave do objeto (backend e
    # worker podem estar em máquinas diferentes); sem MinIO, pasta temporária compartilhada (desenvolvimento).
    minio_endpoint: str = ""
    minio_root_user: str = ""
    minio_root_password: str = ""
    minio_seguro: bool = False
    minio_bucket_entrada: str = "entrada"
    upload_max_mb: int = 20
    cors_origens: str = ""  # vírgula; vazio = mesma origem (o Caddy serve app e API no mesmo domínio)

    @property
    def producao(self) -> bool:
        return self.lexai_ambiente == "producao"

    @model_validator(mode="after")
    def _segredos_de_producao(self):
        if self.producao:
            fracos = [n for n in ("segredo_sessao", "minio_root_password") if getattr(self, n) in VALORES_DE_EXEMPLO]
            if fracos or "troque-esta-senha" in self.database_url:
                raise ValueError(f"segredos com valor de exemplo em produção: {fracos or ['database_url']}")
        return self


config = Config()
