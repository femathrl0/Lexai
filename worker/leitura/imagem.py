"""Leitor de imagem (semana 5, bloqueio da #29): foto ou PDF sem texto nativo -> checagem de qualidade -> OCR.

1. **Nitidez**: variância do Laplaciano da imagem em tons de cinza (foto tremida/borrada tem pouca borda).
2. **Inclinação**: ângulo que maximiza a variância do perfil horizontal (linhas de texto alinhadas dão picos);
   a imagem é endireitada antes do OCR.
3. **OCR**: PaddleOCR (grupo opcional `ocr`) atrás de `MotorOCR`; o teste usa um motor falso.

Foto abaixo do limiar de nitidez, sem texto reconhecido ou com confiança média baixa volta com `qualidade_leitura`
baixa e o motivo; o pipeline então publica `Aviso(categoria="nova_foto")` pedindo outra foto (portão #35).
Limiares fixados aqui até a medição com o conjunto de fotos do grupo (#29/#30).
"""
from __future__ import annotations

from typing import Protocol

import numpy as np

from contratos import Bloco, DocumentoLido, Pagina
from contratos.base import Posicao

LIMIAR_NITIDEZ = 60.0  # variância do Laplaciano (imagem com lado maior ~1600 px)
LIMIAR_CONFIANCA_OCR = 0.6
ANGULO_MAXIMO = 10
LADO_ANALISE = 1600


class MotorOCR(Protocol):
    nome: str

    def reconhecer(self, imagem: np.ndarray) -> list[tuple[str, float, tuple[float, float, float, float]]]:
        """[(texto, confiança 0–1, (x0, y0, x1, y1))] por linha."""
        ...


# ---------------------------------------------------------------- qualidade (numpy puro, testado no CI)
def cinza(imagem: np.ndarray) -> np.ndarray:
    if imagem.ndim == 3:
        imagem = imagem[..., :3] @ np.array([0.299, 0.587, 0.114])
    return imagem.astype(np.float32)


def nitidez(imagem: np.ndarray) -> float:
    g = cinza(imagem)
    lap = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    return float(lap.var())


def _girar(g: np.ndarray, angulo: float) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.fromarray(g.astype(np.uint8)).rotate(angulo, expand=False, fillcolor=255), dtype=np.float32)


def estimar_inclinacao(imagem: np.ndarray, passo: float = 1.0) -> float:
    """Ângulo (graus) que, aplicado com `endireitar`, deixa as linhas de texto na horizontal."""
    g = cinza(imagem)
    if max(g.shape) > 800:
        f = 800 / max(g.shape)
        from PIL import Image

        g = np.asarray(Image.fromarray(g.astype(np.uint8)).resize((int(g.shape[1] * f), int(g.shape[0] * f))),
                       dtype=np.float32)
    melhor, ang = -1.0, 0.0
    for a in np.arange(-ANGULO_MAXIMO, ANGULO_MAXIMO + passo, passo):
        perfil = (255 - _girar(g, a)).sum(axis=1)  # tinta por linha da imagem girada
        v = float(perfil.var())
        if v > melhor:
            melhor, ang = v, float(a)
    return ang


def endireitar(imagem: np.ndarray, angulo: float) -> np.ndarray:
    return imagem if abs(angulo) < 0.5 else _girar(cinza(imagem), angulo)


def reduzir(imagem: np.ndarray, lado: int = LADO_ANALISE) -> np.ndarray:
    if max(imagem.shape[:2]) <= lado:
        return imagem
    from PIL import Image

    f = lado / max(imagem.shape[:2])
    im = Image.fromarray(imagem.astype(np.uint8))
    return np.asarray(im.resize((int(im.width * f), int(im.height * f))))


# ---------------------------------------------------------------- OCR
class PaddleOCRMotor:
    """Adaptador do PaddleOCR (2.x `.ocr` e 3.x `.predict`). Só no worker, com `uv sync --group ocr`."""

    nome = "paddleocr"

    def __init__(self, idioma: str = "pt"):
        from paddleocr import PaddleOCR

        self._ocr = PaddleOCR(lang=idioma)

    def reconhecer(self, imagem):
        img = np.stack([cinza(imagem).astype(np.uint8)] * 3, axis=-1)
        if hasattr(self._ocr, "predict"):  # PaddleOCR 3.x
            saida = []
            for r in self._ocr.predict(img):
                for texto, conf, caixa in zip(r["rec_texts"], r["rec_scores"], r["rec_boxes"], strict=False):
                    x0, y0, x1, y1 = (float(v) for v in caixa)
                    saida.append((texto, float(conf), (x0, y0, x1, y1)))
            return saida
        linhas = self._ocr.ocr(img) or [[]]
        saida = []
        for caixa, (texto, conf) in linhas[0] or []:
            xs, ys = [p[0] for p in caixa], [p[1] for p in caixa]
            saida.append((texto, float(conf), (min(xs), min(ys), max(xs), max(ys))))
        return saida


_MOTOR: MotorOCR | None = None


def motor_padrao() -> MotorOCR:
    global _MOTOR
    if _MOTOR is None:
        _MOTOR = PaddleOCRMotor()
    return _MOTOR


def _avaliar_pagina(imagem: np.ndarray, motor: MotorOCR) -> tuple[list, float, str | None, float]:
    """(linhas OCR, qualidade 0–1, motivo, ângulo)"""
    img = reduzir(imagem)
    n = nitidez(img)
    if n < LIMIAR_NITIDEZ:
        return [], 0.2, f"foto sem nitidez (borrada ou tremida: {n:.0f} < {LIMIAR_NITIDEZ:.0f})", 0.0
    angulo = estimar_inclinacao(img)
    linhas = motor.reconhecer(endireitar(img, angulo))
    if not linhas:
        return [], 0.1, "não encontrei texto na imagem", angulo
    conf = sum(c for _, c, _ in linhas) / len(linhas)
    if conf < LIMIAR_CONFIANCA_OCR:
        return linhas, conf, f"texto pouco legível (confiança média do OCR {conf:.2f})", angulo
    return linhas, min(1.0, conf), None, angulo


def ler_imagens(tarefa_id: str, imagens: list[np.ndarray], motor: MotorOCR | None = None) -> DocumentoLido:
    motor = motor or motor_padrao()
    paginas, qualidades, motivos = [], [], []
    for n, imagem in enumerate(imagens, start=1):
        linhas, q, motivo, _ = _avaliar_pagina(imagem, motor)
        qualidades.append(q)
        if motivo:
            motivos.append(f"página {n}: {motivo}" if len(imagens) > 1 else motivo)
        paginas.append(Pagina(numero=n, blocos=[
            Bloco(id=f"p{n}b{i}", texto=t.strip(), posicao=Posicao(pagina=n, x0=c[0], y0=c[1], x1=c[2], y1=c[3]))
            for i, (t, _, c) in enumerate(linhas) if t.strip()]))
    qualidade = min(qualidades) if qualidades else 0.0
    return DocumentoLido(tarefa_id=tarefa_id, origem="ocr", qualidade_leitura=round(qualidade, 3),
                         motivo_baixa_qualidade="; ".join(motivos) or None, paginas=paginas)


def ler_imagem(tarefa_id: str, caminho: str, motor: MotorOCR | None = None) -> DocumentoLido:
    from PIL import Image, ImageOps

    with Image.open(caminho) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")  # foto do celular vem girada pelo EXIF
        return ler_imagens(tarefa_id, [np.asarray(im)], motor)


def ler_pdf_como_imagem(tarefa_id: str, caminho: str, motor: MotorOCR | None = None, dpi: int = 200) -> DocumentoLido:
    import pymupdf

    imagens = []
    with pymupdf.open(caminho) as doc:
        for pagina in doc:
            pix = pagina.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            imagens.append(np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width))
    if not imagens:
        return DocumentoLido(tarefa_id=tarefa_id, origem="ocr", qualidade_leitura=0.0,
                             motivo_baixa_qualidade="PDF sem páginas", paginas=[])
    return ler_imagens(tarefa_id, imagens, motor)
