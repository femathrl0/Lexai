"""Baixa os pesos das versões em uso (revisões fixadas em worker/modelos/em_uso.yml) para o cache do Hugging Face
(`HF_HOME`, um volume no contêiner). Rodar uma vez por servidor: `docker compose run --rm worker python -m
worker.baixar_modelos`."""
from __future__ import annotations


def main() -> None:
    from huggingface_hub import snapshot_download

    from worker.modelos.registro import carregar_em_uso

    for nome, m in carregar_em_uso().items():
        if m.repo:
            print(f"{nome}: {m.repo}@{(m.revisao or 'main')[:8]}", flush=True)
            snapshot_download(m.repo, revision=m.revisao)


if __name__ == "__main__":
    main()
