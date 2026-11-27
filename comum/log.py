"""Logs em JSON, uma linha por evento, sem dado pessoal (manual: "logs JSON sem dado pessoal"; definição de pronto de
serviço).

    from comum.log import configurar, registrador
    configurar("worker")
    log = registrador(__name__)
    log.info("tarefa concluída", extra={"tarefa": tid, "etapa": "verificando", "ms": 812})

O formatador mascara CPF, CNPJ, e-mail e telefone em qualquer campo de texto, como última barreira: o código não deve
logar pergunta, frase nem trecho do usuário (só ids, etapas, tempos e versões).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import UTC, datetime

_MASCARAS = [
    (re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"), "[CPF]"),
    (re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)"), "[CNPJ]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\(?\d{2}\)?\s?)?9?\d{4}-?\d{4}(?!\d)"), "[TELEFONE]"),
]
_PADRAO = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime", "taskName"}


def mascarar(texto: str) -> str:
    for rx, marca in _MASCARAS:
        texto = rx.sub(marca, texto)
    return texto


class FormatadorJSON(logging.Formatter):
    def __init__(self, servico: str):
        super().__init__()
        self.servico = servico

    def format(self, r: logging.LogRecord) -> str:
        linha = {"quando": datetime.fromtimestamp(r.created, UTC).isoformat(timespec="milliseconds"),
                 "nivel": r.levelname.lower(), "servico": self.servico, "origem": r.name, "msg": mascarar(r.getMessage())}
        for k, v in vars(r).items():
            if k not in _PADRAO and not k.startswith("_"):
                linha[k] = mascarar(v) if isinstance(v, str) else v
        if r.exc_info:
            linha["erro"] = mascarar(self.formatException(r.exc_info))
        return json.dumps(linha, ensure_ascii=False, default=str)


def configurar(servico: str, nivel: str | None = None) -> None:
    raiz = logging.getLogger()
    raiz.handlers.clear()
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(FormatadorJSON(servico))
    raiz.addHandler(h)
    raiz.setLevel((nivel or os.getenv("LOG_NIVEL", "INFO")).upper())


def registrador(nome: str) -> logging.Logger:
    return logging.getLogger(nome)
