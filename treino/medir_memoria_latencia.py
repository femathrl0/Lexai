"""Memória e latência dos modelos candidatos no MacBook M4 e orçamento de memória do worker (issue #3).

Mede cada modelo isolado (um subprocesso por modelo, para a memória não se misturar) e depois todos juntos,
no mesmo processo, com a LLM carregada no Ollama — que é a situação real do worker.

Uso:
    python -m treino.medir_memoria_latencia                 # tudo, registra no MLflow
    python -m treino.medir_memoria_latencia --sem-mlflow
    python -m treino.medir_memoria_latencia --um reranker   # (interno) mede um modelo e imprime JSON

Memória no Apple Silicon é unificada: a parte que vai para a GPU (MPS) não aparece toda no RSS. Por isso cada
medição registra o RSS do processo e a memória alocada pelo driver MPS; o custo do modelo é a soma dos dois.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.request

from treino.comum import RAIZ, RELATORIOS, iniciar_mlflow, maquina, salvar_json, tags_padrao

GB = 1024**3

# nome -> (repositório HF, tipo). Candidatos do manual (stack: reranker, verificador, embeddings, classificadores).
CANDIDATOS: dict[str, tuple[str, str]] = {
    "embeddings_bge_m3": ("BAAI/bge-m3", "bi_encoder"),
    "reranker_bge_v2_m3": ("BAAI/bge-reranker-v2-m3", "cross_encoder"),
    "verificador_mdeberta_xnli": ("MoritzLaurer/mDeBERTa-v3-base-mnli-xnli", "nli"),
    "classificador_bertimbau_base": ("neuralmind/bert-base-portuguese-cased", "classificador"),
}
LLM_PADRAO = os.environ.get("LLM_MODELO", "qwen3:8b")
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


# ---------------------------------------------------------------- textos de carga (lei real, sem dado pessoal)
def _textos_lei(n: int = 64) -> list[str]:
    caminho = RAIZ / "dados" / "chunks" / "legislacao" / "chunks_A_artigo.json"
    if caminho.exists():
        artigos = json.loads(caminho.read_text(encoding="utf-8"))
        clt = [a["corpo_chunk"] for a in artigos if "consolidacao-das-leis-do-trabalho" in a["caminho_relativo"]]
        longos = [t for t in clt if 600 <= len(t) <= 2500]
        return (longos * (n // max(len(longos), 1) + 1))[:n]
    base = (
        "A duração normal do trabalho, para os empregados em qualquer atividade privada, não excederá de 8 (oito) "
        "horas diárias, desde que não seja fixado expressamente outro limite. "
    ) * 6
    return [base] * n


PERGUNTA = "Quais verbas o empregado recebe quando é dispensado sem justa causa?"
FRASE = "Na dispensa sem justa causa, o empregado tem direito ao aviso prévio proporcional ao tempo de serviço."


# ---------------------------------------------------------------- medição de um modelo (subprocesso)
def _memoria(torch_mod) -> dict[str, float]:
    import psutil

    rss = psutil.Process().memory_info().rss / GB
    mps = torch_mod.mps.driver_allocated_memory() / GB if torch_mod.backends.mps.is_available() else 0.0
    return {"rss_gb": rss, "mps_gb": mps, "total_gb": rss + mps}


def _cronometrar(fn, repeticoes: int, aquecimento: int = 2) -> dict[str, float]:
    for _ in range(aquecimento):
        fn()
    tempos = []
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        fn()
        tempos.append((time.perf_counter() - t0) * 1000)
    tempos.sort()
    return {
        "p50_ms": statistics.median(tempos),
        "p95_ms": tempos[min(len(tempos) - 1, int(0.95 * len(tempos)))],
        "media_ms": statistics.fmean(tempos),
    }


def _carregar(nome: str, device: str):
    repo, tipo = CANDIDATOS[nome]
    if tipo == "bi_encoder":
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(repo, device=device)
    if tipo == "cross_encoder":
        from sentence_transformers import CrossEncoder

        return CrossEncoder(repo, device=device, max_length=512)
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(repo)
    # BERTimbau só publica .bin; use_safetensors=False evita a conversão automática (baixa outra cópia e trava)
    kw = {"num_labels": 5, "use_safetensors": False} if tipo == "classificador" else {}
    net = AutoModelForSequenceClassification.from_pretrained(repo, **kw).eval().to(device)
    return tok, net


def _cargas(nome: str, modelo, device: str, rep: int) -> dict[str, dict[str, float]]:
    """Carga típica de cada modelo no worker."""
    import torch

    textos = _textos_lei()
    _, tipo = CANDIDATOS[nome]
    sync = torch.mps.synchronize if device == "mps" else (lambda: None)

    def rodar(f):
        def g():
            f()
            sync()

        return g

    if tipo == "bi_encoder":
        return {
            "consulta_1": _cronometrar(rodar(lambda: modelo.encode([PERGUNTA])), rep),
            "lote_32_trechos": _cronometrar(rodar(lambda: modelo.encode(textos[:32], batch_size=32)), max(3, rep // 4)),
        }
    if tipo == "cross_encoder":
        pares = [(PERGUNTA, t) for t in textos[:30]]
        return {"rerank_30_pares": _cronometrar(rodar(lambda: modelo.predict(pares, batch_size=16)), max(3, rep // 2))}
    tok, net = modelo

    def inferir(premissas, hipoteses=None):
        x = tok(premissas, hipoteses, truncation=True, max_length=512, padding=True, return_tensors="pt")
        x = {k: v.to(device) for k, v in x.items()}
        with torch.no_grad():
            net(**x)

    if tipo == "nli":
        return {
            "par_1": _cronometrar(rodar(lambda: inferir([textos[0]], [FRASE])), rep),
            "resposta_10_frases": _cronometrar(rodar(lambda: inferir(textos[:10], [FRASE] * 10)), max(3, rep // 2)),
        }
    doc = " ".join(textos[:8])  # ~512 tokens após truncar: um documento
    return {"documento_512_tokens": _cronometrar(rodar(lambda: inferir([doc])), rep)}


def medir_um(nome: str, device: str, rep: int) -> dict:
    import torch

    base = _memoria(torch)
    t0 = time.perf_counter()
    modelo = _carregar(nome, device)
    carga_s = time.perf_counter() - t0
    apos_carga = _memoria(torch)
    latencia = _cargas(nome, modelo, device, rep)
    pico = _memoria(torch)
    n_param = None
    try:
        net = modelo[1] if isinstance(modelo, tuple) else getattr(modelo, "model", None) or modelo
        n_param = sum(p.numel() for p in net.parameters())
    except Exception:  # noqa: BLE001 — contagem é informativa
        pass
    return {
        "modelo": nome,
        "repo": CANDIDATOS[nome][0],
        "device": device,
        "parametros": n_param,
        "carga_s": carga_s,
        "memoria_modelo_gb": apos_carga["total_gb"] - base["total_gb"],
        "memoria_pico_gb": pico["total_gb"] - base["total_gb"],
        "memoria": {"base": base, "apos_carga": apos_carga, "pico": pico},
        "latencia": latencia,
    }


def medir_juntos(device: str, rep: int) -> dict:
    """Todos os modelos do worker no mesmo processo (como o worker real carrega)."""
    import torch

    base = _memoria(torch)
    modelos = {n: _carregar(n, device) for n in CANDIDATOS}
    apos = _memoria(torch)
    lat = {n: _cargas(n, m, device, max(3, rep // 2)) for n, m in modelos.items()}
    pico = _memoria(torch)
    del modelos
    gc.collect()
    return {
        "memoria_modelos_gb": apos["total_gb"] - base["total_gb"],
        "memoria_pico_gb": pico["total_gb"] - base["total_gb"],
        "memoria": {"base": base, "apos_carga": apos, "pico": pico},
        "latencia_com_todos_carregados": lat,
    }


# ---------------------------------------------------------------- LLM via Ollama
def _ollama(caminho: str, corpo: dict | None = None, stream: bool = False):
    req = urllib.request.Request(
        OLLAMA + caminho,
        data=json.dumps(corpo).encode() if corpo else None,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=600)
    if stream:
        return resp
    return json.loads(resp.read())


def medir_llm(modelo: str, repeticoes: int = 3, num_ctx: int = 16384) -> dict:
    textos = _textos_lei(64)

    def prompt(i: int) -> str:
        # Prompt diferente a cada corrida, a partir do 1º token: o Ollama reaproveita o cache do prefixo e uma
        # repetição mediria só a geração. No uso real cada pergunta chega com contexto novo (prefill frio).
        contexto = "\n\n".join(textos[(i * 6) % 58 : (i * 6) % 58 + 6])
        return (
            f"Consulta {i}. Use apenas os trechos abaixo para responder em português simples, em até 5 frases."
            f"\n\n{contexto}\n\nPergunta: {PERGUNTA}"
        )

    opcoes = {"num_ctx": num_ctx, "num_predict": 200, "temperature": 0}
    _ollama(
        "/api/generate",
        {"model": modelo, "keep_alive": -1, "prompt": "", "stream": False, "options": {"num_ctx": num_ctx}},
    )  # só carrega
    ps = next((m for m in _ollama("/api/ps")["models"] if m["name"].startswith(modelo)), {})
    corridas = []
    for i in range(repeticoes):
        t0 = time.perf_counter()
        ttft = None
        final = {}
        with _ollama(
            "/api/generate",
            {"model": modelo, "prompt": prompt(i), "stream": True, "think": False, "options": opcoes, "keep_alive": -1},
            stream=True,
        ) as r:
            for linha in r:
                ev = json.loads(linha)
                if ttft is None and ev.get("response"):
                    ttft = (time.perf_counter() - t0) * 1000
                if ev.get("done"):
                    final = ev
        corridas.append(
            {
                "ttft_ms": ttft,
                "total_s": time.perf_counter() - t0,
                "tokens_prompt": final.get("prompt_eval_count"),
                "tokens_saida": final.get("eval_count"),
                "prefill_tok_s": final.get("prompt_eval_count", 0) / max(final.get("prompt_eval_duration", 1), 1) * 1e9,
                "geracao_tok_s": final.get("eval_count", 0) / max(final.get("eval_duration", 1), 1) * 1e9,
            }
        )
    det = ps.get("details", {})
    return {
        "modelo": modelo,
        "num_ctx": num_ctx,
        "quantizacao": det.get("quantization_level"),
        "parametros": det.get("parameter_size"),
        "memoria_gb": ps.get("size", 0) / GB,
        "memoria_vram_gb": ps.get("size_vram", 0) / GB,
        "ttft_ms_mediana": statistics.median(c["ttft_ms"] for c in corridas if c["ttft_ms"] is not None),
        "geracao_tok_s_mediana": statistics.median(c["geracao_tok_s"] for c in corridas),
        "prefill_tok_s_mediana": statistics.median(c["prefill_tok_s"] for c in corridas),
        "corridas": corridas,
    }


def memoria_sistema() -> dict[str, float]:
    import psutil

    vm = psutil.virtual_memory()
    return {"total_gb": vm.total / GB, "disponivel_gb": vm.available / GB, "usada_pct": vm.percent}


# ---------------------------------------------------------------- orçamento
# Folga mínima: o macOS, o navegador da demo, Docker (Postgres/Redis/MLflow/MinIO) e o backend ficam de fora do
# worker. Medido em uso normal; revisar se a demo mudar.
RESERVA_SISTEMA_GB = 8.0


def orcamento(isolados: list[dict], juntos: dict, llm: dict, ram_total_gb: float) -> dict:
    llm_gb = llm.get("memoria_gb", 0.0)
    modelos_gb = juntos["memoria_pico_gb"]
    worker_gb = llm_gb + modelos_gb
    disponivel = ram_total_gb - RESERVA_SISTEMA_GB
    return {
        "ram_total_gb": ram_total_gb,
        "reserva_sistema_gb": RESERVA_SISTEMA_GB,
        "orcamento_worker_gb": disponivel,
        "llm_gb": llm_gb,
        "modelos_pico_gb": modelos_gb,
        "worker_total_gb": worker_gb,
        "folga_gb": disponivel - worker_gb,
        "cabe": worker_gb <= disponivel,
        "por_modelo_isolado_gb": {m["modelo"]: round(m["memoria_pico_gb"], 2) for m in isolados},
    }


# ---------------------------------------------------------------- relatório
def _md(resultado: dict) -> str:
    o = resultado["orcamento"]
    maq, sis, juntos = resultado["maquina"], resultado["sistema_com_tudo"], resultado["juntos"]
    lin = [
        "# Memória e latência no MacBook M4 — orçamento do worker",
        "",
        f"Gerado por `python -m treino.medir_memoria_latencia` em {resultado['quando']} · "
        f"commit `{resultado['commit'][:12]}` · {maq.get('chip', '?')}, {maq.get('ram_gb', '?')} GB · "
        f"device `{resultado['device']}`.",
        "",
        "## Modelos isolados (um processo por modelo)",
        "",
        "| Modelo | Repositório | Parâmetros | Carga (s) | Memória após carga (GB) | Pico (GB) "
        "| Latência p50 / p95 (ms) |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for m in resultado["isolados"]:
        lat = "; ".join(f"{k}: {v['p50_ms']:.0f} / {v['p95_ms']:.0f}" for k, v in m["latencia"].items())
        par = f"{m['parametros'] / 1e6:.0f} M" if m.get("parametros") else "?"
        lin.append(
            f"| {m['modelo']} | `{m['repo']}` | {par} | {m['carga_s']:.1f} | {m['memoria_modelo_gb']:.2f} | "
            f"{m['memoria_pico_gb']:.2f} | {lat} |"
        )
    llm = resultado["llm"]
    lin += [
        "",
        "## LLM (Ollama, nativo)",
        "",
        "| Modelo | Quantização | Parâmetros | num_ctx | Memória (GB) | 1º token (ms) | Prefill (tok/s) "
        "| Geração (tok/s) |",
        "|---|---|---|---:|---:|---:|---:|---:|",
        f"| `{llm['modelo']}` | {llm.get('quantizacao')} | {llm.get('parametros')} | {llm['num_ctx']} | "
        f"{llm['memoria_gb']:.2f} | {llm['ttft_ms_mediana']:.0f} | {llm['prefill_tok_s_mediana']:.0f} | "
        f"{llm['geracao_tok_s_mediana']:.1f} |",
        "",
        "## Todos juntos (como o worker carrega) + LLM",
        "",
        f"- Modelos de ML no mesmo processo: **{juntos['memoria_modelos_gb']:.2f} GB** após carga, "
        f"**{juntos['memoria_pico_gb']:.2f} GB** no pico das cargas típicas.",
        f"- LLM no Ollama: **{o['llm_gb']:.2f} GB**.",
        f"- Memória do sistema no pior momento (tudo carregado): {sis['disponivel_gb']:.1f} GB disponíveis "
        f"de {sis['total_gb']:.0f} GB ({sis['usada_pct']:.0f}% em uso).",
        "",
        "| Latência com todos carregados | p50 / p95 (ms) |",
        "|---|---|",
    ]
    for nome, cargas in juntos["latencia_com_todos_carregados"].items():
        for k, v in cargas.items():
            lin.append(f"| {nome} · {k} | {v['p50_ms']:.0f} / {v['p95_ms']:.0f} |")
    lin += [
        "",
        "## Orçamento de memória do worker",
        "",
        "| Item | GB |",
        "|---|---:|",
        f"| RAM total | {o['ram_total_gb']:.1f} |",
        f"| Reserva: macOS, Docker (Postgres, Redis, MLflow, MinIO), navegador | {o['reserva_sistema_gb']:.1f} |",
        f"| **Orçamento do worker** | **{o['orcamento_worker_gb']:.1f}** |",
        f"| LLM (`{llm['modelo']}`) | {o['llm_gb']:.2f} |",
        f"| Modelos de ML juntos (pico) | {o['modelos_pico_gb']:.2f} |",
        f"| **Worker total** | **{o['worker_total_gb']:.2f}** |",
        f"| **Folga** | **{o['folga_gb']:.2f}** |",
        "",
        f"**Cabe no orçamento: {'sim' if o['cabe'] else 'NÃO'}.**",
        "",
    ]
    return "\n".join(lin)


def _subprocesso(nome: str, device: str, rep: int) -> dict:
    cmd = [
        sys.executable,
        "-m",
        "treino.medir_memoria_latencia",
        "--um",
        nome,
        "--device",
        device,
        "--repeticoes",
        str(rep),
    ]
    saida = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, check=True).stdout
    return json.loads(saida.strip().splitlines()[-1])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--um", choices=list(CANDIDATOS))
    ap.add_argument("--juntos", action="store_true", help="(interno) mede todos no mesmo processo")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--repeticoes", type=int, default=20)
    ap.add_argument("--llm", default=LLM_PADRAO)
    ap.add_argument("--num-ctx", type=int, default=16384, help="contexto da LLM (o ClienteOllama da entrega usa 16384)")
    ap.add_argument("--sem-mlflow", action="store_true")
    a = ap.parse_args()

    if a.um:
        print(json.dumps(medir_um(a.um, a.device, a.repeticoes)))
        return
    if a.juntos:
        print(json.dumps(medir_juntos(a.device, a.repeticoes)))
        return

    import datetime as dt

    from treino.comum import commit_atual

    print("medindo modelos isolados…", flush=True)
    isolados = []
    for nome in CANDIDATOS:
        r = _subprocesso(nome, a.device, a.repeticoes)
        print(f"  {nome}: {r['memoria_pico_gb']:.2f} GB, carga {r['carga_s']:.1f}s", flush=True)
        isolados.append(r)
    print(f"medindo LLM {a.llm}…", flush=True)
    llm = medir_llm(a.llm, num_ctx=a.num_ctx)
    print(f"  {llm['memoria_gb']:.2f} GB, {llm['geracao_tok_s_mediana']:.1f} tok/s", flush=True)
    print("medindo todos juntos com a LLM carregada…", flush=True)
    cmd = [
        sys.executable,
        "-m",
        "treino.medir_memoria_latencia",
        "--juntos",
        "--device",
        a.device,
        "--repeticoes",
        str(a.repeticoes),
    ]
    proc = subprocess.Popen(cmd, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    # amostra a memória do sistema enquanto o worker simulado roda: pega o pior momento
    pior = memoria_sistema()
    while proc.poll() is None:
        agora = memoria_sistema()
        if agora["disponivel_gb"] < pior["disponivel_gb"]:
            pior = agora
        time.sleep(0.5)
    juntos = json.loads(proc.stdout.read().strip().splitlines()[-1])
    ram_total = memoria_sistema()["total_gb"]
    resultado = {
        "quando": dt.datetime.now().isoformat(timespec="seconds"),
        "commit": commit_atual(),
        "maquina": maquina(),
        "device": a.device,
        "isolados": isolados,
        "llm": llm,
        "juntos": juntos,
        "sistema_com_tudo": pior,
        "orcamento": orcamento(isolados, juntos, llm, ram_total),
    }
    js = salvar_json(resultado, RELATORIOS / "memoria_latencia_m4.json")
    md = RELATORIOS / "memoria_latencia_m4.md"
    md.write_text(_md(resultado), encoding="utf-8")
    print(f"relatório: {md}\n{json.dumps(resultado['orcamento'], indent=2)}")

    if not a.sem_mlflow:
        mlflow = iniciar_mlflow("orcamento-memoria-worker")
        with mlflow.start_run(run_name=f"m4-{a.llm}-{a.device}"):
            mlflow.set_tags(tags_padrao(tarefa="memoria_latencia", llm=a.llm))
            for m in isolados:
                mlflow.log_metric(f"{m['modelo']}.memoria_pico_gb", m["memoria_pico_gb"])
                mlflow.log_metric(f"{m['modelo']}.carga_s", m["carga_s"])
                for carga, v in m["latencia"].items():
                    mlflow.log_metric(f"{m['modelo']}.{carga}.p50_ms", v["p50_ms"])
                    mlflow.log_metric(f"{m['modelo']}.{carga}.p95_ms", v["p95_ms"])
            mlflow.log_metrics(
                {
                    "llm.memoria_gb": llm["memoria_gb"],
                    "llm.ttft_ms": llm["ttft_ms_mediana"],
                    "llm.geracao_tok_s": llm["geracao_tok_s_mediana"],
                }
            )
            mlflow.log_metrics(
                {
                    f"orcamento.{k}": float(v)
                    for k, v in resultado["orcamento"].items()
                    if isinstance(v, int | float | bool)
                }
            )
            mlflow.log_artifact(str(js))
            mlflow.log_artifact(str(md))
        print("registrado no MLflow (experimento orcamento-memoria-worker)")


if __name__ == "__main__":
    main()
