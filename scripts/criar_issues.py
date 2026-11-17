"""Cria labels, milestones e issues (cargo × semana + portões) a partir de docs/roteiro_issues.yml.

Uso:
    python scripts/criar_issues.py --repo <dono>/Lexai            # cria no GitHub (precisa do gh autenticado)
    python scripts/criar_issues.py --dry-run --saida /tmp/issues  # só gera os corpos em Markdown

É idempotente: labels são atualizadas, milestones e issues com o mesmo título não são duplicadas.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
ROTEIRO = RAIZ / "docs" / "roteiro_issues.yml"

REQUISITOS = {
    "RF01": "Enviar PDF ou imagem", "RF02": "Extrair e interpretar textos", "RF03": "Tipo de documento e fase",
    "RF04": "Resumos e explicações simples", "RF05": "Possíveis próximas etapas",
    "RF06": "Fundamentar em documentos e fontes", "RF07": "Perguntas e termos jurídicos",
    "RF08": "Documentos e provas relevantes", "RNF01": "LGPD", "RNF02": "Interface acessível e responsiva",
    "RNF03": "Rastreabilidade", "RNF04": "Sinalizar incertezas", "RNF05": "Fontes atualizadas",
    "RNF06": "Não substitui orientação jurídica", "RNF07": "Linguagem acessível",
}
CORES_CARGO = {"cargo:eng-dados": "1f77b4", "cargo:cientista-dados": "9467bd", "cargo:eng-ml": "2ca02c",
               "cargo:eng-ia": "ff7f0e", "cargo:eng-software": "17becf", "curadoria": "d62728"}
OUTRAS = {"portao": ("000000", "Portão de fim de semana do roteiro"),
          "revisao-juridica": ("b60205", "Precisa de decisão da Curadoria (rascunho + fonte + pergunta)")}


def gh(*args: str, entrada: str | None = None) -> str:
    # Repete só quando a conexão nem chegou a ser estabelecida (o pedido não foi enviado; não duplica nada).
    for tentativa in range(8):
        r = subprocess.run(["gh", *args], input=entrada, capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout
        if not any(e in r.stderr for e in ("TLS handshake timeout", "dial tcp", "connection refused")):
            break
        time.sleep(2 * (tentativa + 1))
    sys.exit(f"gh {' '.join(args[:3])}… falhou:\n{r.stderr}")


def titulo_milestone(s: dict) -> str:
    return f"Semana {s['numero']} — {s['titulo']}"


def titulo_issue(s: dict, cargo: dict) -> str:
    return f"[Semana {s['numero']}] {cargo['nome']} — {s['titulo']}"


def corpo_issue(s: dict, chave: str, cargo: dict, tarefa: dict) -> str:
    linhas = [
        f"**Missão do cargo:** {cargo['missao']}",
        "",
        f"**Semana {s['numero']} — {s['titulo']}** · entregável do deck: _{s['deck']}_",
        "",
        "### Entregáveis",
    ]
    for item in tarefa["itens"]:
        if item.get("feito"):
            linhas.append(f"- [x] {item['texto']} — já existe: `{item['feito']}`")
        else:
            linhas.append(f"- [ ] {item['texto']}")
    reqs = ", ".join(f"{r} ({REQUISITOS[r]})" for r in tarefa.get("requisitos", []))
    linhas += [
        "",
        f"**Portão da semana:** {s['portao']}",
        "",
        "### Contexto",
        f"- **Requisitos:** {reqs or '—'}",
        f"- **Pastas:** {', '.join(f'`{p}`' for p in cargo['pastas'])}",
        f"- **Par (revisa e cobre):** {cargo['par']}",
        f"- **Recebe de:** {cargo['recebe']}",
        f"- **Entrega para:** {cargo['entrega']}",
        f"- **Métricas do cargo:** {cargo['metricas']}",
        "",
        "### Como fazer bem",
        *[f"- {d}" for d in cargo["como_fazer_bem"]],
        "",
        "### Definição de pronto",
        "Atende ao requisito, tem teste, foi revisada pelo par, passa no CI e aparece na demo da semana. "
        "Modelo, prompt ou índice: versão candidata → portões → aprovação da Curadoria. "
        "Ver [docs/manual.md](../blob/main/docs/manual.md) — seções do cargo, roteiro semanal e definição de pronto.",
    ]
    return "\n".join(linhas)


def corpo_portao(s: dict, refs: list[str]) -> str:
    return "\n".join([
        f"**Critério do portão:** {s['portao']}",
        "",
        "A semana seguinte só começa com este portão aprovado ou com o desvio registrado em `docs/decisoes/`.",
        "",
        "### Issues da semana",
        *[f"- [ ] {r}" for r in refs],
        "",
        "### Registro da decisão (Demo e portão, fim da semana)",
        "- [ ] Aprovado  - [ ] Aprovado com desvio registrado  - [ ] Reprovado",
    ])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "output" / "issues")
    a = ap.parse_args()
    if not a.dry_run and not a.repo:
        ap.error("--repo é obrigatório fora do --dry-run")
    roteiro = yaml.safe_load(ROTEIRO.read_text(encoding="utf-8"))
    cargos, semanas = roteiro["cargos"], roteiro["semanas"]

    if a.dry_run:
        a.saida.mkdir(parents=True, exist_ok=True)
        n = 0
        for s in semanas:
            refs = []
            for chave, tarefa in s["tarefas"].items():
                t = titulo_issue(s, cargos[chave])
                refs.append(t)
                (a.saida / f"s{s['numero']}_{chave}.md").write_text(
                    f"# {t}\n\n{corpo_issue(s, chave, cargos[chave], tarefa)}\n", encoding="utf-8")
                n += 1
            (a.saida / f"s{s['numero']}_portao.md").write_text(
                f"# [Semana {s['numero']}] Portão\n\n{corpo_portao(s, refs)}\n", encoding="utf-8")
            n += 1
        print(f"{n} issues geradas em {a.saida}")
        return

    repo = ["--repo", a.repo]
    for nome, cor in CORES_CARGO.items():
        gh("label", "create", nome, "--color", cor, "--force", *repo)
    for nome, (cor, desc) in OUTRAS.items():
        gh("label", "create", nome, "--color", cor, "--description", desc, "--force", *repo)
    for req, desc in REQUISITOS.items():
        gh("label", "create", req, "--color", "c5def5" if req.startswith("RF") else "fef2c0",
           "--description", desc, "--force", *repo)
    for s in semanas:
        gh("label", "create", f"semana-{s['numero']}", "--color", "ededed", "--force", *repo)

    existentes = {m["title"] for m in json.loads(gh("api", f"repos/{a.repo}/milestones?state=all&per_page=100"))}
    for s in semanas:
        if titulo_milestone(s) not in existentes:
            gh("api", f"repos/{a.repo}/milestones", "-f", f"title={titulo_milestone(s)}",
               "-f", f"description=Entregável do deck: {s['deck']}. Portão: {s['portao']}")

    abertas = {i["title"]: i["number"] for i in
               json.loads(gh("issue", "list", *repo, "--state", "all", "--limit", "500", "--json", "title,number"))}

    def criar(titulo: str, corpo: str, labels: list[str], milestone: str) -> int:
        if titulo in abertas:
            print("já existe:", titulo)
            return abertas[titulo]
        url = gh("issue", "create", *repo, "--title", titulo, "--body-file", "-", "--milestone", milestone,
                 *sum((["--label", lb] for lb in labels), []), entrada=corpo).strip()
        print("criada:", url)
        abertas[titulo] = int(url.rsplit("/", 1)[1])
        return abertas[titulo]

    for s in semanas:
        refs = []
        for chave, tarefa in s["tarefas"].items():
            cargo = cargos[chave]
            labels = [cargo["label"], f"semana-{s['numero']}", *tarefa.get("requisitos", [])]
            num = criar(titulo_issue(s, cargo), corpo_issue(s, chave, cargo, tarefa), labels, titulo_milestone(s))
            refs.append(f"#{num} {cargo['nome']}")
        criar(f"[Semana {s['numero']}] Portão — {s['titulo']}", corpo_portao(s, refs),
              ["portao", f"semana-{s['numero']}"], titulo_milestone(s))


if __name__ == "__main__":
    main()
