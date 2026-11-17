import pytest

pytest.importorskip("pandas", reason="instale o grupo 'legado': uv sync --group legado")
pytest.importorskip("pyarrow", reason="instale o grupo 'legado': uv sync --group legado")


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.legado)
