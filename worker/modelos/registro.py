"""Resolução dos modelos "em uso" (Eng. de ML e MLOps).

Estágios: candidato → aprovado → em-uso. Só Eng. de ML + Curadoria promovem para "em-uso" (`treino/promover.py`).

O worker só carrega versão em uso. A resolução tem duas fontes, nesta ordem:
1. **MLflow** (`MLFLOW_TRACKING_URI`): a versão com alias `em-uso` de cada modelo registrado. As tags da versão
   (`repo`, `revisao`, `limiares` em JSON) sobrepõem os valores fixados;
2. **fixado no repositório** (`worker/modelos/em_uso.yml`): vale quando o MLflow não está no ar (CI, contêiner
   offline, máquina sem o Compose) ou quando o modelo não tem versão em uso no registro.

Resolver não carrega pesos: quem usa (buscador, verificador, classificador) carrega na primeira chamada. Assim o teste
roda sem modelos e o worker sabe, antes de carregar, quais versões vão para `Versoes.modelos` de cada resposta.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MODELOS = (
    "classificador_tipo_fase",
    "segmentador",
    "extrator_campos",
    "resultado_pedido",
    "intencao_guarda",
    "reranker",
    "verificador_nli",
    "embeddings",
)
ALIAS_EM_USO = "em-uso"
ARQUIVO_FIXADOS = Path(__file__).with_name("em_uso.yml")


def ler_fixados(caminho: Path = ARQUIVO_FIXADOS) -> dict[str, dict]:
    import yaml

    return yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}


FIXADOS: dict[str, dict] = ler_fixados()


@dataclass(frozen=True)
class ModeloEmUso:
    nome: str
    tipo: str  # regras | hf | sklearn | mlflow
    versao: str
    origem: str  # "mlflow" ou "fixado"
    repo: str | None = None
    revisao: str | None = None
    uri: str | None = None  # models:/<nome>@em-uso quando vem do MLflow
    limiares: dict[str, Any] = field(default_factory=dict)

    @property
    def rotulo(self) -> str:
        """Texto curto que vai para Versoes.modelos da resposta (rastreabilidade, RNF03)."""
        if self.repo:
            return f"{self.repo}@{(self.revisao or 'main')[:8]}"
        return f"{self.nome}@{self.versao}"

    def limiar(self, chave: str, padrao: Any = None) -> Any:
        return self.limiares.get(chave, padrao)


def _de_fixado(nome: str, cfg: dict) -> ModeloEmUso:
    versao = cfg.get("versao") or (cfg.get("revisao") or "main")[:12]
    return ModeloEmUso(nome=nome, tipo=cfg.get("tipo", "regras"), versao=str(versao), origem="fixado",
                       repo=cfg.get("repo"), revisao=cfg.get("revisao"), limiares=dict(cfg.get("limiares") or {}))


def _de_mlflow(cliente, nome: str, base: ModeloEmUso | None) -> ModeloEmUso | None:
    try:
        mv = cliente.get_model_version_by_alias(nome, ALIAS_EM_USO)
    except Exception:  # noqa: BLE001 - modelo sem registro ou sem alias: fica o fixado
        return None
    tags = dict(mv.tags or {})
    limiares = dict(base.limiares if base else {})
    if "limiares" in tags:
        limiares.update(json.loads(tags["limiares"]))
    return ModeloEmUso(nome=nome, tipo=tags.get("tipo", "mlflow"), versao=str(mv.version), origem="mlflow",
                       repo=tags.get("repo") or (base.repo if base else None),
                       revisao=tags.get("revisao") or (base.revisao if base else None),
                       uri=f"models:/{nome}@{ALIAS_EM_USO}", limiares=limiares)


def _cliente_mlflow(uri: str | None):
    if not uri:
        return None
    try:
        from mlflow import MlflowClient

        cliente = MlflowClient(tracking_uri=uri)
        cliente.search_registered_models(max_results=1)  # falha rápido se o servidor não responde
        return cliente
    except Exception:  # noqa: BLE001 - sem MLflow o worker segue com os fixados
        return None


def carregar_em_uso(tracking_uri: str | None = None, cliente=None, fixados: dict[str, dict] | None = None
                    ) -> dict[str, ModeloEmUso]:
    """{nome: ModeloEmUso} para todos os MODELOS. Nunca levanta por falta de MLflow."""
    fixados = FIXADOS if fixados is None else fixados
    if cliente is None:
        cliente = _cliente_mlflow(tracking_uri if tracking_uri is not None else os.getenv("MLFLOW_TRACKING_URI"))
    saida = {}
    for nome in MODELOS:
        base = _de_fixado(nome, fixados[nome]) if nome in fixados else None
        escolhido = (_de_mlflow(cliente, nome, base) if cliente is not None else None) or base
        if escolhido is not None:
            saida[nome] = escolhido
    return saida


_EM_USO: dict[str, ModeloEmUso] | None = None


def em_uso() -> dict[str, ModeloEmUso]:
    """Resolução única por processo (o worker resolve ao iniciar; os componentes leem daqui)."""
    global _EM_USO
    if _EM_USO is None:
        _EM_USO = carregar_em_uso()
    return _EM_USO


def versoes(modelos: dict[str, ModeloEmUso]) -> dict[str, str]:
    """Para Versoes.modelos: {nome: rótulo}."""
    return {n: m.rotulo for n, m in modelos.items()}
