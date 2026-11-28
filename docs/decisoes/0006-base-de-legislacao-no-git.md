# 0006 — Base de legislação direto no Git

Data: 24/11/2026 · Responsável: Felipe (Eng. de ML e MLOps), com revisão do Eng. de dados

**Contexto.** O manual mandava versionar todos os dados com DVC, com remoto numa pasta compartilhada. O remoto nunca chegou a ser compartilhado: ficou numa pasta de uma única máquina, e ninguém mais do grupo conseguia rodar `dvc pull`. Duas tentativas de remoto falharam ou foram descartadas em 24/11. No Google Drive, o Google bloqueia o app OAuth padrão do DVC e exigiria um client próprio no Google Cloud. O DagsHub pediria uma conta e um token por pessoa. A base de legislação são 216 arquivos (≈ 100 MB, o maior com 25 MB) de texto de lei público, derivado do LawCodex (`e2a0e14`), sem dado pessoal.

**Decisão.** `dados/processed/legislacao`, `dados/chunks/legislacao` e `dados/relatorios/legislacao` saem do DVC e entram direto no Git, com `-text` no `.gitattributes` para os bytes e os sha256 dos manifestos não mudarem no checkout. O acervo de documentos e os rótulos **continuam no DVC**: passam por anonimização e não podem ir para um repositório público. `raw/`, `interim/` e `output/` continuam fora do Git. Se a base passar de 50 MB por arquivo (aviso do GitHub; o limite é 100 MB), volta para o DVC, com um remoto compartilhado de verdade.

**Alternativa descartada.** Manter o DVC e configurar um remoto (client OAuth no Google Cloud, DagsHub, Backblaze B2 ou Cloudflare R2). Seria mais fiel ao manual, mas pede conta e credencial por pessoa, para ~100 MB que o próprio GitHub guarda sem custo. Git LFS foi descartado pelo limite grátis de 1 GB de download por mês do repositório.
