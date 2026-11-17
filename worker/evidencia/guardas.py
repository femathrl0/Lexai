"""Guardrails de entrada e de saída do fluxo integrado (determinísticos, sem LLM).

Entrada — classifica a pergunta em uma ação e sinaliza riscos:
  responder               pergunta informativa de Direito do Trabalho brasileiro
  orientar_sem_aconselhar relato de caso concreto pedindo o que fazer: regra geral + encaminhamento
  institucional           pergunta sobre a plataforma (sem fundamentação jurídica)
  consulta_individual     situação do próprio processo, valores ou registros pessoais (não acessíveis)
  fora_escopo             outro ramo do direito ou assunto não jurídico
  outra_jurisdicao        direito de outro país
  Sinais transversais: dados_pessoais (mascarados antes da busca e da LLM) e instrucao_suspeita.

Saída — confere a resposta contra as fontes entregues:
  citacao_inexistente     [Fonte N] fora das fontes entregues
  dispositivo_inconsistente   artigo/parágrafo citado não corresponde à fonte, ou número/percentual
                              afirmado não aparece no dispositivo citado
  afirmacao_sem_fonte     proporção alta de frases jurídicas sem citação
  promessa_resultado      garantia de ganho ou de valor
  dados_pessoais_saida    CPF, e-mail ou telefone na resposta (mascarados)
  resposta_alem_do_escopo resposta jurídica desenvolvida quando a entrada pedia recusa/redirecionamento
  sem_fontes              afirmação jurídica sem nenhuma fonte entregue
  consulta_individual_sem_ressalva  entrada de consulta individual cuja resposta não diz que o sistema
                              não tem acesso ao processo/registros da pessoa
  consulta_individual_pede_dados    entrada de consulta individual cuja resposta pede número do processo,
                              documentos ou dados pessoais
  artigo_sem_fonte        artigo citado na resposta que não está em nenhuma fonte entregue (informativo;
                              compara só o número do artigo, não a norma)
  aviso_legal_ausente     resposta sem o aviso de que não substitui orientação profissional (acrescentado)
Bloqueantes (reprovam a resposta): ver BLOQUEANTES; os demais alertas são informativos.
As regras são heurísticas e auditáveis; não substituem revisão humana nem certificam correção jurídica.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata

AVISO_LEGAL = ('Esta resposta é informativa e não substitui a orientação de um advogado, da Defensoria Pública '
               'ou do sindicato da categoria.')
BLOQUEANTES = {'citacao_inexistente', 'dispositivo_inconsistente', 'promessa_resultado', 'resposta_alem_do_escopo',
               'sem_fontes', 'consulta_individual_sem_ressalva', 'consulta_individual_pede_dados'}


def _sem_acento(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto.lower()) if unicodedata.category(c) != 'Mn')


def _rx(*padroes):
    return re.compile('|'.join(padroes), re.IGNORECASE)


# --- dados pessoais -------------------------------------------------------------------------------------------
CPF = re.compile(r'(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)')
CNPJ = re.compile(r'(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)')
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
TELEFONE = re.compile(r'(?<!\d)(?:\(?\d{2}\)?\s?)?9?\d{4}-?\d{4}(?!\d)')
PROCESSO_CNJ = re.compile(r'(?<!\d)\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}(?!\d)')


def _digitos(valor):
    return re.sub(r'\D', '', str(valor or ''))


def mascarar(texto, processos_preservados=()):
    """Mascara dados pessoais. `processos_preservados`: números CNJ (só dígitos) das decisões entregues como fonte,
    que são públicas e devem continuar identificáveis na resposta."""
    achados = []
    preservados = {_digitos(p) for p in processos_preservados if p}
    for nome, padrao, marca in (('processo', PROCESSO_CNJ, '[PROCESSO]'), ('cnpj', CNPJ, '[CNPJ]'), ('cpf', CPF, '[CPF]'),
                                ('email', EMAIL, '[EMAIL]'), ('telefone', TELEFONE, '[TELEFONE]')):
        protegidos = []

        def trocar(m):
            if nome == 'processo' and _digitos(m.group(0)) in preservados:
                protegidos.append(m.group(0))
                return f'\x00{len(protegidos) - 1}\x00'
            if nome not in achados:
                achados.append(nome)
            return marca
        texto = padrao.sub(trocar, texto)
        # Números de processo preservados ficam fora das buscas seguintes (o telefone casaria com parte deles).
        if nome == 'processo':
            reservados = protegidos
    texto = re.sub(r'\x00(\d+)\x00', lambda m: reservados[int(m.group(1))], texto)
    return texto, achados


# --- regras de entrada (sobre o texto sem acentos) --------------------------------------------------------------
INJECAO = _rx(r'ignor\w* (as |todas as |suas )?(instruc|regras|orientac)', r'esquec\w* (as |suas )?(instruc|regras)',
              r'(prompt|instrucoes) do sistema', r'system prompt', r'voce agora (e|sera)', r'finja (que|ser)',
              r'modo (desenvolvedor|developer)', r'sem (restricoes|filtros|limites)', r'jailbreak')
PAISES = _rx(r'\b(eua|estados unidos|portugal|argentina|espanha|italia|franca|alemanha|inglaterra|reino unido|canada|'
             r'mexico|chile|uruguai|paraguai|japao|china|australia)\b', r'lei (americana|portuguesa|argentina|europeia)')
INSTITUCIONAL = _rx(r'\blexia\b', r'\bplataforma\b', r'\bchatbot\b', r'\b(site|aplicativo|app)\b',
                    r'\bfuncionalidades?\b', r'\bmeus dados\b.*\b(guard|armazen|usad|tratad)', r'\bcadastr', r'\bcomo (uso|usar|utilizar)\b')
INDIVIDUAL = _rx(r'\b(meu|minha|o meu|a minha) (processo|acao|reclamacao|sentenca|alvara|recurso|caso no tribunal)\b',
                 r'\b(situacao|fase|andamento|etapa) (atual )?(d[oe] (meu )?)?processo\b', r'\bprocesso trabalhista (esta )?em andamento\b',
                 r'\balvara\b', r'\bprestacao de contas\b', r'\bconsultar (o )?(numero|andamento|processo)',
                 r'\b(valor exato|saldo|extrato|deposito)\b.*\b(minha|meu)\b', r'\bna minha conta\b',
                 r'\bnumero (e|ou) documentos? (nao|nunca)\b', r'\bfundamento .*\bsentenca do meu\b',
                 r'\bo juiz (mandou|determinou|deu|negou|decidiu|marcou)\b', r'\bcontadoria\b', r'\bliquidacao\b.*\b(processo|juiz)\b')
CASO_CONCRETO = _rx(r'\b(trabalhei|fui (demitid|dispensad|contratad|afastad|promovid)|fiquei|recebi|nao recebi|recusei|levei|precisei|'
                    r'sofri|pedi|assinei|me (demitiram|dispensaram|mandaram|obrigaram)|meu (chefe|patrao|empregador|gerente)|'
                    r'minha (empresa|chefe|patroa|carteira)|estou (afastad|gravida|trabalhando|desempregad)|tenho que)\b',
                    r'\b(o que (devo|posso) fazer|devo (entrar|processar|pedir|aceitar|assinar)|vale a pena|tenho chance|vou ganhar)\b')
TRABALHISTA = _rx(r'\btrabalh', r'\bemprega', r'\bclt\b', r'\bsalari', r'\bferias\b', r'\bfgts\b', r'\bjornada\b', r'\bhoras? extras?\b',
                  r'\bdemiss', r'\bdispensa', r'\brescis', r'\baviso previo\b', r'\bcarteira (de trabalho|assinada)\b', r'\bsindicat',
                  r'\bjusta causa\b', r'\b13\s*[oº°]', r'\bdecimo terceiro\b', r'\brescisao\b', r'\bconvencao\b', r'\bnormas? coletivas?\b',r'\badicional\b', r'\bestabilidade\b', r'\bgestante\b',
                  r'\bdomestic', r'\binss\b', r'\bpis\b', r'\bseguro.desemprego\b', r'\bintervalo\b', r'\bprocesso trabalhista\b',
                  r'\bjustica do trabalho\b', r'\bpreposto\b', r'\bassedio\b', r'\bconvencao coletiva\b', r'\bestagi')
OUTRO_DIREITO = _rx(r'\bimposto de renda\b', r'\btributa', r'\bdividendos?\b', r'\bdivorci', r'\bpensao alimenticia\b', r'\bguarda (do|dos|da) filh',
                    r'\binventario\b', r'\bheranca\b', r'\biptu\b', r'\bipva\b', r'\bmulta de transito\b', r'\bcnh\b', r'\bconsumidor\b',
                    r'\baluguel\b', r'\bdespejo\b', r'\bcrime\b', r'\bpolicia\b', r'\bfalencia\b', r'\bacoes da bolsa\b', r'\breceita federal\b')


@dataclass
class ResultadoEntrada:
    acao: str
    pergunta_sanitizada: str
    sinais: list = field(default_factory=list)
    motivo: str = ''


def verificar_entrada(pergunta):
    texto = (pergunta or '').strip()
    if len(texto) < 8:
        return ResultadoEntrada('fora_escopo', texto, ['pergunta_vazia'], 'Pergunta vazia ou curta demais.')
    texto = texto[:2000]
    sanitizada, pii = mascarar(texto)
    sinais = ['dados_pessoais'] if pii else []
    base = _sem_acento(sanitizada)
    if INJECAO.search(base):
        sinais.append('instrucao_suspeita')
        # Remove as frases com instruções; o restante segue como pergunta, tratado como dado.
        frases = [f for f in re.split(r'(?<=[.!?])\s+', sanitizada) if not INJECAO.search(_sem_acento(f))]
        sanitizada = ' '.join(frases).strip()
        base = _sem_acento(sanitizada)
        if len(sanitizada) < 8:
            return ResultadoEntrada('fora_escopo', sanitizada, sinais, 'Somente instruções, sem pergunta jurídica.')
    if INSTITUCIONAL.search(base):
        return ResultadoEntrada('institucional', sanitizada, sinais, 'Pergunta sobre a plataforma.')
    if PAISES.search(base):
        return ResultadoEntrada('outra_jurisdicao', sanitizada, sinais, 'Pergunta sobre o direito de outro país.')
    trabalhista = bool(TRABALHISTA.search(base))
    if OUTRO_DIREITO.search(base) and not trabalhista:
        return ResultadoEntrada('fora_escopo', sanitizada, sinais, 'Outro ramo do direito.')
    if INDIVIDUAL.search(base):
        return ResultadoEntrada('consulta_individual', sanitizada, sinais, 'Situação de processo, valor ou registro individual.')
    if CASO_CONCRETO.search(base):
        return ResultadoEntrada('orientar_sem_aconselhar', sanitizada, sinais, 'Relato de caso concreto.')
    # Sem sinal claro de outro ramo, a pergunta segue: a suficiência da evidência é decidida pela recuperação.
    if not trabalhista:
        sinais.append('sem_termo_trabalhista')
    return ResultadoEntrada('responder', sanitizada, sinais, 'Pergunta informativa.')


# --- saída ------------------------------------------------------------------------------------------------------
CITACAO = re.compile(r'\[?\(?Fonte\s+(\d+)\)?\]?', re.IGNORECASE)
ARTIGO = re.compile(r'\bart(?:igo)?\.?\s*(\d+(?:-[A-Z])?)(?:\s*[ºo°])?', re.IGNORECASE)
PARAGRAFO = re.compile(r'§\s*(\d+)\s*[ºo°]?|par[áa]grafo\s+([úu]nico|\d+)', re.IGNORECASE)
CAPUT = re.compile(r'\bcaput\b', re.IGNORECASE)
# "Art. 73, § 2º", "art. 73, parágrafo único", "Art. 73, caput", "Art. 391-A".
MENCAO = re.compile(r'\bart(?:igo)?\.?\s*(\d+(?:-[A-Z])?)\s*[ºo°]?\s*(?:,\s*(?:§\s*(\d+)\s*[ºo°]?|par[áa]grafo\s+([úu]nico|\d+)|(caput)))?',
                    re.IGNORECASE)
NUMEROS = re.compile(r'(\d+(?:[.,]\d+)?)\s*(%|por cento|minutos?|horas?|dias?|meses|anos?|segundos?)', re.IGNORECASE)
PROMESSA = _rx(r'voce (vai|ira|certamente) (ganhar|receber|conseguir)', r'com certeza (voce )?(ganha|recebe|tem direito)',
               r'(ganho|vitoria|resultado) garantid', r'garanto que', r'nao tem como perder')
JURIDICO = _rx(r'\bart\.?\s*\d', r'\blei\b', r'\bdireito\b', r'\bdeve(m)?\b', r'\bprazo\b', r'\bobrigat', r'\b\d+\s*%', r'\bclt\b',
               r'\bpode(m)?\b', r'\bgarant')


ABREVIACOES = re.compile(r'\b(arts?|inc|incs|al|n|nº|p|pag|par|sr|sra|dr|dra|ex|obs|art)\.(?=\s)', re.IGNORECASE)
RESSALVA_INDIVIDUAL = _rx(r'nao (tenho|temos|consigo|e possivel) (acesso|acessar|consultar|saber|informar|dizer)',
                          r'sem (acesso|o numero|os documentos)', r'(consulte|consultar|verifique) .*(tribunal|advogad|processo|pje|site)',
                          r'nao (foram|foi) (informad|fornecid)')
# Pedido de dados ou documentos do caso: o sistema não acessa processos, então não deve solicitá-los.
PEDIDO_DADOS = re.compile(r'\b(forneca|fornecer|informe|informar|envie|enviar|mande|mandar|compartilhe|compartilhar|anexe|anexar|'
                          r'passe|passar|apresente|apresentar|digite|digitar)\b(\s+\S+){0,6}?\s+(o\s+)?'
                          r'(numero d[oa] (processo|acao)|documentos?|copia|trechos? da sentenca|sentenca|cpf|contracheques?)')


def _artigos_nas_fontes(fontes):
    """Artigos disponíveis nas fontes: o artigo_ref da legislação e os artigos citados no texto (ex.: em decisões)."""
    artigos = set()
    for fonte in fontes:
        ref = _normaliza_artigo(fonte.get('artigo_ref'))
        if ref:
            artigos.add(ref)
        artigos.update(a.upper() for a in ARTIGO.findall(fonte.get('texto', '') or ''))
    return artigos


def frases(texto):
    """Divide em frases sem quebrar em abreviações jurídicas ('Art. 73', 'nº', 'inc.')."""
    protegido = ABREVIACOES.sub(lambda m: m.group(1) + '․', texto)
    return [f.replace('․', '.') for f in re.split(r'(?<=[.!?:])\s+|\n+', protegido) if len(f.strip()) > 20]


def _normaliza_artigo(valor):
    m = re.search(r'(\d+(?:-[A-Z])?)', str(valor or ''), re.IGNORECASE)
    return m.group(1).upper() if m else None


def dispositivos(texto):
    """Divide o texto de um artigo em caput, parágrafos (§ N, único) e devolve {rótulo: trecho}."""
    partes, atual, rotulo = {}, [], 'caput'
    for linha in re.split(r'(?=§\s*\d+\s*[ºo°]?)|(?=Par[áa]grafo [úu]nico)', texto):
        m = re.match(r'§\s*(\d+)|Par[áa]grafo [úu]nico', linha.strip())
        if m:
            partes[rotulo] = ' '.join(atual)
            rotulo, atual = (f'§{m.group(1)}' if m.group(1) else 'unico'), []
        atual.append(linha)
    partes[rotulo] = ' '.join(atual)
    return partes


@dataclass
class ResultadoSaida:
    aprovada: bool
    alertas: list
    resposta_final: str


def verificar_saida(resposta, fontes, entrada=None):
    """fontes: lista na ordem das [Fonte N], cada uma com 'texto' e, na legislação, 'artigo_ref'."""
    alertas, texto = [], resposta or ''
    processos_fontes = [f.get('processo') for f in fontes] + PROCESSO_CNJ.findall(' '.join(f.get('texto', '') or '' for f in fontes))
    final, pii = mascarar(texto, processos_fontes)
    if pii:
        alertas.append(dict(codigo='dados_pessoais_saida', detalhe=', '.join(pii)))
    lista_frases = frases(texto)
    for numero in {int(n) for n in CITACAO.findall(texto)}:
        if not 1 <= numero <= len(fontes):
            alertas.append(dict(codigo='citacao_inexistente', detalhe=f'Fonte {numero}'))
    for frase in lista_frases:
        citadas =[int(n) for n in CITACAO.findall(frase) if 1 <= int(n) <= len(fontes)]
        artigos = ARTIGO.findall(frase)
        if not citadas or not artigos:
            continue
        mencoes = [(m.group(1).upper(), m.group(2) or m.group(3) or m.group(4)) for m in MENCAO.finditer(frase)]
        for n in citadas:
            fonte = fontes[n - 1]
            ref = _normaliza_artigo(fonte.get('artigo_ref'))
            if ref is None:
                continue  # jurisprudência ou fonte sem artigo: não se aplica
            # Somente os dispositivos mencionados junto do próprio artigo da fonte ("Art. 73, § 2º").
            alvo = set()
            for artigo, dispositivo in mencoes:
                if artigo != ref or not dispositivo:
                    continue
                d = _sem_acento(dispositivo)
                alvo.add('caput' if d == 'caput' else 'unico' if d.startswith('unico') else f'§{d}')
            partes = dispositivos(fonte.get('texto', '')) if alvo else {}
            for rotulo in sorted(alvo):
                if rotulo not in partes:
                    alertas.append(dict(codigo='dispositivo_inconsistente', detalhe=f'{rotulo} não existe no art. {ref} [Fonte {n}]',
                                        frase=frase.strip()[:200]))
                    continue
                trecho = _sem_acento(partes[rotulo])
                for valor, unidade in NUMEROS.findall(frase):
                    if valor.replace(',', '.') not in trecho.replace(',', '.'):
                        alertas.append(dict(codigo='dispositivo_inconsistente',
                                            detalhe=f'"{valor} {unidade}" não aparece no {rotulo} do art. {ref} [Fonte {n}]',
                                            frase=frase.strip()[:200]))
    # Artigo citado na resposta que não está em nenhuma fonte entregue (só compara o número do artigo, não a norma).
    if fontes:
        disponiveis = _artigos_nas_fontes(fontes)
        for artigo in sorted({m.group(1).upper() for m in MENCAO.finditer(texto)} - disponiveis):
            frase = next((f for f in lista_frases if re.search(rf'\bart(?:igo)?\.?\s*{re.escape(artigo)}\b', f, re.IGNORECASE)), '')
            alertas.append(dict(codigo='artigo_sem_fonte', detalhe=f'art. {artigo} não está em nenhuma fonte entregue',
                                frase=frase.strip()[:200]))
    juridicas = [f for f in lista_frases if JURIDICO.search(_sem_acento(f))]
    sem_citacao = [f for f in juridicas if not CITACAO.search(f)]
    if juridicas and not fontes:
        alertas.append(dict(codigo='sem_fontes', detalhe='Afirmações jurídicas sem nenhuma fonte entregue.'))
    elif len(juridicas) >= 3 and len(sem_citacao) / len(juridicas) > 0.6:
        alertas.append(dict(codigo='afirmacao_sem_fonte', detalhe=f'{len(sem_citacao)} de {len(juridicas)} frases jurídicas sem citação'))
    if PROMESSA.search(_sem_acento(texto)):
        alertas.append(dict(codigo='promessa_resultado', detalhe='Promessa de resultado ou de valor.'))
    if entrada is not None and entrada.acao in ('fora_escopo', 'outra_jurisdicao', 'institucional') and len(juridicas) >= 3:
        alertas.append(dict(codigo='resposta_alem_do_escopo', detalhe=f'Entrada classificada como {entrada.acao}.'))
    if entrada is not None and entrada.acao == 'consulta_individual' and not RESSALVA_INDIVIDUAL.search(_sem_acento(texto)):
        alertas.append(dict(codigo='consulta_individual_sem_ressalva',
                            detalhe='A resposta não informa que o sistema não tem acesso ao processo ou aos registros da pessoa.'))
    if entrada is not None and entrada.acao == 'consulta_individual':
        sem_acento = _sem_acento(texto)
        for m in PEDIDO_DADOS.finditer(sem_acento):
            if not re.search(r'\bnao\s+(\S+\s+)?$', sem_acento[max(0, m.start() - 15):m.start()]):  # "não envie seu CPF" é orientação correta
                alertas.append(dict(codigo='consulta_individual_pede_dados',
                                    detalhe='A resposta pede número do processo, documentos ou dados pessoais.',
                                    frase=texto[m.start():m.end() + 40].strip()))
                break
    if 'nao substitui' not in _sem_acento(texto):
        alertas.append(dict(codigo='aviso_legal_ausente', detalhe='Aviso acrescentado.'))
        final = final.rstrip() + '\n\n' + AVISO_LEGAL
    unicos, vistos = [], set()
    for a in alertas:
        chave = (a['codigo'], a['detalhe'])
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(a)
    aprovada = not any(a['codigo'] in BLOQUEANTES for a in unicos)
    return ResultadoSaida(aprovada, unicos, final)
