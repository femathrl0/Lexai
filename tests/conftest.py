import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _previsoes_em_pasta_temporaria(tmp_path, monkeypatch):
    """O log de previsões (worker/modelos/monitoramento.py) nunca escreve em dados/ durante os testes."""
    monkeypatch.setenv("LEXAI_PREVISOES_DIR", str(tmp_path / "previsoes"))
