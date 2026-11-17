"""Experimentos locais de chunking; offsets referem-se ao texto protegido, sem reescrita."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import bisect
import hashlib
import json
import re
import time

import numpy as np

from . import audit, light_nlp, automatic_review

STRATEGIES = {
    'fixo': dict(titulo='Janelas fixas', limite=256, sobreposicao=32),
    'paragrafos': dict(titulo='Parágrafos e frases', limite=256, sobreposicao=32),
    'estrutura': dict(titulo='Estrutura jurídica', limite=256, sobreposicao=32),
    'adaptativo': dict(titulo='Adaptativo ao conteúdo', limite=384, sobreposicao=48),
    'semantico': dict(titulo='Fronteiras semânticas', limite=256, sobreposicao=32),
    'parent_child': dict(titulo='Estrutura com parent–child', limite=256, sobreposicao=32),
}
HEADINGS = re.compile(r'(?im)^[ \t]*(?:[IVXLCDM\d]+[. \t–—-]+)?(?:relat[oó]rio|fundamenta[çc][aã]o|voto|dispositivo|conclus[aã]o|ac[oó]rd[aã]o|ementa)[ \t]*[:. \t–—-]*$')
BREAKS = re.compile(r'\n\s*\n|(?<=[.!?;])\s+(?=[A-ZÀ-Ý§])')
MARKER = re.compile(r'\[CPF_REMOVIDO\]')


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def offsets(text, tokenizer):
    return tokenizer(text, add_special_tokens=False, return_offsets_mapping=True,
                     truncation=False, verbose=False)['offset_mapping']


def token_count(text, tokenizer):
    return len(tokenizer.encode(text, add_special_tokens=False, truncation=False, verbose=False))


def boundaries(text):
    return sorted({m.end() for m in BREAKS.finditer(text)} | {len(text)})


def split_spans(text, tokenizer, limit=256, overlap=32, preferred=(), sections=()):
    """Cobertura integral, limite real de tokens e sobreposição sem cortar o marcador de CPF."""
    if limit < 16 or overlap < 0 or overlap >= limit // 2:
        raise ValueError('Limite/sobreposição inválidos.')
    if not text or not text.strip():
        return []
    positions = offsets(text, tokenizer)
    if not positions:
        return [(0, len(text))]
    starts = [p[0] for p in positions]
    ends = [p[1] for p in positions]
    masks = [(m.start(), m.end()) for m in MARKER.finditer(text)]
    def safe(point, direction):
        for a, b in masks:
            if a < point < b:
                return a if direction < 0 else b
        return point
    result = []
    start = 0
    while start < len(text):
        first = bisect.bisect_right(ends, start)
        last = min(len(positions), first + limit)
        hard_end = starts[last] if last < len(positions) else len(text)
        hard_end = safe(hard_end, -1)
        # Retokenizar a fatia evita diferenças de tokenização em suas bordas.
        while hard_end > start and token_count(text[start:hard_end], tokenizer) > limit:
            last -= 1
            hard_end = safe(starts[last], -1)
        if hard_end <= start:
            raise ValueError('Não foi possível produzir um chunk dentro do limite.')
        end = hard_end
        if hard_end < len(text) or any(start < x < hard_end for x in sections):
            section_candidates = [x for x in sections if start < x < hard_end or start < x == hard_end < len(text)]
            preferred_candidates = [x for x in preferred if start + (hard_end-start)*0.5 <= x <= hard_end]
            if section_candidates:
                end = section_candidates[0]
            elif preferred_candidates:
                end = preferred_candidates[-1]
        end = safe(end, -1)
        if end <= start:
            end = hard_end
        result.append((start, end))
        if end == len(text):
            break
        if end in sections or not overlap:
            following = end
        else:
            end_token = bisect.bisect_left(starts, end)
            following = safe(starts[max(first+1, end_token-overlap)], -1)
        start = following if start < following <= end else end
    return result


def semantic_boundaries(text, model):
    """Unidades completas codificadas pelo MiniLM; nenhum truncamento silencioso."""
    tokenizer = model.tokenizer
    unit_spans = split_spans(text, tokenizer, model.max_seq_length-2, 0,
                            preferred=boundaries(text))
    if len(unit_spans) < 2:
        return [], len(unit_spans)
    units = [text[a:b] for a, b in unit_spans]
    if any(len(tokenizer.encode(s, add_special_tokens=True, truncation=False)) > model.max_seq_length for s in units):
        raise ValueError('Unidade semântica excede a entrada do modelo.')
    vectors = model.encode(units, batch_size=32, normalize_embeddings=True,
                           show_progress_bar=False, convert_to_numpy=True)
    similarities = np.sum(vectors[:-1]*vectors[1:], axis=1)
    threshold = float(np.quantile(similarities, .25))
    return [unit_spans[i][1] for i, v in enumerate(similarities) if v < threshold], len(units)


def chunk_document(text, kind, tokenizer, strategy, model=None):
    config = STRATEGIES[strategy]
    limit, overlap = config['limite'], config['sobreposicao']
    sections = [m.start() for m in HEADINGS.finditer(text) if m.start() > 0]
    preferred = boundaries(text) if strategy != 'fixo' else []
    semantic_units = 0
    if strategy == 'semantico':
        if model is None:
            raise ValueError('Chunking semântico exige o modelo local carregado.')
        sections, semantic_units = semantic_boundaries(text, model)
    if strategy not in ('estrutura', 'adaptativo', 'semantico', 'parent_child'):
        sections = []
    if strategy == 'adaptativo' and kind == 'ementa':
        sections = []
    spans = split_spans(text, tokenizer, limit, overlap, preferred, sections)
    # O limite maior do adaptativo permite manter ementas de até 384 tokens inteiras.
    return spans, dict(secoes_detectadas=len(list(HEADINGS.finditer(text))),
                       unidades_semanticas=semantic_units)


def parent_span(text, child, tokenizer, limit=1024):
    positions = offsets(text, tokenizer)
    starts = [x[0] for x in positions]
    a, b = child
    lo = max(0, bisect.bisect_right(starts, a)-1)
    hi = bisect.bisect_left(starts, b)
    left = max(0, lo-max(0, (limit-(hi-lo))//2))
    right = min(len(positions), left+limit)
    while True:
        begin = 0 if left == 0 else starts[left]
        end = len(text) if right == len(positions) else starts[right]
        # Não partir o marcador de mascaramento nas bordas do contexto ampliado.
        for m in MARKER.finditer(text):
            if m.start() < begin < m.end(): begin = m.start()
            if m.start() < end < m.end(): end = m.end()
        if token_count(text[begin:end], tokenizer) <= limit:
            assert begin <= a < b <= end
            return begin, end
        if right > hi: right -= 1
        elif left < lo: left += 1
        else: raise ValueError('Contexto pai excede o limite.')


def validate_spans(text, spans, tokenizer, limit):
    covered = 0
    repeated = 0
    for a, b in spans:
        if not (0 <= a < b <= len(text)) or a > covered:
            raise ValueError('Offsets inválidos ou lacuna no texto.')
        if not text[a:b].strip() or token_count(text[a:b], tokenizer) > limit:
            raise ValueError('Chunk vazio ou acima do limite de tokens.')
        for m in MARKER.finditer(text):
            if m.start() < a < m.end() or m.start() < b < m.end():
                raise ValueError('Marcador de CPF partido.')
        repeated += max(0, min(covered, b)-a)
        covered = max(covered, b)
    if covered != len(text):
        raise ValueError('Cobertura incompleta.')
    return repeated


def select_sample(root, max_docs=120):
    """Amostra determinística por arquivo, tribunal, tipo e faixa, sem a partição teste."""
    import pandas as pd
    import pyarrow.parquet as pq
    root = Path(root).resolve()
    _, review = automatic_review.load(root)
    _, manifest = light_nlp.load(root)
    index_path = root / review['indice']
    if audit.hash_file(index_path) != review['indice_sha256']:
        raise ValueError('Índice automático alterado.')
    df = pq.read_table(index_path).to_pandas()
    pinned = root / 'dados/relatorios/jurisprudencia/base_reduzida/amostra_chunking_fixada.json'
    fixed = json.loads(pinned.read_text(encoding='utf-8'))['registro_ids'] if pinned.exists() else None
    if fixed is not None:
        # Amostra fixada na migração para a base reduzida: mesmos documentos e mesma ordem da amostra
        # estratificada original, com os registro_id novos. Mantém os experimentos reprodutíveis.
        if len(fixed) != max_docs:
            raise ValueError('Amostra fixada com tamanho diferente do solicitado.')
        df = df[df.registro_id.isin(fixed)].copy()
    else:
        df = df[df.candidato_consolidado & df.split_proposto.ne('teste')].copy()
    df['faixa'] = pd.cut(df.texto_caracteres, [0, 500, 2000, 10000, 50000, float('inf')], right=False).astype(str)
    keys = ['arquivo_id', 'tribunal', 'tipo_conteudo_declarado', 'faixa']
    if fixed is not None:
        df = df.set_index('registro_id').loc[fixed].reset_index()
    else:
        df = df.sort_values('registro_id')
        df['ordem_estrato'] = df.groupby(keys, observed=True).cumcount()
        df = df.sort_values(['ordem_estrato', 'registro_id']).head(max_docs)
    wanted = {r['registro_id']: r for r in df.to_dict('records')}
    files = [m for m in manifest['arquivos'] if m['arquivo_id'] in set(df.arquivo_id)]
    sample = []
    for f in files:
        p = root / f['arquivo']
        if audit.hash_file(p) != f['sha256']:
            raise ValueError('Shard protegido alterado.')
        ids = set(wanted)
        # Filtro por IDs mantém o texto fora de relatórios e da saída do notebook.
        table = pq.read_table(p, filters=[('registro_id', 'in', sorted(ids))])
        for row in table.to_pylist():
            meta = wanted.pop(row['registro_id'])
            field = row['texto_principal_campo']
            if field not in light_nlp.TEXT_FIELDS:
                raise ValueError('Campo principal desconhecido.')
            row.update({k: meta[k] for k in ('split_proposto', 'grupo_avaliacao', 'tipo_conteudo_declarado', 'faixa')})
            row['texto'] = row[field]
            row['parent_arquivo'] = f['arquivo']
            row['parent_sha256'] = f['sha256']
            sample.append(row)
    if wanted or len(sample) != len(df) or not sample:
        raise ValueError('Amostra incompleta.')
    if fixed is not None:
        # Ordem original da amostra (a ordenação por registro_id da base completa), preservada na migração.
        order = {rid: i for i, rid in enumerate(fixed)}
        return sorted(sample, key=lambda r: order[r['registro_id']]), review, manifest
    return sorted(sample, key=lambda r: r['registro_id']), review, manifest


def prepare(root, max_docs=120):
    from transformers import AutoTokenizer
    from sentence_transformers import SentenceTransformer
    import torch
    torch.set_num_threads(min(4, torch.get_num_threads()))
    tokenizer = AutoTokenizer.from_pretrained('BAAI/bge-m3', local_files_only=True, use_fast=True)
    model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
                                local_files_only=True, device='cpu')
    sample, review, manifest = select_sample(root, max_docs)
    config = dict(max_documentos=max_docs, amostra_ids=[r['registro_id'] for r in sample],
                  indice_sha256=review['indice_sha256'], base_csv_sha256=manifest['csv_sha256'],
                  codigo_sha256=audit.hash_file(__file__), estrategias=STRATEGIES,
                  tokenizador='BAAI/bge-m3', modelo_fronteiras='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
                  criterio_semantico='similaridade adjacente abaixo do percentil 25 por documento',
                  escopo='Amostra técnica de desenvolvimento; não é indexação integral nem avaliação jurídica de respostas.')
    # Registra a identidade dos artefatos locais usados sem depender da branch remota.
    for label, path in [('tokenizador', tokenizer.init_kwargs.get('_commit_hash')),
                        ('modelo_semantico', getattr(model[0].auto_model.config, '_commit_hash', None))]:
        config[label+'_commit'] = path
    identity = digest(json.dumps(config, sort_keys=True, ensure_ascii=False))
    data = Path(root)/'dados/chunks/jurisprudencia/experimentos'/identity
    report = Path(root)/'dados/relatorios/jurisprudencia/chunking'/identity
    data.mkdir(parents=True, exist_ok=True); report.mkdir(parents=True, exist_ok=True)
    audit.write_json(report/'configuracao.json', config)
    audit.write_csv(report/'amostra.csv', [{k:r[k] for k in ('registro_id','arquivo_id','tribunal','split_proposto','tipo_conteudo_declarado','faixa')} for r in sample])
    return dict(root=Path(root), data=data, report=report, tokenizer=tokenizer, model=model,
                sample=sample, config=config, results=[], identity=identity)


def experiment(state, strategy):
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    from .privacy import PY_PATTERN
    tokenizer = state['tokenizer']; config = STRATEGIES[strategy]
    rows, parents, details = [], {}, []
    begin = time.perf_counter()
    total_chars = repeated = total_tokens = semantic_units = sections = 0
    for doc in state['sample']:
        text = doc['texto']
        if PY_PATTERN.search(text):
            raise ValueError('Padrão residual de CPF na entrada protegida; conteúdo não exibido.')
        spans, signals = chunk_document(text, doc['tipo_conteudo_declarado'], tokenizer, strategy, state['model'])
        repeated += validate_spans(text, spans, tokenizer, config['limite'])
        total_chars += len(text); semantic_units += signals['unidades_semanticas']; sections += signals['secoes_detectadas']
        document_tokens = token_count(text, tokenizer)
        for index, (a, b) in enumerate(spans):
            content = text[a:b]; n = token_count(content, tokenizer); total_tokens += n
            parent_id = doc['registro_id']
            parent_tokens = document_tokens if strategy != 'parent_child' else None
            if strategy == 'parent_child':
                x, y = parent_span(text, (a,b), tokenizer)
                parent_id = digest('|'.join([doc['registro_id'], str(x), str(y)]))
                parent_tokens = token_count(text[x:y], tokenizer)
                parents[parent_id] = dict(parent_id=parent_id, registro_id=doc['registro_id'], inicio=x, fim=y,
                                          texto=text[x:y], tokens=parent_tokens)
            chunk_id = digest('|'.join([state['identity'],strategy,doc['registro_id'],str(a),str(b)]))
            rows.append(dict(chunk_id=chunk_id, estrategia=strategy, registro_id=doc['registro_id'],
                             arquivo_id=doc['arquivo_id'], tribunal=doc['tribunal'],
                             campo_texto=doc['texto_principal_campo'], tipo_conteudo=doc['tipo_conteudo_declarado'],
                             split_proposto=doc['split_proposto'], grupo_avaliacao=doc['grupo_avaliacao'],
                             parent_id=parent_id, parent_arquivo=doc['parent_arquivo'], parent_sha256=doc['parent_sha256'],
                             ordem=index, inicio=a, fim=b, tokens=n, caracteres=b-a, texto=content,
                             texto_sha256=digest(content), contexto_tokens=parent_tokens))
        details.append(dict(registro_id=doc['registro_id'],chunks=len(spans),caracteres=len(text),
                            secoes_detectadas=signals['secoes_detectadas']))
    frame = pd.DataFrame(rows)
    if frame.chunk_id.duplicated().any(): raise ValueError('ID de chunk repetido.')
    target = state['data']/(strategy+'.parquet')
    pq.write_table(pa.Table.from_pylist(rows), target, compression='zstd')
    # Validação independente da exportação: texto, offsets, IDs e contagens.
    exported = pq.read_table(target).to_pylist()
    original_docs = {d['registro_id']:d['texto'] for d in state['sample']}
    if len(exported)!=len(rows): raise ValueError('Contagem da exportação divergente.')
    for r in exported:
        if original_docs[r['registro_id']][r['inicio']:r['fim']] != r['texto'] or digest(r['texto']) != r['texto_sha256']:
            raise ValueError('Texto exportado divergente.')
    if parents:
        pq.write_table(pa.Table.from_pylist(list(parents.values())), state['data']/'pais_parent_child.parquet', compression='zstd')
    # Sobreposição exata entre chunks de splits diferentes é observada, não presumida ausente.
    split_copies = int(frame.groupby('texto_sha256').split_proposto.nunique().gt(1).sum())
    result = dict(estrategia=strategy, titulo=config['titulo'], documentos=len(details), chunks=len(rows),
                  tokens_mediana=float(frame.tokens.median()), tokens_p95=float(frame.tokens.quantile(.95)),
                  tokens_maximo=int(frame.tokens.max()), tokens_total=total_tokens,
                  chunks_menores_32_tokens=int(frame.tokens.lt(32).sum()), cobertura_caracteres_pct=100.0,
                  repeticao_caracteres_pct=100*repeated/total_chars, secoes_detectadas=sections,
                  unidades_semanticas=semantic_units, copias_chunks_entre_splits=split_copies,
                  pais=len(parents), tempo_segundos=time.perf_counter()-begin,
                  parquet=str(target.relative_to(state['root'])), parquet_sha256=audit.hash_file(target),
                  bytes_parquet=target.stat().st_size, verificacao_offsets='aprovada',
                  limite_tokens=config['limite'], sobreposicao_alvo_tokens=config['sobreposicao'])
    if parents:
        result['contexto_pai_tokens_mediana'] = float(frame.contexto_tokens.median())
        result['ampliacao_contexto_mediana'] = float((frame.contexto_tokens/frame.tokens).median())
        result['pais_sha256'] = audit.hash_file(state['data']/'pais_parent_child.parquet')
    state['results'].append(result)
    audit.write_json(state['report']/(strategy+'.json'), result)
    audit.write_csv(state['report']/(strategy+'_documentos.csv'), details)
    return frame.drop(columns=['texto']), result


def plot_strategy(state, frame, strategy):
    import matplotlib.pyplot as plt
    config = STRATEGIES[strategy]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.5))
    axes[0].hist(frame.tokens, bins=24, color='#287b8e', edgecolor='white')
    axes[0].axvline(config['limite'], color='#b23b43', linestyle='--', label='Limite configurado')
    axes[0].set(xlabel='Tokens BGE-M3 por chunk', ylabel='Quantidade', title='Distribuição dos tamanhos')
    axes[0].legend(fontsize=8)
    if strategy == 'parent_child':
        axes[1].scatter(frame.tokens, frame.contexto_tokens, s=8, alpha=.3)
        axes[1].set(xlabel='Tokens do trecho', ylabel='Tokens do contexto pai', title='Ampliação do contexto por trecho')
    else:
        counts = frame.groupby('registro_id').size()
        axes[1].hist(counts, bins=24, color='#c58a34', edgecolor='white')
        axes[1].set(xlabel='Chunks por documento', ylabel='Documentos', title='Fragmentação dos documentos')
    fig.suptitle(config['titulo']+' — amostra técnica, sem teste de respostas')
    fig.tight_layout(); fig.savefig(state['report']/(strategy+'.png'), dpi=140); plt.show()


def finish(state):
    import pandas as pd
    import matplotlib.pyplot as plt
    results = state['results']
    if {r['estrategia'] for r in results} != set(STRATEGIES): raise ValueError('Experimentos incompletos.')
    frame = pd.DataFrame(results)
    audit.write_csv(state['report']/'comparacao.csv', results,
                    fields=sorted({k for row in results for k in row}))
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, field, title in zip(axes, ['chunks','repeticao_caracteres_pct','tokens_p95'],
                               ['Quantidade de chunks','Caracteres repetidos (%)','Tamanho p95 (tokens)']):
        ax.barh(frame.titulo, frame[field], color='#287b8e'); ax.set_title(title)
    fig.tight_layout(); fig.savefig(state['report']/'comparacao.png', dpi=140); plt.show()
    summary = dict(executado_em_utc=datetime.now(timezone.utc).isoformat(), configuracao=state['config'],
                   documentos_amostra=len(state['sample']), resultados=results, status='experimentos_estruturais_concluidos',
                   recuperacao_com_perguntas_avaliada=False, embeddings_corpus_gerados=False,
                   embeddings_fronteiras_semanticas_gerados=True, indexacao_integral=False,
                   limite='Sem Recall@k, MRR, nDCG ou avaliação de respostas; ainda não há estratégia vencedora de recuperação.')
    audit.write_json(state['report']/'resumo.json', summary)
    audit.write_json(state['root']/'dados/relatorios/jurisprudencia/chunking/ativa.json',
                     dict(pasta_relatorios=str(state['report'].relative_to(state['root'])),
                          pasta_dados=str(state['data'].relative_to(state['root']))))
    return frame
