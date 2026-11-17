"""Verificador (modelo: Eng. de ML; integração: Eng. de IA).

Cross-encoder NLI sobre (trecho citado → frase): sustenta | contradiz | nao_trata. Última barreira contra
alucinação. Candidato inicial: mDeBERTa-v3 treinado em MNLI/XNLI (escolha final por benchmark nos pares-ouro).
"""
from __future__ import annotations

from typing import Literal, Protocol

Veredito = Literal["sustenta", "contradiz", "nao_trata"]
MODELO_PADRAO = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"


class Verificador(Protocol):
    modelo: str

    def verificar(self, frase: str, trecho: str) -> tuple[Veredito, dict[str, float]]: ...


class VerificadorNLI:
    def __init__(self, modelo: str = MODELO_PADRAO, device: str | None = None, max_length: int = 512):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.modelo, self.max_length, self._torch = modelo, max_length, torch
        self.tok = AutoTokenizer.from_pretrained(modelo)
        self.net = AutoModelForSequenceClassification.from_pretrained(modelo).eval()
        if device:
            self.net.to(device)
        self.device = device
        rotulos = {i: r.lower() for i, r in self.net.config.id2label.items()}
        self.indice = {"sustenta": next(i for i, r in rotulos.items() if r.startswith("entail")),
                       "nao_trata": next(i for i, r in rotulos.items() if r.startswith("neutral")),
                       "contradiz": next(i for i, r in rotulos.items() if r.startswith("contrad"))}

    def verificar(self, frase: str, trecho: str) -> tuple[Veredito, dict[str, float]]:
        # Premissa = trecho citado (truncado se longo); hipótese = frase da resposta.
        x = self.tok(trecho, frase, truncation="only_first", max_length=self.max_length, return_tensors="pt")
        if self.device:
            x = {k: v.to(self.device) for k, v in x.items()}
        with self._torch.no_grad():
            p = self._torch.softmax(self.net(**x).logits[0], dim=-1).tolist()
        probs = {k: round(p[i], 4) for k, i in self.indice.items()}
        return max(probs, key=probs.get), probs
