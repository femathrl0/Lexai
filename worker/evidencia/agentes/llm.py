"""Cliente mínimo do Ollama com saída estruturada (JSON Schema) e uma nova tentativa fora do contrato."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)


class LLM(Protocol):
    modelo: str

    def gerar(self, sistema: str, usuario: str, formato: type[M]) -> M: ...


class SaidaForaDoContrato(RuntimeError):
    pass


class ClienteOllama:
    def __init__(self, modelo: str | None = None, host: str | None = None, timeout: float = 300):
        self.modelo = modelo or os.getenv("LLM_MODELO", "qwen3:8b")
        self.host = (host or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        self.timeout = timeout
        # Mesmas opções da geração herdada (worker/evidencia/explicador.py), para comparabilidade.
        self.opcoes = dict(temperature=0, seed=42, num_ctx=16384, num_predict=1500)

    def _chamar(self, sistema: str, usuario: str, schema: dict) -> str:
        corpo = dict(model=self.modelo, stream=False, think=False, format=schema, options=self.opcoes,
                     messages=[dict(role="system", content=sistema), dict(role="user", content=usuario)])
        req = urllib.request.Request(f"{self.host}/api/chat", data=json.dumps(corpo).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())["message"]["content"]

    def gerar(self, sistema: str, usuario: str, formato: type[M]) -> M:
        schema = formato.model_json_schema()
        erro = None
        for _ in range(2):  # manual: "LLM devolve saída fora do contrato → refaz uma vez"
            texto = self._chamar(sistema, usuario, schema)
            try:
                return formato.model_validate_json(texto)
            except ValidationError as e:
                erro = e
        raise SaidaForaDoContrato(str(erro))
