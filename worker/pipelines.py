"""Os três pipelines do worker, um por fila.

Cada etapa abaixo tem dono e issue própria; os módulos conversam pelos contratos em contratos/.
"""
import os

from redis import Redis

from contratos import Aviso, Concluido, Status, Versoes

from .publicacao import publicar

LIMIAR_QUALIDADE_LEITURA = 0.5


def _redis() -> Redis:
    return Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:16379/0"))


def processar_documento(tarefa_id: str, usuario_id: str, caminho: str, guardar: bool, redis: Redis | None = None,
                        orquestrador=None) -> None:
    """PDF → leitura → segmentos → tipo/fase, campos e resultado → frases sobre o documento (com o trecho literal) →
    explicação da lei dos pedidos pelo sistema multiagente → concluído. Cada evento é publicado assim que sai."""
    from .documento import analisar, pergunta_sobre_pedidos
    from .leitura.leitor import ler_pdf
    from .modelos.registro import em_uso, versoes

    r = redis or _redis()

    def pub(evento):
        publicar(r, tarefa_id, evento)

    try:
        pub(Status(etapa="lendo"))
        doc = ler_pdf(tarefa_id, caminho)
        if doc.qualidade_leitura < LIMIAR_QUALIDADE_LEITURA:
            pub(Aviso(categoria="nova_foto", texto="Não consegui ler bem o documento"
                      + (f" ({doc.motivo_baixa_qualidade})" if doc.motivo_baixa_qualidade else "")
                      + ". Envie de novo, com boa luz, sem cortes e com a página inteira."))
            pub(Concluido(versoes=Versoes()))
            return
        pub(Status(etapa="classificando"))
        modelos = em_uso()
        analise = analisar(doc, modelos)
        if analise.classificacao.abstencao:
            pub(Aviso(categoria="incerteza", texto="Não tenho certeza do tipo deste documento; confira no cabeçalho."))
        for frase in analise.frases:
            pub(frase)
        pergunta = pergunta_sobre_pedidos(analise)
        orq = orquestrador if orquestrador is not None else (_orquestrador() if pergunta else None)
        if pergunta and orq is not None:
            base, dos_modelos = len(analise.frases), versoes(modelos)

            def repassar(e):
                if e.tipo == "frase":  # a numeração continua depois das frases sobre o documento
                    e = e.model_copy(update={"ordem": e.ordem + base})
                elif e.tipo == "concluido":
                    e = e.model_copy(update={"versoes": e.versoes.model_copy(
                        update={"modelos": {**dos_modelos, **e.versoes.modelos}})})
                pub(e)

            orq.publicar = repassar
            orq.responder(pergunta, tarefa_id=tarefa_id)  # publica as frases verificadas e o próprio Concluido
        else:
            pub(Concluido(versoes=Versoes(modelos=versoes(modelos))))
    finally:
        if not guardar and os.path.exists(caminho):
            os.remove(caminho)  # sem opt-in, o original é descartado (RNF01)


_ORQUESTRADOR = None


def _orquestrador():
    """Montado uma vez por processo: só o worker carrega modelos (manual)."""
    global _ORQUESTRADOR
    if _ORQUESTRADOR is None:
        from .evidencia.agentes.montagem import montar

        _ORQUESTRADOR = montar(os.getenv("BUSCADOR", "local"))
    return _ORQUESTRADOR


def responder_pergunta(tarefa_id: str, usuario_id: str, pergunta: str, documento_id: str | None) -> None:
    """Sistema multiagente: Triagem → Pesquisa → Análise → Comunicação → Validação (worker/evidencia/agentes)."""
    r = _redis()
    orq = _orquestrador()
    orq.publicar = lambda evento: publicar(r, tarefa_id, evento)
    orq.responder(pergunta, tarefa_id=tarefa_id)


def ingerir_lote(tarefa_id: str, lote: str) -> None:
    """Divisão estrutural -> embeddings -> versão candidata -> regressão -> (Curadoria aprova) publicação."""
    raise NotImplementedError("ver issue de ingestão jurídica (Eng. de dados + Eng. de IA)")
