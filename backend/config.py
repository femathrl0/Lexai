import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:16379/0")
    database_url: str = os.getenv("DATABASE_URL", "")
    sessao_minutos: int = int(os.getenv("SESSAO_MINUTOS", "60"))


config = Config()
