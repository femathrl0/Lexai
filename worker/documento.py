"""Análise de um documento enviado (fluxo do documento, issue #24 e bloqueio das #25/#26): leitura → segmentação →
tipo e fase → campos → resultado → frases sobre o documento, cada uma com o trecho literal do próprio documento.

As frases sobre o documento são **fatos lidos nele** por regras (tipo, resultado do recurso, pedidos e o resultado de
cada um), sempre com o trecho de onde saíram, e passam pelas mesmas regras de saída da Validação
(`validacao.motivo_por_regra`) antes de publicar. A explicação jurídica (o que a lei diz sobre os pedidos) vem depois,
pelo sistema multiagente, com as fontes do corpus jurídico e o verificador NLI como último portão.

Nenhum nome de parte entra nas frases (RNF01): o extrator só devolve papéis.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from contratos import Classificacao, DocumentoLido, Segmentos
from contratos.eventos import Frase

from .modelos import extrator_campos, resultado_pedido, tipo_documento
from .modelos.registro import ModeloEmUso

TEXTO_RECURSO = {"provido": "foi provido (o tribunal deu razão a quem recorreu)",
                 "parcialmente_provido": "foi parcialmente provido (o tribunal deu razão em parte a quem recorreu)",
                 "desprovido": "foi desprovido (o tribunal manteve a decisão anterior)",
                 "nao_conhecido": "não foi conhecido (o tribunal não chegou a analisar o mérito)"}
NOME_PARTE = {"outro": "cabeçalho e ementa", "relatorio": "relatório", "fundamentacao": "fundamentação",
              "dispositivo": "dispositivo"}
TEXTO_PEDIDO = {"procedente": "foi reconhecido", "improcedente": "não foi reconhecido",
                "parcialmente_procedente": "foi reconhecido em parte"}


@dataclass
class Analise:
    segmentos: Segmentos
    classificacao: Classificacao
    resultado_recurso: str | None
    frases: list[Frase] = field(default_factory=list)


def _texto(doc: DocumentoLido) -> str:
    return "\n\n".join(b.texto for p in doc.paginas for b in p.blocos)


def _trecho(segmentos: Segmentos, parte: str, contem: str | None = None):
    for t in segmentos.trechos:
        if t.parte == parte and (contem is None or contem.lower() in t.texto.lower()):
            return t
    return None


def analisar(doc: DocumentoLido, modelos: dict[str, ModeloEmUso] | None = None) -> Analise:
    from .evidencia.agentes.validacao import motivo_por_regra
    from .leitura.segmentador import segmentar

    modelos = modelos or {}
    lim_tipo = modelos["classificador_tipo_fase"].limiar("abstencao", 0.44) if "classificador_tipo_fase" in modelos else 0.44
    lim_res = modelos["resultado_pedido"].limiar("abstencao", 0.5) if "resultado_pedido" in modelos else 0.5
    seg = segmentar(doc)
    texto = _texto(doc)
    tipo = tipo_documento.classificar(texto, limiar_abstencao=lim_tipo)
    campos = extrator_campos.extrair(texto, trecho_id=seg.trechos[0].id if seg.trechos else None)
    ementa = extrator_campos.ementa(texto)
    t_ementa = _trecho(seg, "outro", "EMENTA")
    pedidos = resultado_pedido.pedidos_da_ementa(ementa, limiar_abstencao=lim_res, trecho_id=t_ementa.id if t_ementa else None)
    conclusao = resultado_pedido.trecho_conclusao(texto) or resultado_pedido.trecho_acordam(texto)
    recurso = resultado_pedido.classificar_regra(conclusao) if conclusao else None
    cls = Classificacao(tarefa_id=doc.tarefa_id, tipo_documento=tipo["tipo"], confianca_tipo=tipo["confianca_tipo"],
                        fase=tipo["fase"], confianca_fase=tipo["confianca_fase"], campos=campos, pedidos=pedidos,
                        abstencao=tipo["abstencao"])

    candidatas: list[tuple[str, object]] = []
    if cls.tipo_documento and (t := seg.trechos[0] if seg.trechos else None):
        fase = f", da fase de {cls.fase}" if cls.fase else ""
        candidatas.append((f"Este documento é um acórdão de {tipo_documento.NOMES[cls.tipo_documento]}{fase}.", t))
    if recurso and (t := _trecho(seg, "dispositivo")):
        candidatas.append((f"Segundo o dispositivo, o recurso {TEXTO_RECURSO[recurso]}.", t))
    for p in pedidos:
        if p.resultado in TEXTO_PEDIDO and t_ementa:
            candidatas.append((f"Sobre {p.pedido.lower()}, o direito {TEXTO_PEDIDO[p.resultado]} nesta decisão.", t_ementa))
    frases = []
    for texto_frase, t in candidatas:
        # mesmas regras de saída da Validação (conselho, promessa, número fora do trecho); sem filtro lexical,
        # porque a frase é uma paráfrase curta de um trecho longo do próprio documento
        if motivo_por_regra(texto_frase, t.texto, limiar_lexical=0) is None:
            frases.append(Frase(ordem=len(frases), texto=texto_frase, trecho_id=t.id, trecho_texto=t.texto[:1500],
                                fonte=f"seu documento — {NOME_PARTE[t.parte]}"))
    return Analise(segmentos=seg, classificacao=cls, resultado_recurso=recurso, frases=frases)


def pergunta_sobre_pedidos(analise: Analise, maximo: int = 3) -> str | None:
    """Pergunta informativa (sem dado do caso) para o sistema multiagente explicar a lei dos pedidos do documento."""
    nomes = [p.pedido.lower() for p in analise.classificacao.pedidos[:maximo]]
    if not nomes:
        return None
    return "O que a legislação trabalhista diz sobre " + ", ".join(nomes) + "?"
