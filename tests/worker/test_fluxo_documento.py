"""Portão da semana 4 (#28): um PDF entra pela fila e o app recebe, frase a frase, uma explicação com fontes — no CI,
com Redis falso e agentes simulados (sem modelos)."""
import json

import fakeredis
import pytest

from contratos.eventos import EVENTO
from tests.agentes.fakes import sistema
from worker.filas import canal_tarefa
from worker.pipelines import processar_documento

pymupdf = pytest.importorskip("pymupdf")

ACORDAO = """PODER JUDICIARIO
IDENTIFICACAO
PROCESSO n. 0000566-05.2024.5.10.0001 - RO
RELATOR(A): Desembargador PEDRO LUIS VICENTIN FOLTRAN
RECORRENTE: M. V. M.
RECORRIDO: C. E. F.
EMENTA
HORAS EXTRAS. CONTROLES DE JORNADA. HORAS EXTRAS DEVIDAS.
DANO MORAL. NAO CONFIGURADO.
Recurso do reclamante conhecido e desprovido.
RELATORIO
Contra a sentenca recorreu o reclamante.
FUNDAMENTACAO
Conheco do recurso.
CONCLUSAO
Conheco do recurso e, no merito, nego-lhe provimento.
ACORDAO
ACORDAM os integrantes da Turma em negar provimento ao recurso."""

BOA = [dict(texto="O empregador paga as verbas rescisórias em até dez dias após o fim do contrato.", trecho="T1")]


def _pdf(tmp_path, texto):
    doc = pymupdf.open()
    pagina = doc.new_page()
    y = 60
    for paragrafo in texto.split("\n"):
        pagina.insert_text((50, y), paragrafo, fontsize=9)
        y += 14
    caminho = tmp_path / "decisao.pdf"
    doc.save(caminho)
    return str(caminho)


def _eventos(redis, tarefa_id, rodar):
    ps = redis.pubsub()
    ps.subscribe(canal_tarefa(tarefa_id))
    ps.get_message()
    rodar()
    saida = []
    while (m := ps.get_message(timeout=0.2)) is not None:
        if m["type"] == "message":
            saida.append(EVENTO.validate_python(json.loads(m["data"])))
    return saida


def test_pdf_pela_fila_vira_frases_com_fonte(tmp_path):
    r = fakeredis.FakeRedis()
    orq, _, _ = sistema([BOA])
    caminho = _pdf(tmp_path, ACORDAO)
    eventos = _eventos(r, "t1", lambda: processar_documento("t1", "u1", caminho, guardar=False, redis=r, orquestrador=orq))
    tipos = [e.tipo for e in eventos]
    assert tipos[0] == "status" and tipos[-1] == "concluido"
    frases = [e for e in eventos if e.tipo == "frase"]
    assert [f.ordem for f in frases] == list(range(len(frases)))  # frase a frase, sem buraco na numeração
    assert all(f.fonte and f.trecho_texto for f in frases)  # cada frase com a fonte e o trecho literal
    textos = " ".join(f.texto for f in frases)
    assert "recurso ordinário" in textos and "desprovido" in textos
    assert any(f.fonte.startswith("seu documento") for f in frases) and any(f.fonte.startswith("CLT") for f in frases)
    assert "M. V. M." not in textos  # nenhum nome de parte nas frases
    assert "classificador_tipo_fase" in eventos[-1].versoes.modelos
    assert not (tmp_path / "decisao.pdf").exists()  # sem opt-in, o original é apagado


def test_pdf_sem_texto_pede_nova_foto(tmp_path):
    r = fakeredis.FakeRedis()
    doc = pymupdf.open()
    doc.new_page()
    caminho = tmp_path / "vazio.pdf"
    doc.save(caminho)
    eventos = _eventos(r, "t2", lambda: processar_documento("t2", "u1", str(caminho), guardar=True, redis=r,
                                                           orquestrador=sistema([])[0]))
    assert any(e.tipo == "aviso" and e.categoria == "nova_foto" for e in eventos)
    assert eventos[-1].tipo == "concluido" and caminho.exists()
