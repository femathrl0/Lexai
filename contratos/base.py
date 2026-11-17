from pydantic import BaseModel, ConfigDict, Field


class Contrato(BaseModel):
    """Base de todos os contratos: campos extras são proibidos, para que mudanças passem por PR."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Posicao(Contrato):
    """Página e caixa do trecho no documento original (o app mostra o trecho literal ao lado)."""

    pagina: int = Field(ge=1)
    x0: float
    y0: float
    x1: float
    y1: float


class Versoes(Contrato):
    """Identificadores gravados em cada resultado (RNF03)."""

    modelos: dict[str, str] = Field(default_factory=dict, description="nome do modelo -> versão no MLflow")
    prompt: str | None = None
    indices: dict[str, str] = Field(default_factory=dict, description="corpus_juridico/trechos_usuario -> versão")
