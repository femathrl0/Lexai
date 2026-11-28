"""Entrega do arquivo enviado ao worker: objeto no MinIO (produção) ou arquivo temporário (desenvolvimento).

A fila leva só a referência: `minio://<bucket>/<chave>` ou o caminho local. O worker baixa, processa e apaga a cópia
de entrada; o original só fica guardado com o opt-in de guarda (#33).
"""
from __future__ import annotations

import io
import tempfile
import uuid

from .config import Config, config

TIPOS_ACEITOS = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
ASSINATURAS = {b"%PDF": ".pdf", b"\xff\xd8\xff": ".jpg", b"\x89PNG": ".png", b"RIFF": ".webp"}


class ArquivoRecusado(ValueError):
    pass


def extensao(dados: bytes) -> str:
    """Pelo conteúdo, não pelo nome nem pelo Content-Type declarado."""
    for assinatura, ext in ASSINATURAS.items():
        if dados.startswith(assinatura):
            return ext
    raise ArquivoRecusado("tipo de arquivo não aceito: envie PDF ou foto (JPG, PNG, WebP)")


def guardar_entrada(dados: bytes, cfg: Config = config) -> str:
    if len(dados) > cfg.upload_max_mb * 2**20:
        raise ArquivoRecusado(f"arquivo maior que {cfg.upload_max_mb} MB")
    ext = extensao(dados)
    if cfg.minio_endpoint:
        from minio import Minio

        cliente = Minio(cfg.minio_endpoint, access_key=cfg.minio_root_user, secret_key=cfg.minio_root_password,
                        secure=cfg.minio_seguro)
        if not cliente.bucket_exists(cfg.minio_bucket_entrada):
            cliente.make_bucket(cfg.minio_bucket_entrada)
        chave = f"{uuid.uuid4().hex}{ext}"
        cliente.put_object(cfg.minio_bucket_entrada, chave, io.BytesIO(dados), len(dados))
        return f"minio://{cfg.minio_bucket_entrada}/{chave}"
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:  # nome do usuário não vai para o disco
        tmp.write(dados)
    return tmp.name
