# dados/

A base de legislação entra **direto no Git**, desde 24/11/2026, para todo o grupo ter acesso sem configurar remoto
(o DVC não tinha remoto compartilhado; Google Drive e DagsHub foram descartados):

| Pasta | Conteúdo | Tamanho |
|---|---|---|
| `processed/legislacao/` | 5.284 artigos estruturados das 25 normas do LawCodex (commit `e2a0e14`, ver `corpus/manifesto.yml`) | 12 MB |
| `chunks/legislacao/` | Chunks A (artigo) e D (parágrafo completo) usados pela busca | 39 MB |
| `relatorios/legislacao/` | Relatórios de auditoria, EDA, estruturação, chunking, recuperação e integração RAG | 48 MB |

É texto de lei público, sem dado pessoal. As três pastas ficam com `-text` no `.gitattributes`: os bytes não mudam no
checkout e os sha256 registrados nos manifestos continuam valendo.

Regras que continuam:

- **Nunca suba documento cru nem dado pessoal.** `raw/`, `interim/` e `output/` continuam fora do Git (`.gitignore`
  da raiz). Documento de usuário só depois da anonimização e com termo de consentimento.
- **Limite do GitHub:** 100 MB por arquivo, com aviso a partir de 50 MB; hoje o maior tem 25 MB. Base que passar
  disso volta para o DVC, com um remoto compartilhado.
- Mudou a base? Commit com a origem e o hash da versão nova, como em `corpus/manifesto.yml`.
