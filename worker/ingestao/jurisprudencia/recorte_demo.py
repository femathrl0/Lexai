"""Recorte de jurisprudência anonimizado para o buscador local do sistema multiagente (Eng. de dados).

    uv run --group worker python -m worker.ingestao.jurisprudencia.recorte_demo

Monta `corpus/jurisprudencia/recorte_demo.jsonl` (formato lido por `BuscadorLocal`: id, tipo_fonte, fonte, texto,
versao) a partir de duas fontes públicas, com versão fixa:

1. **Súmulas do TST** (texto oficial, sem dado pessoal): Livro de Súmulas do TST em PDF. Entram só as súmulas
   vigentes (as marcadas "cancelada" saem), sem o histórico de redações anteriores.
2. **Ementas do TRT-10** do RepoJus (`efaraneda/repojus`, CC BY 4.0, revisão fixa). Do inteiro teor entra **só a
   ementa**: cabeçalho com partes, advogados e relator fica de fora. Filtro por tema (os temas das perguntas da
   bateria), cota por tema e anonimização:
   - mascara CPF, CNPJ, número de processo, e-mail e telefone (`worker.evidencia.guardas.mascarar`);
   - **descarta** a ementa inteira quando há indício de nome de pessoa ou empresa (iniciais "L. V. H. S.",
     sequência de palavras com inicial maiúscula fora do vocabulário da legislação, sufixos LTDA/S.A./EIRELI) ou
     dado de saúde nominal. Descartar é mais seguro que tentar mascarar nome.
   O relatório (`corpus/jurisprudencia/relatorio_recorte.json`) traz contagens por motivo, nunca os valores removidos.

Os originais baixados ficam em `dados/raw/jurisprudencia/` (fora do Git).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
import urllib.request
from collections import Counter
from pathlib import Path

from worker.evidencia import guardas

RAIZ = Path(__file__).resolve().parents[3]
RAW = RAIZ / "dados" / "raw" / "jurisprudencia"
SAIDA = RAIZ / "corpus" / "jurisprudencia"
ARTIGOS = RAIZ / "dados" / "processed" / "legislacao" / "legislacao_artigos_completos.json"

REPOJUS_REV = "91aa953b3c976a8688135dea49cf6644f7732243"
REPOJUS = f"https://huggingface.co/datasets/efaraneda/repojus/resolve/{REPOJUS_REV}/data/v3"
PARTICOES = ["p_tribunal=TRT10/p_ano=2024/part-00000.parquet"]
LIVRO_SUMULAS = "https://www.tst.jus.br/documents/10157/63003/Livro-Internet.pdf"

# Tema → padrões procurados na verbetação da ementa (primeiras linhas, sem acento). Cota por tema no recorte.
TEMAS = {
    "verbas_rescisorias": r"verbas rescisorias|multa do art(igo)?\.? 477|art(igo)?s?\.? 467 e 477|prazo .{0,20}rescis",
    "aviso_previo": r"aviso previo",
    "gestante": r"gestante|estabilidade provisoria .{0,40}gravid",
    "justa_causa": r"justa causa|rescisao indireta",
    "horas_extras": r"horas extras|intervalo intrajornada|jornada",
    "adicional_noturno": r"adicional noturno|trabalho noturno|hora noturna",
    "insalubridade": r"insalubridade|periculosidade",
    "descontos": r"descontos? salaria|devolucao de descontos",
    "fgts": r"\bfgts\b",
    "ferias": r"\bferias\b",
}
COTA_POR_TEMA = 25
MAX_CHARS = 3000

INICIAIS = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ]\.\s?[A-ZÁÉÍÓÚÂÊÔÃÕÇ]\.")
EMPRESA = re.compile(r"\b(LTDA|Ltda|EIRELI|S\.\s?A\.|S/A|EPP)\b")
PALAVRA_MAIUSCULA = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõçà]+|\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}\b")
# Empregadores, sindicatos e plataformas que aparecem pela sigla nas ementas do TRT-10 (achados na auditoria do
# recorte). Ementa que cita um deles sai: o manual manda anonimizar também o empregador.
ENTIDADES = re.compile(r"\b(CAESB|EBSERH|IFOOD|iFood|SINTTEL|ECT|PREVI|NOVACAP|CEB|TERRACAP|METR[ÔO]-DF|SLU|BRB|"
                       r"CORREIOS|Correios|UBER|Uber|99POP|RAPPI|Rappi|LOGGI|Loggi)\b")
SIGLAS = {"clt": "CLT", "tst": "TST", "adct": "ADCT", "fgts": "FGTS", "ctps": "CTPS", "oj": "OJ", "sbdi": "SBDI",
          "inss": "INSS", "cf": "CF", "cpc": "CPC", "sdi": "SDI", "trct": "TRCT", "cipa": "CIPA", "pis": "PIS",
          "rsr": "RSR", "dsr": "DSR", "ii": "II", "iii": "III", "iv": "IV", "cnpj": "CNPJ", "plr": "PLR"}
SAUDE_NOMINAL = re.compile(r"\bCID[-\s]?\d|\bCID\s?[A-Z]\d", re.IGNORECASE)
# Termos com inicial maiúscula comuns nas ementas e ausentes da legislação (não são nomes de pessoas).
VOCAB_EXTRA = set("""ementa caso exame questao discussao razoes decidir dispositivo tese julgamento provimento parcial
recurso ordinario reclamante reclamada reclamado recorrente recorrido sumarissimo tst trt sbdi sdi oj sumula sumulas
ctps fgts inss clt cpc cf adct stf stj tema jurisprudencia relevante cabimento majoracao sucumbenciais sucumbencia
honorarios danos morais acumulo funcao vinculo empregaticio indireta conhecido desprovido provido nao pje regiao
turma desembargador desembargadora juiz juiza convocado convocada relator relatora acordao embargos declaracao
agravo peticao instrumento mandado seguranca acao rescisoria brasilia df distrito federal tocantins
verbete mte rel trct configurado cct ocupacional rot col interjornada ficta obreiro obreira confronta plr irr red rsr
trd deferidas indevidos dejt noturna termica petita infirmada infirmado desconstituicao dsr emb laborados airr crfb
excelso imprestaveis epi substitutiva subjetiva labor variados exc relationem act probatoriamente banheiro banheiros
causal honoraria bienal quinquenal infectocontagiosas destempo matematica arr pccs fiducia ppp colendo qualitativo
oitava intertemporal incontroversas decima biologico exordial tardias modulada cerceamento ipsa terceirizados
postulados resp estimativos intra ojsbdi inteligencia sobrejornada limitador fatico regit indeferido repercussoes
informal extrafolha contracheques faturadas intempestivo desconstituidos dialeticidade egregio egregia""".split())


def _sem_acento(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _baixar(url: str, destino: Path) -> Path:
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        print(f"baixando {url}")
        with urllib.request.urlopen(url, timeout=600) as r, open(destino, "wb") as f:
            while bloco := r.read(1 << 20):
                f.write(bloco)
    return destino


def _sha256(arq: Path) -> str:
    h = hashlib.sha256()
    with open(arq, "rb") as f:
        while bloco := f.read(1 << 20):
            h.update(bloco)
    return h.hexdigest()


def _juntar_linhas(linhas: list[str]) -> str:
    """Junta linhas do PDF desfazendo a hifenização de fim de linha ("estabili-\\ndade" → "estabilidade")."""
    texto = ""
    for linha in (x.strip() for x in linhas):
        if not linha:
            continue
        if re.search(r"[A-Za-zÀ-ÿ]-$", texto) and re.match(r"[A-Za-zÀ-ÿ]", linha):
            texto = texto[:-1] + linha
        else:
            texto = f"{texto} {linha}" if texto else linha
    return re.sub(r"\s+", " ", texto).strip()


# --- Súmulas do TST -------------------------------------------------------------------------------------------
def sumulas_tst(pdf: Path) -> list[dict]:
    from pypdf import PdfReader

    texto = "\n".join(p.extract_text() or "" for p in PdfReader(pdf).pages)
    # Só a parte das súmulas: do "SUM-1 " até o fim da última súmula, antes das Orientações Jurisprudenciais.
    inicio = texto.find("\nSUM-1 ")
    secao_oj = re.search(r"\n\s*Orientação Jurisprudencial\s*\n(?:\s*\n)*\s*do\s*\n", texto[inicio:])
    fim = inicio + secao_oj.start() if secao_oj else len(texto)
    linhas = [x for x in texto[inicio:fim].splitlines()
              if not re.fullmatch(r"\s*(Súmulas|SÚMULAS|A-\d+)\s*", x)]
    blocos: list[list[str]] = []
    for linha in linhas:
        if re.match(r"SUM-\d+ ", linha):
            blocos.append([linha])
        elif blocos:
            blocos[-1].append(linha)
    versao = f"tst-livro-sumulas:{_sha256(pdf)[:12]}"
    saida = []
    for bloco in blocos:
        numero = re.match(r"SUM-(\d+)", bloco[0]).group(1)
        cabecalho, corpo, no_corpo = [], [], False
        for linha in bloco:
            if linha.strip().startswith("Histórico:"):
                break
            if no_corpo:
                corpo.append(linha)
            else:
                cabecalho.append(linha)
                if "Res" in " ".join(cabecalho) and re.search(r"\d{4}\s*$", linha.strip()):
                    no_corpo = True
        cab = _juntar_linhas(cabecalho)
        if "cancelad" in cab.lower() or not corpo:
            continue
        titulo = re.split(r"\s+\(|\s+[-–]\s+Res\.", cab, maxsplit=1)[0]
        titulo = re.sub(r"^SUM-\d+\s+", "", titulo).rstrip(" .-–").lower()
        titulo = re.sub(r"[a-zà-ÿ]+", lambda m: SIGLAS.get(m.group(0), m.group(0)), titulo)
        titulo = re.sub(r"(^|\.\s+)([a-zà-ÿ])", lambda m: m.group(1) + m.group(2).upper(), titulo)
        saida.append(dict(id=f"tst-sum-{numero}", tipo_fonte="sumula", fonte=f"Súmula {numero} do TST",
                          texto=f"{titulo}. {_juntar_linhas(corpo)}", versao=versao))
    return saida


# --- Ementas do TRT-10 ----------------------------------------------------------------------------------------
def _vocabulario_legislacao() -> set[str]:
    vocab = set(VOCAB_EXTRA)
    if ARTIGOS.exists():
        for a in json.loads(ARTIGOS.read_text(encoding="utf-8")):
            vocab.update(re.findall(r"[a-z]+", _sem_acento(a["texto_artigo_completo"])))
    return vocab


def extrair_ementa(inteiro_teor: str) -> str | None:
    m = re.search(r"(?m)^\s*EMENTA\s*:?\s*$", inteiro_teor) or re.search(r"\bEMENTA\s*:", inteiro_teor)
    if not m:
        return None
    resto = inteiro_teor[m.end():]
    corte = re.search(r"(?m)^\s*(?:[IV]+\s*[-–.]\s*)?(RELATÓRIO|RELATORIO|Vistos|ADMISSIBILIDADE|FUNDAMENTAÇÃO|"
                      r"VOTO|CONHECIMENTO)\b", resto)
    ementa = resto[: corte.start() if corte else MAX_CHARS * 2].strip()
    ementa = re.sub(r"^\s*[:.\-–]\s*", "", ementa)          # "EMENTA\n:" → começa no texto
    ementa = re.sub(r"\s*\n\s*([.,;:])", r"\1", ementa)        # "DEVOLUÇÃO\n." → "DEVOLUÇÃO."
    ementa = re.sub(r"\n{2,}", "\n", ementa).strip()
    return ementa if len(ementa) >= 200 else None


def motivo_descarte(ementa: str, vocab: set[str]) -> str | None:
    """Indício de dado pessoal que não dá para mascarar com segurança → a ementa sai do recorte."""
    if INICIAIS.search(ementa):
        return "iniciais_de_nome"
    if EMPRESA.search(ementa) or ENTIDADES.search(ementa):
        return "nome_de_empresa"
    if SAUDE_NOMINAL.search(ementa):
        return "dado_de_saude"
    # Palavra com inicial maiúscula (ou toda maiúscula) fora do vocabulário da legislação e das ementas: provável
    # nome próprio (pessoa, empresa, cidade). Ignora a primeira palavra de cada frase.
    for frase in re.split(r"(?<=[.;:!?])\s+|\n", ementa):
        frase = frase.strip()
        for m in PALAVRA_MAIUSCULA.finditer(frase):
            if m.start() == 0:
                continue
            palavra = _sem_acento(m.group(0))
            if len(palavra) > 2 and palavra not in vocab:
                return "provavel_nome_proprio"
    return None


def ementas_trt10(parquets: list[Path], vocab: set[str]) -> tuple[list[dict], Counter, Counter]:
    import pyarrow.parquet as pq

    candidatos: dict[str, list[tuple[str, dict]]] = {t: [] for t in TEMAS}
    descartes, mascaras = Counter(), Counter()
    vistos = set()
    for arq in parquets:
        versao = f"repojus:{REPOJUS_REV[:12]}:{_sha256(arq)[:12]}"
        f = pq.ParquetFile(arq)
        for lote in f.iter_batches(batch_size=500, columns=["doc_id", "tipo", "data_julgamento",
                                                                 "data_publicacao", "texto_integral"]):
            for r in lote.to_pylist():
                if "Recurso Ordinário" not in (r["tipo"] or ""):
                    continue
                ementa = extrair_ementa(r["texto_integral"] or "")
                if not ementa:
                    descartes["sem_ementa"] += 1
                    continue
                cabeca = _sem_acento(ementa[:400])
                tema = next((t for t, p in TEMAS.items() if re.search(p, cabeca)), None)
                if tema is None:
                    continue
                motivo = motivo_descarte(ementa, vocab)
                if motivo:
                    descartes[motivo] += 1
                    continue
                texto, achados = guardas.mascarar(ementa[:MAX_CHARS])
                mascaras.update(achados)
                chave = hashlib.sha256(_sem_acento(texto).encode()).hexdigest()
                if chave in vistos:
                    descartes["duplicada"] += 1
                    continue
                vistos.add(chave)
                curto = r["doc_id"].rsplit(":", 1)[-1][:12]
                candidatos[tema].append((chave, dict(
                    id=f"trt10-{curto}", tipo_fonte="ementa", tema=tema,
                    fonte=f"TRT-10, {r['tipo']}, " + (f"julgado em {r['data_julgamento']}" if r["data_julgamento"]
                                                       else f"publicado em {r['data_publicacao'] or 's/d'}")
                          + f" (ementa {curto})",
                    texto=texto, versao=versao)))
    saida = []
    for tema, lista in candidatos.items():
        # Escolha determinística e espalhada: ordena pelo hash do texto e pega a cota.
        saida += [d for _, d in sorted(lista, key=lambda x: x[0])[:COTA_POR_TEMA]]
    return saida, descartes, mascaras


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sem-ementas", action="store_true", help="só as súmulas do TST")
    a = ap.parse_args()

    pdf = _baixar(LIVRO_SUMULAS, RAW / "tst" / "Livro-Internet.pdf")
    sumulas = sumulas_tst(pdf)
    ementas, descartes, mascaras = [], Counter(), Counter()
    if not a.sem_ementas:
        parquets = [_baixar(f"{REPOJUS}/{p}", RAW / "repojus" / p.replace("/", "_")) for p in PARTICOES]
        ementas, descartes, mascaras = ementas_trt10(parquets, _vocabulario_legislacao())

    SAIDA.mkdir(parents=True, exist_ok=True)
    docs = sumulas + ementas
    with open(SAIDA / "recorte_demo.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    relatorio = dict(
        fontes=dict(sumulas_tst=dict(url=LIVRO_SUMULAS, sha256=_sha256(pdf)),
                    repojus=dict(dataset="efaraneda/repojus", revisao=REPOJUS_REV, particoes=PARTICOES,
                                 licenca="CC BY 4.0")),
        total=len(docs), sumulas=len(sumulas), ementas=len(ementas),
        ementas_por_tema=dict(Counter(d["tema"] for d in ementas)),
        descartes=dict(descartes), mascaras_aplicadas=dict(mascaras),
        regra="ementa com indício de nome de pessoa/empresa ou dado de saúde é descartada; CPF, CNPJ, processo, "
              "e-mail e telefone são mascarados; cabeçalho do inteiro teor nunca entra")
    (SAIDA / "relatorio_recorte.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
