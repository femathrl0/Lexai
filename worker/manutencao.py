"""Limpeza do armazenamento S3 (RNF01), agendada pelo Airflow (`lexai_manutencao`):

- bucket de entrada: o worker apaga a cópia ao terminar; sobra só quando a tarefa falhou de vez. Tudo com mais de
  `HORAS_ENTRADA` horas sai;
- bucket de originais (opt-in de guarda, #33): sai o que passou de `PRAZO_GUARDA_DIAS`.

    python -m worker.manutencao [--simular]
"""
from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta

HORAS_ENTRADA = 24


def vencidos(objetos, agora: datetime, limite: timedelta) -> list[str]:
    """Nomes dos objetos com `last_modified` mais antigo que `agora - limite`."""
    return [o.object_name for o in objetos if o.last_modified is not None and agora - o.last_modified > limite]


def limpar(cliente, simular: bool = False, agora: datetime | None = None) -> dict[str, int]:
    agora = agora or datetime.now(UTC)
    regras = {os.getenv("MINIO_BUCKET_ENTRADA", "entrada"): timedelta(hours=HORAS_ENTRADA),
              os.getenv("MINIO_BUCKET_ORIGINAIS", "originais"): timedelta(days=int(os.getenv("PRAZO_GUARDA_DIAS", "30")))}
    apagados = {}
    for bucket, limite in regras.items():
        if not cliente.bucket_exists(bucket):
            apagados[bucket] = 0
            continue
        nomes = vencidos(cliente.list_objects(bucket, recursive=True), agora, limite)
        if not simular:
            for n in nomes:
                cliente.remove_object(bucket, n)
        apagados[bucket] = len(nomes)
    return apagados


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", action="store_true", help="só conta, não apaga")
    a = ap.parse_args()
    if not os.getenv("MINIO_ENDPOINT"):
        print("MINIO_ENDPOINT vazio: nada a limpar (uploads em pasta temporária)")
        return
    from .armazenamento import _cliente

    print(limpar(_cliente(), simular=a.simular))


if __name__ == "__main__":
    main()
