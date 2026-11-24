from __future__ import annotations

import re

from contratos import FraseAprovada, RespostaVerificada, Versoes
from contratos.agentes import EstadoTarefa
from worker.evidencia import guardas
from worker.evidencia.verificador import Verificador

from .base import Agente, Saida

# Frases que dão ordens à pessoa sobre o caso (manual: guarda de saída). Encaminhamento genérico é permitido.
CONSELHO = guardas._rx(r"\bvoce (deve|precisa|tem que|deveria)\b", r"\brecorra\b", r"\bprocesse\b",
                       r"\bentre com (uma )?(acao|processo|reclamacao)\b", r"\bexija\b", r"\bnao assine\b",
                       r"\baceite o acordo\b", r"\bvale a pena (processar|entrar)\b")
JANELA = 1200  # caracteres por janela; acima disso a premissa passa do limite de 512 tokens do NLI
CAPUT_CONTEXTO = 300  # começo do caput levado para cada parágrafo/inciso, que sozinho perde o sujeito
# Limiar de p(sustenta) do NLI. 0,55 desde 24/11, calibrado nos pares-ouro v1 com a Validação completa
# (avaliacao/agentes/resultados/2026-11-24_calibracao_nli_E_janela_lexical_20.md): janelas por dispositivo, número
# conferido na janela de apoio e sobreposição >= 0,2 → precisão 0,912 e recall 0,912 (portão 0,90 atingido).
# Em 19/11 (janela de 1.200 caracteres, limiar 0,75): 0,875 e 0,62. Escolhido e medido nos mesmos 105 pares.
LIMIAR_SUSTENTA = 0.55


def _por_tamanho(texto: str) -> list[str]:
    if len(texto) <= JANELA:
        return [texto]
    passo = JANELA - 200
    return [texto[i:i + JANELA] for i in range(0, len(texto) - 200, passo)]


_ROTULO_ARTIGO = re.compile(r"(art\.?|artigo|s[uú]mula|oj)\s*[\w.º°-]*\.?", re.IGNORECASE)


def _janelas(texto: str) -> list[str]:
    """Premissas para o NLI: o artigo inteiro e, se ele tiver parágrafos ou incisos, o caput e cada dispositivo com
    o começo do caput.

    O mDeBERTa foi treinado com premissas curtas (MNLI/XNLI): contra o artigo inteiro ele não reconhece nem a cópia
    literal de um parágrafo (p=0,00 no § 3º do art. 23 da LC 150; 0,95 contra o parágrafo sozinho). A frase é
    sustentada se alguma janela a sustentar. O artigo inteiro continua entre as janelas: sem ele, frases que juntam
    caput e parágrafo perdem apoio.
    """
    partes = [p.strip() for p in re.split(r"\n+", texto) if p.strip()]
    if len(partes) > 1 and _ROTULO_ARTIGO.fullmatch(partes[0]):
        partes = [f"{partes[0]} {partes[1]}"] + partes[2:]  # "Art. 473" sozinho não é caput: junta com a linha seguinte
    janelas = _por_tamanho(texto)
    if len(partes) > 1:
        caput = partes[0]
        prefixo = caput[:CAPUT_CONTEXTO] + (" (…) " if len(caput) > CAPUT_CONTEXTO else " ")
        janelas += [caput] + [prefixo + p for p in partes[1:]]
    vistas, unicas = set(), []
    for j in janelas:
        for parte in _por_tamanho(j):
            if parte not in vistas:
                vistas.add(parte)
                unicas.append(parte)
    return unicas


def melhor_janela(verificador: Verificador, frase: str, texto: str) -> tuple[str, dict[str, float], str]:
    """(veredito, probabilidades, janela) da janela que mais sustenta a frase. O agente e a calibração usam a
    mesma função, para não divergirem."""
    janelas = _janelas(texto)
    if hasattr(verificador, "verificar_lote"):
        resultados = verificador.verificar_lote(frase, janelas)
    else:
        resultados = [verificador.verificar(frase, j) for j in janelas]
    i = max(range(len(janelas)), key=lambda k: resultados[k][1]["sustenta"])
    return resultados[i][0], resultados[i][1], janelas[i]


def motivo_na_janela(frase: str, janela: str) -> str | None:
    """Regra numérica contra a janela que o NLI usou como apoio. O número trocado costuma existir em outro
    dispositivo do mesmo artigo ("5 dias" do nascimento numa frase sobre casamento, que é 3)."""
    if ausentes := numeros_ausentes(frase, janela):
        return f"número ou prazo que não está no dispositivo que sustenta a frase: {', '.join(ausentes)}"
    return None


# --- sobreposição lexical: sinal independente do NLI ---------------------------------------------------------
# O NLI aprova frase que generaliza o trecho com palavras que ele não usa ("o tempo além da jornada não é hora
# extra", p=1,00, contra o § 2º do art. 4º, que só vale para quem fica por escolha própria).
LIMIAR_LEXICAL = 0.2  # calibrado com o limiar acima (0,3 dá precisão 0,905 e recall 0,84; 0 dá 0,915 e 0,79 em 0,9)


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", guardas._sem_acento(s)) if len(t) > 3}


def sobreposicao(frase: str, trecho: str) -> float:
    """Fração das palavras de conteúdo (mais de 3 letras) da frase que aparecem no trecho."""
    f = _tokens(frase)
    return len(f & _tokens(trecho)) / len(f) if f else 0.0


# --- regra de números (manual: "regras conferem resultado e prazos") -----------------------------------------
# O NLI erra troca de número (aprova "5 dias por casamento" contra um trecho que diz 3). Por isso todo número com
# unidade na frase precisa aparecer no trecho citado, em algarismo ou por extenso.
_UNIDADES = r"(%|por cento|minutos?|horas?|dias?|semanas?|meses|m[eê]s|anos?|segundos?|sal[aá]rios?(?:-m[ií]nimos?)?|vezes)"
_EXTENSO = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
            "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14, "catorze": 14,
            "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19, "vinte": 20, "trinta": 30,
            "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90, "cem": 100,
            "cento": 100, "duzentos": 200, "trezentos": 300}
_PALAVRA_NUM = "(?:" + "|".join(sorted(_EXTENSO, key=len, reverse=True)) + ")"
_EXTENSO_RX = re.compile(rf"\b{_PALAVRA_NUM}(?:\s+e\s+{_PALAVRA_NUM})*\b")
_NUM_FRASE = re.compile(rf"(\d+(?:[.,]\d+)?|{_EXTENSO_RX.pattern})\s*(?:\(\w+\)\s*)?{_UNIDADES}", re.IGNORECASE)


def _valor(token: str) -> float:
    token = token.strip()
    if token[0].isdigit():
        return float(token.replace(".", "").replace(",", ".") if token.count(".") and "," in token
                     else token.replace(",", "."))
    return float(sum(_EXTENSO[p] for p in re.split(r"\s+e\s+", token)))


def _numeros_do_trecho(texto: str) -> set[float]:
    t = guardas._sem_acento(texto)
    nums = {_valor(n) for n in re.findall(r"\d+(?:,\d+)?", t)}
    return nums | {_valor(m.group(0)) for m in _EXTENSO_RX.finditer(t)}


def numeros_ausentes(frase: str, trecho: str) -> list[str]:
    """Números com unidade da frase ("5 dias", "40%", "dez dias") que não aparecem no trecho."""
    presentes = _numeros_do_trecho(trecho)
    return [m.group(0) for m in _NUM_FRASE.finditer(guardas._sem_acento(frase)) if _valor(m.group(1)) not in presentes]


def motivo_por_regra(texto: str, trecho_texto: str | None, limiar_lexical: float | None = None) -> str | None:
    """Regras de saída aplicadas antes do NLI. Devolve o motivo da reprovação ou None."""
    base = guardas._sem_acento(texto)
    if trecho_texto is None:
        return "frase sem trecho de apoio"
    if CONSELHO.search(base):
        return "dá ordem à pessoa sobre o caso (aconselhamento)"
    if guardas.PROMESSA.search(base):
        return "promete resultado"
    if ausentes := numeros_ausentes(texto, trecho_texto):
        return f"número ou prazo que não está no trecho: {', '.join(ausentes)}"
    limiar_lexical = LIMIAR_LEXICAL if limiar_lexical is None else limiar_lexical
    if limiar_lexical and (lex := sobreposicao(texto, trecho_texto)) < limiar_lexical:
        return f"a frase usa pouco do texto do trecho (sobreposição {lex:.2f} < {limiar_lexical:.2f})"
    return None


class AgenteValidacao(Agente):
    nome = "validacao"
    responsabilidade = ("Validation Agent: último portão. Confere cada frase contra o trecho citado (NLI: sustenta, "
                        "contradiz ou não trata) e contra as regras de saída (sem fonte, conselho, promessa, dado "
                        "pessoal); devolve frases reprovadas para reescrita (1×), pede nova busca se faltar fonte (1×) "
                        "e, no fim, remove o que segue reprovado e emite avisos de incerteza.")

    def __init__(self, verificador: Verificador | None, limiar_sustenta: float = LIMIAR_SUSTENTA,
                 versoes_extra: dict | None = None, limiar_lexical: float = LIMIAR_LEXICAL):
        self.verificador, self.limiar, self.limiar_lexical = verificador, limiar_sustenta, limiar_lexical
        self.versoes_extra = versoes_extra or {}

    def _julgar(self, texto: str, trecho) -> tuple[bool, str, dict]:
        if motivo := motivo_por_regra(texto, trecho.texto if trecho is not None else None, self.limiar_lexical):
            return False, motivo, {}
        if self.verificador is None:
            return True, "aprovada só pelas regras (NLI desligado)", {}
        melhor, probs_melhor, janela = melhor_janela(self.verificador, texto, trecho.texto)
        if probs_melhor["sustenta"] >= self.limiar and (motivo := motivo_na_janela(texto, janela)):
            return False, motivo, probs_melhor
        if probs_melhor["sustenta"] >= self.limiar:
            return True, f"sustentada pelo trecho (p={probs_melhor['sustenta']:.2f})", probs_melhor
        motivo = "o trecho contradiz a frase" if melhor == "contradiz" else "o trecho citado não trata do que a frase afirma"
        return False, f"{motivo} (p_sustenta={probs_melhor['sustenta']:.2f})", probs_melhor

    def executar(self, estado: EstadoTarefa) -> Saida:
        por_id = {t.id: t for t in estado.evidencias.trechos}
        aprovadas, reprovadas, julgamento = [], {}, []
        for f in estado.explicacao.frases:
            trecho = por_id.get(f.trecho_id) if f.trecho_id else None
            ok, motivo, probs = self._julgar(f.texto, trecho)
            julgamento.append(dict(ordem=f.ordem, aprovada=ok, motivo=motivo, nli=probs, trecho=f.trecho_id))
            if ok:
                texto, _ = guardas.mascarar(f.texto)
                aprovadas.append(FraseAprovada(ordem=f.ordem, texto=texto, trecho_id=trecho.id, fonte=trecho.fonte))
            else:
                reprovadas[f.ordem] = motivo
        dados = dict(julgamento=julgamento, limiar_sustenta=self.limiar,
                     verificador=getattr(self.verificador, "modelo", None))

        if reprovadas and estado.reescritas < 1:
            estado.reescritas += 1
            estado.frases_para_refazer = reprovadas
            return Saida(f"{len(aprovadas)} aprovadas, {len(reprovadas)} reprovadas → devolve à Análise para reescrever "
                         f"as frases {sorted(reprovadas)}", dados, tipo="devolucao", devolver_para="analise")
        sem_fonte = estado.evidencias.sem_fonte_segura or all("sem trecho" in m for m in reprovadas.values())
        if not aprovadas and sem_fonte and estado.novas_buscas < 1:
            estado.novas_buscas += 1
            estado.frases_para_refazer = {}
            return Saida("nenhuma frase com fonte → pede à Pesquisa uma nova busca com consulta reformulada", dados,
                         tipo="devolucao", devolver_para="pesquisa")

        avisos = []
        if reprovadas:
            avisos.append(f"{len(reprovadas)} frase(s) foram removidas porque não puderam ser confirmadas nas fontes.")
        if not aprovadas:
            avisos.append("Não encontrei fonte jurídica segura para responder. Explico só o que está nas fontes, e aqui "
                          "elas não bastaram.")
        if estado.triagem.acao == "orientar_sem_aconselhar":
            avisos.append("Sua pergunta descreve um caso concreto: procure um advogado, a Defensoria Pública ou o "
                          "sindicato da categoria para avaliar a sua situação.")
        avisos.append(guardas.AVISO_LEGAL)
        estado.resposta = RespostaVerificada(
            tarefa_id=estado.tarefa_id, frases=aprovadas, avisos=avisos,
            versoes=Versoes(modelos={k: v for k, v in dict(llm=estado.explicacao.modelo_llm,
                                                            nli=dados["verificador"], **self.versoes_extra).items() if v},
                            prompt=estado.explicacao.prompt_id, indices={"corpus_juridico": estado.evidencias.trechos[0].versao}
                            if estado.evidencias.trechos else {}))
        return Saida(f"liberou {len(aprovadas)} frases" + (f", removeu {len(reprovadas)}" if reprovadas else ""), dados)
