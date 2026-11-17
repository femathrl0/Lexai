"""Contratos tipados entre módulos (manual: "Contratos entre módulos").

Mudar um contrato exige um pull request próprio, aprovado por quem produz e por quem consome.
"""
from .base import Versoes
from .classificacao import Campo, Classificacao, ResultadoPedido
from .documento import Bloco, DocumentoLido, Pagina
from .eventos import Aviso, Concluido, Erro, Evento, Frase, Status
from .evidencias import Evidencias, TrechoEvidencia
from .explicacao import Explicacao, FraseGerada
from .resposta import FraseAprovada, RespostaVerificada
from .segmentos import Segmentos, Trecho

__all__ = [
    "Aviso", "Bloco", "Campo", "Classificacao", "Concluido", "DocumentoLido", "Erro", "Evento", "Evidencias",
    "Explicacao", "Frase", "FraseAprovada", "FraseGerada", "Pagina", "RespostaVerificada", "ResultadoPedido",
    "Segmentos", "Status", "Trecho", "TrechoEvidencia", "Versoes",
]
