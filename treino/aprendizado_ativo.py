"""Fila de aprendizado ativo (issue #38; manual, monitoramento: "% previsões abaixo do limiar → fila de anotação").

    uv run --group treino python -m treino.aprendizado_ativo [--desde AAAA-MM-DD] [--tamanho 50] [--log arquivo.jsonl]

Lê o log de previsões do worker (`worker/modelos/monitoramento.py`), separa as que ficaram **abaixo do limiar** do
modelo em uso (ou se abstiveram) e monta um lote de anotação no formato de importação do Label Studio, com a
configuração de rótulos de cada tarefa.

Ordem: menor confiança primeiro, com cota por modelo (nenhum modelo ocupa o lote inteiro) e uma tarefa por documento
por modelo. O lote **não tem texto**: cada item aponta para a tarefa por hash; o documento só é anexado para quem deu
o consentimento de guarda (opt-in, #33), pela Cientista de dados, fora deste script.

Saída: `dados/output/aprendizado_ativo/lote_<data>.json` (tarefas) e `config_<modelo>.xml` (rótulos).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from treino.comum import RAIZ

SAIDA = RAIZ / "dados" / "output" / "aprendizado_ativo"
LIMIAR_PADRAO = 0.5
ROTULOS = {
    "classificador_tipo_fase": ["recurso_ordinario", "agravo_peticao", "embargos_declaracao", "agravo_instrumento",
                                "acao_originaria", "sentenca", "outro"],
    "resultado_pedido": ["procedente", "improcedente", "parcialmente_procedente", "nao_identificado"],
    "verificador_nli": ["sustenta", "contradiz", "nao_trata"],
    "extrator_campos": ["campos_corretos", "campo_errado", "campo_faltando"],
}
LIMIAR_DO_MODELO = {"classificador_tipo_fase": "abstencao", "resultado_pedido": "abstencao", "verificador_nli": "sustenta"}


# ---------------------------------------------------------------- funções puras (testadas no CI)
def limiares_em_uso() -> dict[str, float]:
    from worker.modelos.registro import carregar_em_uso

    em_uso = carregar_em_uso(tracking_uri="")
    return {m: float(em_uso[m].limiar(chave, LIMIAR_PADRAO)) for m, chave in LIMIAR_DO_MODELO.items() if m in em_uso}


def incerta(previsao: dict, limiares: dict[str, float]) -> bool:
    if previsao.get("abstencao"):
        return True
    conf = previsao.get("confianca")
    return conf is not None and conf < limiares.get(previsao["modelo"], LIMIAR_PADRAO)


def selecionar(log: list[dict], limiares: dict[str, float], tamanho: int) -> list[dict]:
    candidatas: dict[tuple[str, str], dict] = {}
    for p in log:
        if p.get("modelo") not in ROTULOS or not incerta(p, limiares):
            continue
        chave = (p["modelo"], p["tarefa"])
        atual = candidatas.get(chave)
        if atual is None or (p.get("confianca") or 0) < (atual.get("confianca") or 0):
            candidatas[chave] = p
    por_modelo: dict[str, list[dict]] = defaultdict(list)
    for p in sorted(candidatas.values(), key=lambda x: (x.get("confianca") or 0.0)):
        por_modelo[p["modelo"]].append(p)
    lote, i = [], 0
    while len(lote) < tamanho and any(i < len(v) for v in por_modelo.values()):  # rodízio entre modelos
        for v in por_modelo.values():
            if i < len(v) and len(lote) < tamanho:
                lote.append(v[i])
        i += 1
    return lote


def para_label_studio(lote: list[dict]) -> list[dict]:
    return [{"data": {"tarefa": p["tarefa"], "modelo": p["modelo"], "versao": p.get("versao"),
                      "previsao": p.get("previsao"), "confianca": p.get("confianca"), "origem": p.get("origem")},
             "meta": {"motivo": "abstencao" if p.get("abstencao") else "abaixo_do_limiar", "quando": p.get("quando")},
             "predictions": [{"model_version": p.get("versao"), "score": p.get("confianca") or 0.0,
                              "result": [{"from_name": "rotulo", "to_name": "info", "type": "choices",
                                          "value": {"choices": [p["previsao"]]}}] if p.get("previsao") in ROTULOS[p["modelo"]]
                              else []}]}
            for p in lote]


def config_xml(modelo: str) -> str:
    escolhas = "\n".join(f'    <Choice value="{r}"/>' for r in ROTULOS[modelo])
    return (f'<View>\n  <Header value="{modelo}: confira no documento da tarefa e escolha o rótulo"/>\n'
            f'  <Text name="info" value="$previsao (confiança $confianca)"/>\n'
            f'  <Choices name="rotulo" toName="info" choice="single" required="true">\n{escolhas}\n  </Choices>\n</View>\n')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde")
    ap.add_argument("--tamanho", type=int, default=50)
    ap.add_argument("--log", type=Path, help="JSONL de previsões (padrão: o log do worker)")
    a = ap.parse_args()
    from worker.modelos.monitoramento import ler

    log = [json.loads(x) for x in a.log.read_text(encoding="utf-8").splitlines() if x.strip()] if a.log else ler(a.desde)
    lote = selecionar(log, limiares_em_uso(), a.tamanho)
    SAIDA.mkdir(parents=True, exist_ok=True)
    destino = SAIDA / f"lote_{date.today():%Y-%m-%d}.json"
    destino.write_text(json.dumps(para_label_studio(lote), ensure_ascii=False, indent=2), encoding="utf-8")
    for m in {p["modelo"] for p in lote}:
        (SAIDA / f"config_{m}.xml").write_text(config_xml(m), encoding="utf-8")
    lim = limiares_em_uso()
    incertas = sum(incerta(p, lim) for p in log)
    print(f"{len(log)} previsões, {incertas} abaixo do limiar ({incertas / max(len(log), 1):.1%}); "
          f"lote de {len(lote)} → {destino}")


if __name__ == "__main__":
    main()
