"""Monitoramento de deriva e de confiança com Evidently (issue #31, RNF04).

    uv run --group treino python -m treino.deriva referencia [--docs 2000]   # grava a referência (sem texto)
    uv run --group treino python -m treino.deriva relatorio [--desde AAAA-MM-DD] [--atual arquivo.jsonl]

**Referência**: os mesmos atributos que o worker registra (`worker/modelos/monitoramento.py`), calculados sobre
acórdãos da divisão de validação do RepoJus com o código em uso — confiança do tipo, abstenção, tamanho do
documento, nº de pedidos, fração de pedidos sem resultado identificado, campos preenchidos e qualidade da leitura.
Só números: o arquivo `avaliacao/monitoramento/referencia.csv` entra no Git.

**Atual**: o log de previsões do worker (padrão `dados/output/previsoes/*.jsonl`), agregado por tarefa.

O relatório (HTML + JSON em `dados/output/monitoramento/`) traz a deriva por coluna (teste K-S/qui-quadrado do
Evidently) e um resumo de confiança. Alerta (código de saída 2) quando metade ou mais das colunas derivam ou quando a
taxa de abstenção sobe mais de 10 pontos — sinal para olhar a fila de aprendizado ativo (`treino/aprendizado_ativo.py`).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from treino.comum import RAIZ, parametros, salvar_json

REFERENCIA = RAIZ / "avaliacao" / "monitoramento" / "referencia.csv"
SAIDA = RAIZ / "dados" / "output" / "monitoramento"
COLUNAS = ["confianca_tipo", "abstencao_tipo", "caracteres", "pedidos", "fracao_pedidos_sem_resultado",
           "campos_preenchidos", "qualidade_leitura"]
LIMIAR_PARCELA_DERIVA = 0.5
LIMIAR_SUBIDA_ABSTENCAO = 0.10


# ---------------------------------------------------------------- funções puras (testadas no CI)
def agregar_por_tarefa(linhas: list[dict]) -> list[dict]:
    """Do log de previsões (uma linha por modelo) para uma linha por documento com as COLUNAS."""
    por: dict[str, dict] = {}
    for x in linhas:
        if x.get("modelo") not in ("classificador_tipo_fase", "resultado_pedido", "extrator_campos"):
            continue
        d = por.setdefault(x["tarefa"], {"pedidos": 0, "sem_resultado": 0})
        d["caracteres"] = x.get("caracteres", d.get("caracteres"))
        d["qualidade_leitura"] = x.get("qualidade_leitura", d.get("qualidade_leitura"))
        if x["modelo"] == "classificador_tipo_fase":
            d["confianca_tipo"], d["abstencao_tipo"] = x["confianca"], int(x["abstencao"])
        elif x["modelo"] == "resultado_pedido":
            d["pedidos"] += 1
            d["sem_resultado"] += int(x["abstencao"])
        else:
            d["campos_preenchidos"] = x.get("campos_preenchidos")
    out = []
    for d in por.values():
        d["fracao_pedidos_sem_resultado"] = d["sem_resultado"] / d["pedidos"] if d["pedidos"] else 0.0
        out.append({c: d.get(c) for c in COLUNAS})
    return out


def alerta(resumo: dict) -> list[str]:
    motivos = []
    if resumo["parcela_colunas_com_deriva"] >= LIMIAR_PARCELA_DERIVA:
        motivos.append(f"{resumo['parcela_colunas_com_deriva']:.0%} das colunas com deriva")
    if resumo["abstencao_atual"] - resumo["abstencao_referencia"] > LIMIAR_SUBIDA_ABSTENCAO:
        motivos.append(f"abstenção subiu de {resumo['abstencao_referencia']:.1%} para {resumo['abstencao_atual']:.1%}")
    return motivos


# ---------------------------------------------------------------- execução
def _atributos(textos, modelos, origem="nativo", qualidade=1.0, prefixo="ref"):
    from contratos import Bloco, DocumentoLido, Pagina
    from contratos.base import Posicao
    from worker.documento import analisar

    pos = Posicao(pagina=1, x0=0, y0=0, x1=1, y1=1)
    for i, texto in enumerate(textos):
        blocos = [Bloco(id=f"b{j}", texto=p, posicao=pos) for j, p in enumerate(texto.split("\n\n")) if p.strip()]
        doc = DocumentoLido(tarefa_id=f"{prefixo}{i}", origem=origem, qualidade_leitura=qualidade,
                            paginas=[Pagina(numero=1, blocos=blocos)])
        yield doc, analisar(doc, modelos)


def exemplo(docs: int, taxa_ruido: float = 0.03) -> Path:
    """Log de previsões de exemplo (fotos simuladas: acórdãos de teste com ruído de OCR), gravado pelo mesmo
    `monitoramento.registrar_analise` do worker. Só números; serve ao workflow agendado e à demo do monitoramento."""
    import os
    import tempfile

    import pandas as pd

    from treino.classificador_tipo import baixar, divisao
    from treino.ruido_ocr import ruido
    from worker.modelos import monitoramento
    from worker.modelos.registro import carregar_em_uso

    df = pd.read_parquet(baixar(), columns=["processo", "texto_integral"])
    df = df[df.processo.map(divisao) == "teste"].sample(n=docs, random_state=23)
    modelos = carregar_em_uso(tracking_uri="")
    destino = RAIZ / "avaliacao" / "monitoramento" / "previsoes_exemplo.jsonl"
    with tempfile.TemporaryDirectory() as d:
        os.environ["LEXAI_PREVISOES_DIR"] = d
        textos = [ruido(t, taxa_ruido, semente=i) for i, t in enumerate(df.texto_integral)]
        for doc, a in _atributos(textos, modelos, origem="ocr", qualidade=0.8, prefixo="ex"):
            monitoramento.registrar_analise(doc.tarefa_id, doc, a, modelos)
        linhas = monitoramento.ler()
    for x in linhas:
        x["quando"] = "2026-11-27T12:00:00+00:00"  # arquivo reproduzível
    destino.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in linhas), encoding="utf-8")
    return destino


def referencia(docs: int) -> Path:
    import pandas as pd

    from treino.classificador_tipo import baixar, divisao
    from worker.modelos.registro import carregar_em_uso

    df = pd.read_parquet(baixar(), columns=["processo", "texto_integral"])
    df = df[df.processo.map(divisao) == "validacao"].sample(n=docs, random_state=17)
    modelos = carregar_em_uso(tracking_uri="")
    linhas = []
    for (_doc, a), texto in zip(_atributos(df.texto_integral, modelos), df.texto_integral, strict=True):
        c = a.classificacao
        sem = sum(p.resultado == "nao_identificado" for p in c.pedidos)
        linhas.append({"confianca_tipo": c.confianca_tipo, "abstencao_tipo": int(c.abstencao), "caracteres": len(texto),
                       "pedidos": len(c.pedidos), "fracao_pedidos_sem_resultado": sem / len(c.pedidos) if c.pedidos else 0.0,
                       "campos_preenchidos": sum(x.valor is not None for x in c.campos), "qualidade_leitura": 1.0})
    REFERENCIA.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(linhas, columns=COLUNAS).to_csv(REFERENCIA, index=False)
    return REFERENCIA


def relatorio(atual: list[dict], destino: Path = SAIDA) -> dict:
    import pandas as pd
    from evidently import Report
    from evidently.presets import DataDriftPreset

    ref = pd.read_csv(REFERENCIA)
    cur = pd.DataFrame(agregar_por_tarefa(atual), columns=COLUNAS).astype(float)
    if len(cur) < 20:
        return {"documentos_atuais": len(cur), "aviso": "menos de 20 documentos no período: sem teste de deriva"}
    snap = Report([DataDriftPreset()]).run(current_data=cur, reference_data=ref.astype(float))
    destino.mkdir(parents=True, exist_ok=True)
    snap.save_html(str(destino / "deriva.html"))
    d = snap.dict()
    por_coluna = {}
    for m in d["metrics"]:
        nome = str(m.get("metric_name", ""))
        if nome.startswith("ValueDrift(column="):
            col = nome.split("column=")[1].split(",")[0]
            por_coluna[col] = {"p_valor_ou_distancia": float(m["value"]), "metodo": nome.split("method=")[1].split(",")[0]}
    contagem = next((m["value"] for m in d["metrics"] if str(m.get("metric_name", "")).startswith("DriftedColumnsCount")), {})
    resumo = {"documentos_referencia": len(ref), "documentos_atuais": len(cur),
              "parcela_colunas_com_deriva": float(contagem.get("share", 0.0)), "colunas": por_coluna,
              "confianca_tipo_media": {"referencia": float(ref.confianca_tipo.mean()), "atual": float(cur.confianca_tipo.mean())},
              "abstencao_referencia": float(ref.abstencao_tipo.mean()), "abstencao_atual": float(cur.abstencao_tipo.mean())}
    resumo["alertas"] = alerta(resumo)
    salvar_json(resumo, destino / "deriva.json")
    return resumo


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("referencia")
    r.add_argument("--docs", type=int, default=parametros("deriva").get("docs_referencia", 2000))
    ex = sub.add_parser("exemplo")
    ex.add_argument("--docs", type=int, default=500)
    rel = sub.add_parser("relatorio")
    rel.add_argument("--desde")
    rel.add_argument("--atual", type=Path, help="JSONL de previsões (padrão: o log do worker)")
    a = ap.parse_args()
    if a.cmd == "referencia":
        print(referencia(a.docs))
        return
    if a.cmd == "exemplo":
        print(exemplo(a.docs))
        return
    from worker.modelos.monitoramento import ler

    atual = ([json.loads(x) for x in a.atual.read_text(encoding="utf-8").splitlines() if x.strip()] if a.atual
             else ler(a.desde))
    resumo = relatorio(atual)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    if resumo.get("alertas"):
        print("ALERTA: " + "; ".join(resumo["alertas"]), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
