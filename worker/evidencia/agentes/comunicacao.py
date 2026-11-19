from __future__ import annotations

import os
import re
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel

from contratos import Explicacao, FraseGerada
from contratos.agentes import EstadoTarefa

from .base import Agente, Saida
from .llm import LLM

# v2 desde 19/11 (bateria de 17/11). Para comparar com a versão anterior: LEXAI_PROMPT_COMUNICACAO=comunicacao/v1
PROMPT_ID = os.getenv("LEXAI_PROMPT_COMUNICACAO", "comunicacao/v2")
PROMPT = (Path(__file__).resolve().parents[3] / "prompts" / f"{PROMPT_ID}.md").read_text(encoding="utf-8")
PROMPT_SHA256 = sha256(PROMPT.encode()).hexdigest()

# Glossário do manual + termos frequentes nas respostas. A Curadoria revisa as definições.
GLOSSARIO = {
    "dispositivo": "parte final da decisão, onde o juiz diz o que foi decidido",
    "fundamentação": "parte em que o juiz explica as razões da decisão",
    "procedente": "pedido aceito pelo juiz",
    "improcedente": "pedido recusado pelo juiz",
    "parcialmente procedente": "pedido aceito em parte",
    "súmula": "entendimento consolidado do TST sobre um tema",
    "verbas rescisórias": "valores pagos ao trabalhador quando o contrato termina",
    "aviso prévio": "comunicação antecipada do fim do contrato, ou o pagamento que a substitui",
    "rescisão": "fim do contrato de trabalho",
    "justa causa": "falta grave que permite encerrar o contrato sem algumas verbas",
    "FGTS": "Fundo de Garantia do Tempo de Serviço, depósito mensal feito pelo empregador",
    "CTPS": "Carteira de Trabalho e Previdência Social",
    "prescrição": "perda do prazo para cobrar um direito na Justiça",
    "reclamante": "quem entrou com a ação (em geral, o trabalhador)",
    "reclamada": "quem é processado (em geral, o empregador)",
    "estabilidade": "período em que o trabalhador não pode ser dispensado sem justa causa",
    "insalubridade": "trabalho exposto a agentes que fazem mal à saúde",
}


class FraseCom(BaseModel):
    ordem: int
    texto: str


class ComunicacaoLLM(BaseModel):
    frases: list[FraseCom]


def _silabas(palavra: str) -> int:
    return max(1, len(re.findall(r"[aeiouáéíóúâêôãõàü]+", palavra.lower())))


def flesch_pt(texto: str) -> float:
    """Índice de Flesch adaptado ao português (Martins et al., 1996). Maior = mais fácil (75+ = fácil)."""
    frases = max(1, len(re.findall(r"[.!?]+", texto)) or 1)
    palavras = re.findall(r"[A-Za-zÀ-ÿ]+", texto)
    if not palavras:
        return 0.0
    return round(248.835 - 1.015 * len(palavras) / frases - 84.6 * sum(map(_silabas, palavras)) / len(palavras), 1)


class AgenteComunicacao(Agente):
    nome = "comunicacao"
    responsabilidade = ("Communication Agent: adapta cada frase ao público (leigo ou advogado), explica termos com o "
                        "glossário e mede a legibilidade, sem mudar o conteúdo nem o trecho citado.")

    def __init__(self, llm: LLM):
        self.llm = llm

    def executar(self, estado: EstadoTarefa) -> Saida:
        originais = estado.explicacao.frases
        texto = " ".join(f.texto for f in originais)
        termos = {k: v for k, v in GLOSSARIO.items() if k.lower() in texto.lower()}
        usuario = (f"PÚBLICO: {estado.persona}\nGLOSSÁRIO: {termos or 'nenhum termo'}\n\nFRASES:\n" +
                   "\n".join(f"{f.ordem}. {f.texto}" for f in originais))
        r = self.llm.gerar(PROMPT, usuario, ComunicacaoLLM)
        novas = {f.ordem: f.texto.strip() for f in r.frases if f.texto.strip()}
        # Contrato com a Validação: mesmas frases, mesma ordem, mesmo trecho. Frase perdida volta à versão original.
        mantidas = [o.ordem for o in originais if o.ordem not in novas]
        frases = [FraseGerada(ordem=o.ordem, texto=novas.get(o.ordem, o.texto), trecho_id=o.trecho_id) for o in originais]
        antes, depois = flesch_pt(texto), flesch_pt(" ".join(f.texto for f in frases))
        estado.explicacao = Explicacao(tarefa_id=estado.tarefa_id, prompt_id=estado.explicacao.prompt_id,
                                       modelo_llm=estado.explicacao.modelo_llm, frases=frases)
        return Saida(f"adaptou {len(frases) - len(mantidas)} frases para '{estado.persona}' "
                     f"(legibilidade {antes} → {depois})" + (f"; manteve originais {mantidas}" if mantidas else ""),
                     dict(prompt=PROMPT_ID, legibilidade_antes=antes, legibilidade_depois=depois,
                          termos_glossario=list(termos), frases=[f.model_dump() for f in frases]))
