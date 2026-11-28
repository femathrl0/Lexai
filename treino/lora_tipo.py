"""BERTimbau + LoRA contra o baseline TF-IDF + LR no tipo de documento e fase (issue #17, RF03).

    uv run --group treino python -m treino.lora_tipo                 # rodada completa (MacBook M4, MPS)
    uv run --group treino python -m treino.lora_tipo --amostra 200   # fumaça na CPU (valida o pipeline)

Mesmo lote, mesmos rótulos e **mesma divisão por processo** do baseline (`treino.classificador_tipo`), com o cabeçalho
removido e o nome das classes mascarado (`sem_cabecalho`), que é a variante candidata. O texto vai truncado nos
primeiros `--max-tokens` tokens depois da EMENTA.

Regra de promoção (decisão 0004): o modelo maior só vira `candidato` se tiver F1 macro na validação **≥ 2 pontos acima**
do baseline e **não aumentar** o erro grave (`fase_trocada`) no mesmo conjunto. A comparação usa o relatório gravado do
baseline (`treino/relatorios/classificador_tipo_baseline.json`). Rodada com `--amostra` nunca registra no registro de
modelos.

Saída: `treino/relatorios/lora_tipo.{json,md}` e um run no experimento `classificador_tipo_fase`.
"""

from __future__ import annotations

import argparse
import json
import time

from treino.comum import RELATORIOS, parametros, salvar_json

MODELO_BASE = "neuralmind/bert-base-portuguese-cased"
GANHO_MINIMO = 0.02  # decisão 0004
BASELINE_RELATORIO = RELATORIOS / "classificador_tipo_baseline.json"


# ---------------------------------------------------------------- funções puras (testadas no CI)
def decidir_promocao(candidato_val: dict, baseline_val: dict, ganho_minimo: float = GANHO_MINIMO) -> tuple[bool, str]:
    """Aplica a regra da decisão 0004 às métricas de validação (dicionários no formato de `classificador_tipo.avaliar`)."""
    ganho = candidato_val["f1_macro"] - baseline_val["f1_macro"]
    graves_c, graves_b = candidato_val.get("fase_trocada", 0), baseline_val.get("fase_trocada", 0)
    if ganho < ganho_minimo:
        return False, f"ganho de F1 macro {ganho:+.3f} < {ganho_minimo:.2f} na validação"
    if graves_c > graves_b:
        return False, f"aumenta o erro grave fase_trocada ({graves_b} → {graves_c})"
    return True, f"ganho de F1 macro {ganho:+.3f} e fase_trocada {graves_b} → {graves_c}"


def amostrar(df, n_por_divisao: int | None, semente: int = 13):
    """Amostra estratificada por classe dentro de cada divisão (a divisão por processo não muda)."""
    import pandas as pd

    if not n_por_divisao:
        return df
    partes = []
    for _, g in df.groupby("divisao"):
        frac = min(1.0, n_por_divisao / len(g))
        partes += [x.sample(frac=frac, random_state=semente) for _, x in g.groupby("classe")]
    return pd.concat(partes).reset_index(drop=True)


# ---------------------------------------------------------------- treino
def _device(pedido: str | None) -> str:
    import torch

    if pedido:
        return pedido
    if torch.backends.mps.is_available():
        return "mps"
    return "cuda" if torch.cuda.is_available() else "cpu"


def treinar(a) -> dict:
    import numpy as np
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from treino.classificador_tipo import CLASSES, LOTE, SEMENTE, avaliar, carregar_lote, sem_cabecalho
    from treino.metricas import limiar_abstencao

    torch.manual_seed(a.semente)
    np.random.seed(a.semente)
    device = _device(a.device)
    df = amostrar(carregar_lote(), a.amostra)
    partes = {d: df[df.divisao == d].reset_index(drop=True) for d in ("treino", "validacao", "teste")}
    print({d: len(p) for d, p in partes.items()}, "device", device, flush=True)

    tok = AutoTokenizer.from_pretrained(a.modelo)
    rotulo_id = {c: i for i, c in enumerate(CLASSES)}
    net = AutoModelForSequenceClassification.from_pretrained(
        a.modelo, num_labels=len(CLASSES), id2label=dict(enumerate(CLASSES)), label2id=rotulo_id)
    lora = LoraConfig(task_type="SEQ_CLS", r=a.r, lora_alpha=2 * a.r, lora_dropout=0.1,
                      target_modules=["query", "value"])
    net = get_peft_model(net, lora).to(device)
    treinaveis = sum(p.numel() for p in net.parameters() if p.requires_grad)

    def lotes(p, embaralhar: bool):
        idx = np.random.permutation(len(p)) if embaralhar else np.arange(len(p))
        for i in range(0, len(idx), a.lote):
            sel = p.iloc[idx[i:i + a.lote]]
            x = tok([sem_cabecalho(t) for t in sel.texto], truncation=True, max_length=a.max_tokens, padding=True,
                    return_tensors="pt")
            y = torch.tensor([rotulo_id[c] for c in sel.classe])
            yield {k: v.to(device) for k, v in x.items()}, y.to(device)

    # pesos de classe como no baseline (class_weight="balanced")
    cont = partes["treino"].classe.value_counts()
    pesos = torch.tensor([len(partes["treino"]) / (len(CLASSES) * cont.get(c, 1)) for c in CLASSES],
                         dtype=torch.float32, device=device)
    perda = torch.nn.CrossEntropyLoss(weight=pesos)
    opt = torch.optim.AdamW([p for p in net.parameters() if p.requires_grad], lr=a.lr, weight_decay=0.01)

    def prever(p):
        net.eval()
        probas = []
        with torch.no_grad():
            for x, _ in lotes(p, False):
                probas.append(torch.softmax(net(**x).logits.float(), dim=-1).cpu().numpy())
        net.train()
        return np.concatenate(probas) if probas else np.zeros((0, len(CLASSES)))

    t0 = time.perf_counter()
    historico = []
    melhor = None
    for epoca in range(a.epocas):
        net.train()
        soma, n = 0.0, 0
        for x, y in lotes(partes["treino"], True):
            opt.zero_grad()
            loss = perda(net(**x).logits, y)
            loss.backward()
            opt.step()
            soma, n = soma + loss.item(), n + 1
        proba_val = prever(partes["validacao"])
        pred_val = [CLASSES[i] for i in proba_val.argmax(1)]
        f1 = avaliar(list(partes["validacao"].classe), pred_val)["f1_macro"]
        historico.append({"epoca": epoca + 1, "perda_treino": soma / max(n, 1), "f1_macro_validacao": f1})
        print(f"  época {epoca + 1}: perda {soma / max(n, 1):.4f}, F1 macro validação {f1:.4f}", flush=True)
        if melhor is None or f1 > melhor[0]:
            melhor = (f1, {k: v.detach().cpu().clone() for k, v in net.state_dict().items() if "lora" in k
                           or "classifier" in k})
    net.load_state_dict(melhor[1], strict=False)
    duracao = time.perf_counter() - t0

    proba_val = prever(partes["validacao"])
    pred_val = np.array([CLASSES[i] for i in proba_val.argmax(1)])
    conf_val = proba_val.max(1)
    limiar, _, _ = limiar_abstencao(list(conf_val), list(pred_val == partes["validacao"].classe.to_numpy()), a.precisao_alvo)
    metricas = {}
    for d in ("validacao", "teste"):
        proba = proba_val if d == "validacao" else prever(partes[d])
        pred = np.array([CLASSES[i] for i in proba.argmax(1)])
        conf = proba.max(1)
        m = avaliar(list(partes[d].classe), list(pred), confianca=list(conf), fase_true=list(partes[d].fase))
        aceitas = conf >= limiar
        m["com_abstencao"] = {"limiar": float(limiar), "cobertura": float(aceitas.mean()),
                              "acuracia_aceitas": float((pred[aceitas] == partes[d].classe.to_numpy()[aceitas]).mean())
                              if aceitas.any() else None}
        metricas[d] = m

    baseline = json.loads(BASELINE_RELATORIO.read_text(encoding="utf-8"))["resultados"]["tfidf_lr_sem_cabecalho"]
    promove, motivo = decidir_promocao(metricas["validacao"], baseline["validacao"])
    if a.amostra:
        promove, motivo = False, f"rodada de fumaça (--amostra {a.amostra}); {motivo}"
    params = {"modelo_base": a.modelo, "lora_r": a.r, "lora_alpha": 2 * a.r, "alvo": "query,value", "lr": a.lr,
              "epocas": a.epocas, "lote": a.lote, "max_tokens": a.max_tokens, "semente": a.semente,
              "amostra": a.amostra or 0, "device": device, "parametros_treinaveis": treinaveis,
              "preprocessamento": "tfidf_lr_sem_cabecalho (sem_cabecalho)", "limiar_abstencao": float(limiar)}
    rel = {"params": params, "historico": historico, "metricas": metricas, "duracao_s": round(duracao),
           "baseline_validacao_f1_macro": baseline["validacao"]["f1_macro"],
           "decisao": {"promove_para_candidato": promove, "motivo": motivo}}

    if not a.sem_mlflow:
        from treino.comum import iniciar_mlflow, tags_padrao

        mlflow = iniciar_mlflow("classificador_tipo_fase")
        with mlflow.start_run(run_name="bertimbau_lora_sem_cabecalho") as run:
            mlflow.set_tags(tags_padrao(tarefa="tipo_documento", variante="bertimbau_lora", **{
                "dados.lote": LOTE["id"], "dados.sha256": LOTE["sha256"], "dados.semente_divisao": SEMENTE}))
            mlflow.log_params(params)
            for d, m in metricas.items():
                mlflow.log_metrics({f"{d}.{k}": float(v) for k, v in m.items() if isinstance(v, int | float)})
            mlflow.log_dict(rel, "relatorio.json")
            if promove:
                caminho = RELATORIOS.parent / "modelos" / "lora_tipo"
                net.save_pretrained(caminho)
                tok.save_pretrained(caminho)
                mlflow.log_artifacts(str(caminho), artifact_path="modelo")
                from mlflow import MlflowClient

                mv = mlflow.register_model(f"runs:/{run.info.run_id}/modelo", "classificador_tipo_fase")
                MlflowClient().set_model_version_tag("classificador_tipo_fase", mv.version, "estagio", "candidato")
                rel["registro"] = {"versao": mv.version}
    return rel


def markdown(rel: dict) -> str:
    p, m = rel["params"], rel["metricas"]
    lin = ["# BERTimbau + LoRA contra o baseline — tipo de documento", "",
           f"Base `{p['modelo_base']}`, LoRA r={p['lora_r']} em query/value ({p['parametros_treinaveis']:,} parâmetros "
           f"treináveis), {p['epocas']} épocas, {p['max_tokens']} tokens, device {p['device']}, "
           f"{'amostra de ' + str(p['amostra']) + ' por divisão' if p['amostra'] else 'lote completo'}; "
           f"{rel['duracao_s']} s de treino.", "",
           "| Divisão | F1 macro | Acurácia | Fase trocada | ECE | Cobertura com abstenção |", "|---|---:|---:|---:|---:|---:|"]
    for d, x in m.items():
        lin.append(f"| {d} | {x['f1_macro']:.3f} | {x['acuracia']:.3f} | {x.get('fase_trocada', '—')} | "
                   f"{x.get('ece', 0):.3f} | {x['com_abstencao']['cobertura']:.1%} |")
    dec = rel["decisao"]
    lin += ["", f"Baseline TF-IDF + LR (validação): F1 macro {rel['baseline_validacao_f1_macro']:.3f}.", "",
            f"**Decisão (regra 0004):** {'vira candidato' if dec['promove_para_candidato'] else 'não promove'} — "
            f"{dec['motivo']}."]
    return "\n".join(lin) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p = parametros("lora_tipo")
    ap.add_argument("--modelo", default=p.get("modelo", MODELO_BASE))
    ap.add_argument("--amostra", type=int, default=None, help="exemplos por divisão (fumaça na CPU)")
    ap.add_argument("--epocas", type=int, default=p.get("epocas", 3))
    ap.add_argument("--lote", type=int, default=p.get("lote", 16))
    ap.add_argument("--lr", type=float, default=p.get("lr", 3e-4))
    ap.add_argument("--r", type=int, default=p.get("r", 8))
    ap.add_argument("--max-tokens", type=int, default=p.get("max_tokens", 512))
    ap.add_argument("--semente", type=int, default=p.get("semente", 42))
    ap.add_argument("--precisao-alvo", type=float, default=0.98)
    ap.add_argument("--device", default=None)
    ap.add_argument("--sem-mlflow", action="store_true")
    a = ap.parse_args()
    rel = treinar(a)
    nome = "lora_tipo_amostra" if a.amostra else "lora_tipo"
    salvar_json(rel, RELATORIOS / f"{nome}.json")
    (RELATORIOS / f"{nome}.md").write_text(markdown(rel), encoding="utf-8")
    print(markdown(rel))


if __name__ == "__main__":
    main()
