"""Log de previsões para monitoramento (issue #31) e aprendizado ativo (#38).

Cada previsão vira uma linha JSON em `$LEXAI_PREVISOES_DIR/<AAAA-MM-DD>.jsonl` (padrão `dados/output/previsoes/`, fora
do Git). **Só números e rótulos**: modelo, versão, confiança, abstenção e atributos agregados do documento (tamanho,
origem, qualidade da leitura). Nunca texto, nome, CPF ou o id do usuário (RNF01); a tarefa entra por hash, para a fila
de anotação poder pedir o documento a quem deu consentimento de guarda.

Falha no log nunca derruba a tarefa.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

PADRAO = Path(__file__).resolve().parents[2] / "dados" / "output" / "previsoes"
CAMPOS_PROIBIDOS = {"texto", "pergunta", "frase", "trecho", "nome", "cpf", "usuario_id", "email"}


def diretorio() -> Path:
    return Path(os.getenv("LEXAI_PREVISOES_DIR", PADRAO))


def tarefa_hash(tarefa_id: str) -> str:
    return hashlib.sha256(f"lexai-monitoramento:{tarefa_id}".encode()).hexdigest()[:16]


def registrar(modelo: str, versao: str, confianca: float | None, abstencao: bool, tarefa_id: str, previsao: str | None = None,
              **atributos: float | int | str | bool | None) -> None:
    proibidos = CAMPOS_PROIBIDOS & set(atributos)
    if proibidos:
        raise ValueError(f"campo com conteúdo do usuário no log de previsões: {sorted(proibidos)}")
    linha = {"quando": datetime.now(UTC).isoformat(timespec="seconds"), "modelo": modelo, "versao": versao,
             "previsao": previsao, "confianca": None if confianca is None else round(float(confianca), 4),
             "abstencao": bool(abstencao), "tarefa": tarefa_hash(tarefa_id), **atributos}
    try:
        d = diretorio()
        d.mkdir(parents=True, exist_ok=True)
        with (d / f"{datetime.now(UTC):%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except OSError:
        pass


def registrar_analise(tarefa_id: str, doc, analise, modelos: dict) -> None:
    """As previsões de um documento analisado (worker/documento.py)."""
    cls = analise.classificacao
    n_car = sum(len(b.texto) for p in doc.paginas for b in p.blocos)
    comum = {"origem": doc.origem, "qualidade_leitura": doc.qualidade_leitura, "paginas": len(doc.paginas),
             "caracteres": n_car, "trechos": len(analise.segmentos.trechos)}
    v = {n: m.rotulo for n, m in modelos.items()}
    registrar("classificador_tipo_fase", v.get("classificador_tipo_fase", "?"), cls.confianca_tipo, cls.abstencao, tarefa_id,
              cls.tipo_documento, **comum)
    for p in cls.pedidos:
        registrar("resultado_pedido", v.get("resultado_pedido", "?"), p.confianca, p.resultado == "nao_identificado",
                  tarefa_id, p.resultado, **comum)
    preenchidos = sum(c.valor is not None for c in cls.campos)
    registrar("extrator_campos", v.get("extrator_campos", "?"), preenchidos / max(len(cls.campos), 1),
              preenchidos == 0, tarefa_id, None, campos_preenchidos=preenchidos, **comum)


def registrar_validacao(tarefa_id: str, estado, versao_nli: str) -> None:
    """p(sustenta) de cada frase julgada pela Validação (deriva de confiança do verificador)."""
    for m in estado.rastro.mensagens:
        if m.de != "validacao":
            continue
        for j in m.dados.get("julgamento", []):
            p = (j.get("nli") or {}).get("sustenta")
            registrar("verificador_nli", versao_nli, p, not j.get("aprovada", False), tarefa_id,
                      "aprovada" if j.get("aprovada") else "reprovada")


def ler(desde: str | None = None) -> list[dict]:
    d = diretorio()
    linhas = []
    for arq in sorted(d.glob("*.jsonl")) if d.exists() else []:
        if desde and arq.stem < desde:
            continue
        linhas += [json.loads(x) for x in arq.read_text(encoding="utf-8").splitlines() if x.strip()]
    return linhas
