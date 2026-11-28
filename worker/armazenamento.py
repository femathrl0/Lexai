"""Lado do worker da entrega do arquivo (ver backend/armazenamento.py): baixa `minio://bucket/chave` para um arquivo
temporário e, ao fim, apaga a cópia de entrada."""
from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator


def _cliente():
    from minio import Minio

    return Minio(os.environ["MINIO_ENDPOINT"], access_key=os.getenv("MINIO_ROOT_USER", ""),
                 secret_key=os.getenv("MINIO_ROOT_PASSWORD", ""), secure=os.getenv("MINIO_SEGURO", "false") == "true")


@contextlib.contextmanager
def arquivo_local(referencia: str, guardar: bool) -> Iterator[str]:
    """Caminho local do arquivo enquanto o bloco roda. Sem opt-in (`guardar=False`) a entrada é apagada no fim."""
    if not referencia.startswith("minio://"):
        try:
            yield referencia
        finally:
            if not guardar and os.path.exists(referencia):
                os.remove(referencia)  # sem opt-in, o original é descartado (RNF01)
        return
    bucket, chave = referencia.removeprefix("minio://").split("/", 1)
    cli = _cliente()
    fd, caminho = tempfile.mkstemp(suffix=os.path.splitext(chave)[1])
    os.close(fd)
    try:
        cli.fget_object(bucket, chave, caminho)
        yield caminho
    finally:
        os.remove(caminho)
        if not guardar:
            cli.remove_object(bucket, chave)
