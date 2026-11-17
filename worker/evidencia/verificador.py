"""Verificador (modelo: Eng. de ML; integração: Eng. de IA).

Cross-encoder NLI sobre (frase, trecho citado): sustenta | contradiz | nao_trata. Última barreira contra alucinação.
Candidato inicial: mDeBERTa-v3 treinado em XNLI, escolhido por benchmark nos pares-ouro.
"""
from typing import Literal

Veredito = Literal["sustenta", "contradiz", "nao_trata"]


def verificar(frase: str, trecho: str) -> tuple[Veredito, float]:
    raise NotImplementedError("TODO: carregar o verificador 'em uso' do MLflow")
