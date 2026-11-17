# dados/

Só ponteiros do DVC entram no Git. Nunca suba documento cru; tudo passa pela anonimização antes.

```bash
uv run --group treino dvc pull     # baixa da pasta compartilhada (remote "compartilhado")
uv run --group treino dvc add dados/<pasta> && git add dados/<pasta>.dvc
uv run --group treino dvc push
```

Ajuste a url do remoto (`.dvc/config`) para a pasta compartilhada do grupo.
