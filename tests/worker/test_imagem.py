import numpy as np
import pytest

from worker.leitura.imagem import LIMIAR_NITIDEZ, estimar_inclinacao, ler_imagens, nitidez

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402


def pagina_de_texto(angulo=0.0, borrar=0):
    im = Image.new("L", (1200, 1600), 255)
    d = ImageDraw.Draw(im)
    for i in range(40):
        d.rectangle((100, 100 + i * 35, 1100, 100 + i * 35 + 12), fill=0)  # "linhas de texto"
        for j in range(0, 1000, 60):
            d.rectangle((100 + j + 45, 100 + i * 35, 100 + j + 60, 100 + i * 35 + 12), fill=255)  # espaços
    if angulo:
        im = im.rotate(angulo, fillcolor=255)
    if borrar:
        im = im.filter(ImageFilter.GaussianBlur(borrar))
    return np.asarray(im)


class MotorFalso:
    nome = "falso"

    def __init__(self, confianca=0.95):
        self.confianca, self.chamadas = confianca, 0

    def reconhecer(self, imagem):
        self.chamadas += 1
        return [("ACÓRDÃO", self.confianca, (0, 0, 10, 10)), ("Nego provimento ao recurso.", self.confianca, (0, 20, 10, 30))]


def test_nitidez_separa_foto_borrada():
    assert nitidez(pagina_de_texto()) > LIMIAR_NITIDEZ > nitidez(pagina_de_texto(borrar=6))


def test_inclinacao_estimada_e_desfeita():
    assert abs(estimar_inclinacao(pagina_de_texto(angulo=5)) + 5) <= 1
    assert abs(estimar_inclinacao(pagina_de_texto())) <= 1


def test_foto_boa_vira_documento_ocr():
    doc = ler_imagens("t", [pagina_de_texto(angulo=3)], MotorFalso())
    assert doc.origem == "ocr" and doc.qualidade_leitura >= 0.9 and doc.motivo_baixa_qualidade is None
    assert [b.texto for b in doc.paginas[0].blocos][1].startswith("Nego")


def test_foto_borrada_e_recusada_sem_chamar_ocr():
    motor = MotorFalso()
    doc = ler_imagens("t", [pagina_de_texto(borrar=6)], motor)
    assert doc.qualidade_leitura < 0.5 and "nitidez" in doc.motivo_baixa_qualidade and motor.chamadas == 0


def test_ocr_com_baixa_confianca_pede_nova_foto():
    doc = ler_imagens("t", [pagina_de_texto()], MotorFalso(confianca=0.3))
    assert doc.qualidade_leitura < 0.5 and "pouco legível" in doc.motivo_baixa_qualidade
