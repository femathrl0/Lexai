"""O backend nunca importa biblioteca de ML (manual: "só o worker carrega modelos")."""
import ast
from pathlib import Path

PROIBIDAS = {"torch", "transformers", "sentence_transformers", "sklearn", "peft", "mlflow", "pymupdf", "fitz",
             "paddleocr", "ollama", "numpy", "pandas"}
BACKEND = Path(__file__).resolve().parents[2] / "backend"


def test_backend_nao_importa_ml():
    achados = []
    for arquivo in BACKEND.rglob("*.py"):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            nomes = [a.name for a in no.names] if isinstance(no, ast.Import) else (
                [no.module] if isinstance(no, ast.ImportFrom) and no.module else [])
            achados += [f"{arquivo.name}: {n}" for n in nomes if n.split(".")[0] in PROIBIDAS]
    assert not achados, achados
