"""Auditoria em fluxo: não altera originais nem exporta textos/dados de partes."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone, date
from pathlib import Path
from urllib.parse import urlparse

FILES = ['jurisprudencia_trt13.jsonl', 'jurisprudencias_tst.json',
         'train-00001.parquet', 'train-00000.parquet', 'train-00002.parquet', 'train-00005.parquet',
         'part-00000.parquet', 'part-00000 (1).parquet', 'part-00000 (3).parquet',
         'part-00000 (2).parquet', 'part-00000 (4).parquet', 'part-00000 (5).parquet',
         'part-00001.parquet', 'part-00000 (6).parquet', 'part-00000 (7).parquet',
         'part-00002.parquet', 'part-00001 (1).parquet', 'part-00000 (8).parquet',
         'part-00001 (2).parquet', 'part-00000 (9).parquet']
PROTOCOL = 'jurisprudencia-auditoria-v2'
TEXT_FIELDS = ['texto_integral', 'inteiro_teor', 'registro.txtInteiroTeor', 'registro.inteiroTeorHtml',
               'registro.txtInteiroTeorNaoAnalisado', 'registro.ementa', 'ementa', 'texto_busca']
PROCESS_FIELDS = ['processo_normalizado', 'numero_processo', 'processo', 'registro.numFormatado', 'registro.numProcDocumento']
DOC_FIELDS = ['doc_id', 'unique_key', 'documento_id', 'pje_id', 'registro.id', 'dg_unique']
JUDGE_FIELDS = ['data_julgamento', 'registro.dtaJulgamento', 'data_assinatura']
PUBLICATION_FIELDS = ['data_publicacao', 'registro.dtaPublicacao']
SAFE_CATEGORIES = {'tribunal', 'base', 'classe', 'tipo', 'tipo_decisao', 'segmento', 'ramo_direito',
                   'registro.tipo.nome', 'registro.orgao.sigla', 'spider_name'}
CPF = re.compile(r'\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11}')
EMAIL = re.compile(r'[\w.+-]{1,100}@[\w.-]{1,150}\.[A-Za-z]{2,20}')
CNJ = re.compile(r'(?<!\d)\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}(?!\d)')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def hash_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n', encoding='utf-8')
    temporary.replace(path)


def write_csv(path, rows, fields=None):
    rows = list(rows)
    if not rows and not fields:
        return
    with Path(path).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def flatten(record, prefix=''):
    result = {}
    for key, value in record.items():
        path = prefix+'.'+str(key) if prefix else str(key)
        result[path] = value
        if isinstance(value, dict):
            result.update(flatten(value, path))
    return result


def empty(value):
    return value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, (list, dict)) and not value)


def first(flat, fields):
    return next(((name, flat[name]) for name in fields if name in flat and not empty(flat[name])), ('', None))


def court(value):
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    if text in ('STF', 'SUPREMO TRIBUNAL FEDERAL'):
        return 'STF'
    if text in ('TST', 'TRIBUNAL SUPERIOR DO TRABALHO'):
        return 'TST'
    match = re.fullmatch(r'TRT[\s\-_]*(\d{1,2})', text)
    if match and 1 <= int(match[1]) <= 24:
        return f'TRT-{int(match[1]):02d}'
    return None


def identify_court(flat, filename):
    declared = [(key, court(flat.get(key))) for key in
                ('tribunal', 'court', 'registro.orgao.sigla', 'registro.orgao.nome')]
    known = [(key, value) for key, value in declared if value]
    if known:
        return known[0][1], 'campo_estruturado:'+known[0][0], len({v for _, v in known}) > 1
    # Nome de arquivo é somente uma hipótese, nunca evidência do tribunal julgador.
    match = re.search(r'(trt[\s_-]*\d{1,2}|tst|stf)', filename, re.I)
    return (court(match[0]) or 'não identificado' if match else 'não identificado'), 'hipotese_nome_arquivo' if match else 'sem_evidencia', False


def parse_date(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value/1000 if abs(value) > 10_000_000_000 else value, timezone.utc).date()
        except (ValueError, OSError, OverflowError):
            return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).date()
    except ValueError:
        for fmt in ('%d/%m/%Y', '%Y%m%d'):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


def cpf_valid(value):
    value = re.sub(r'\D', '', value)
    if len(value) != 11 or len(set(value)) == 1:
        return False
    for size in (9, 10):
        result = (sum(int(value[i])*(size+1-i) for i in range(size))*10) % 11
        if (0 if result == 10 else result) != int(value[size]):
            return False
    return True


def cpf_candidates(text):
    # Filtra limites apenas nos candidatos, sem lookbehind em cada caractere.
    # isdecimal corresponde a \d Unicode (não a isdigit, que inclui sobrescritos).
    for match in CPF.finditer(text):
        if match.start() and text[match.start()-1].isdecimal():
            continue
        if match.end() < len(text) and text[match.end()].isdecimal():
            continue
        yield match


def normalize_spaces(text):
    return ' '.join(text.split())


def describe_type(value):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, int):
        return 'int'
    if isinstance(value, float):
        return 'float'
    return type(value).__name__


def inventory(paths):
    result = []
    for i, path in enumerate(map(Path, paths), 1):
        entry = {'arquivo_id': f'f{i:02d}', 'arquivo': path.name, 'caminho_original': str(path),
                 'formato': path.suffix.lower().lstrip('.'), 'existe': path.is_file()}
        if path.is_file():
            print('Inventário e hash:', path.name, flush=True)
            stat = path.stat()
            entry.update(bytes=stat.st_size, sha256=hash_file(path), mtime_ns=stat.st_mtime_ns)
        result.append(entry)
    return result


class Profile:
    def __init__(self, filename):
        self.filename = filename
        self.fields, self.root_keys = {}, set()
        self.courts, self.methods, self.quality = Counter(), Counter(), Counter()
        self.text_fields, self.years, self.categories, self.domains = Counter(), Counter(), {}, Counter()
        self.lengths = []
        self.rows = 0
        self.minimum, self.maximum = None, None

    def add(self, record, line):
        self.rows += 1
        self.root_keys.update(record)
        flat = flatten(record)
        for key, value in flat.items():
            stat = self.fields.setdefault(key, {'presentes': 0, 'nulos': 0, 'vazios_nao_nulos': 0,
                'tipos': Counter(), 'uniques': set(), 'limite_cardinalidade': False, 'max_chars': 0})
            stat['presentes'] += 1
            stat['tipos'][describe_type(value)] += 1
            stat['nulos'] += value is None
            stat['vazios_nao_nulos'] += value is not None and empty(value)
            if not empty(value):
                if len(stat['uniques']) < 2000:
                    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
                    stat['uniques'].add(hashlib.sha256(encoded).digest())
                else:
                    stat['limite_cardinalidade'] = True
            if isinstance(value, str):
                stat['max_chars'] = max(stat['max_chars'], len(value))
            if key in SAFE_CATEGORIES and isinstance(value, str) and len(value) <= 180:
                counts = self.categories.setdefault(key, Counter())
                if value in counts or len(counts) < 2000:
                    counts[value] += 1
            if key.lower() in ('url', 'source', 'fonte') and isinstance(value, str):
                parsed = urlparse(value)
                if parsed.scheme in ('http', 'https') and parsed.hostname:
                    self.domains[parsed.hostname.lower()] += 1
                elif value.strip():
                    self.quality['origem_sem_url_http_valida'] += 1
            if key.split('.')[-1].lower() in ('partes', 'advogados', 'cpf', 'cnpj', 'endereco', 'email', 'telefone') and not empty(value):
                self.quality['campo_partes_ou_contato_preenchido'] += 1
        tribunal, method, conflict = identify_court(flat, self.filename)
        self.courts[tribunal or 'não identificado'] += 1
        self.methods[method] += 1
        self.quality['conflito_tribunal_em_campos'] += conflict
        field, value = first(flat, TEXT_FIELDS)
        text = value if isinstance(value, str) else ''
        if value is not None and not isinstance(value, str):
            self.quality['texto_principal_tipo_inesperado'] += 1
        self.text_fields[field or 'ausente'] += 1
        size = len(text)
        self.lengths.append(size)
        self.quality['sem_texto_principal'] += not text.strip()
        self.quality['texto_curto_menor_80_chars'] += bool(text.strip()) and size < 80
        self.quality['texto_longo_maior_50000_chars'] += size > 50000
        self.quality['texto_com_html'] += '<' in text and bool(re.search(r'</?[A-Za-z][^>]{0,150}>', text))
        self.quality['texto_com_replacement_unicode'] += '\ufffd' in text
        self.quality['texto_com_controle_incomum'] += bool(re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', text))
        self.quality['texto_com_sinal_mojibake'] += any(t in text for t in ('Ã£', 'Ã§', 'Ã³', 'â€', 'Â§'))
        self.quality['texto_com_email_candidato'] += '@' in text and bool(EMAIL.search(text))
        self.quality['texto_com_cpf_checksum_valido'] += any(cpf_valid(m[0]) for m in cpf_candidates(text))
        j_field, j_raw = first(flat, JUDGE_FIELDS)
        p_field, p_raw = first(flat, PUBLICATION_FIELDS)
        jdate, pdate = parse_date(j_raw), parse_date(p_raw)
        for prefix, raw, parsed in [('julgamento_ou_assinatura', j_raw, jdate), ('publicacao', p_raw, pdate)]:
            self.quality[prefix+'_ausente'] += empty(raw)
            self.quality[prefix+'_nao_interpretavel'] += not empty(raw) and parsed is None
            self.quality[prefix+'_futura'] += parsed is not None and parsed > date.today()
        if jdate:
            self.years[jdate.year] += 1
            self.minimum = min(self.minimum, jdate) if self.minimum else jdate
            self.maximum = max(self.maximum, jdate) if self.maximum else jdate
        self.quality['publicacao_anterior_julgamento_ou_assinatura'] += bool(jdate and pdate and pdate < jdate)
        _, process = first(flat, PROCESS_FIELDS)
        proc = str(process).strip() if process is not None else ''
        self.quality['processo_ausente'] += not proc
        self.quality['processo_formato_cnj_detectado'] += bool(CNJ.search(proc) or re.fullmatch(r'\d{20}', proc))
        _, doc = first(flat, DOC_FIELDS)
        self.quality['identificador_documental_ausente'] += doc is None
        # Hash declarado é conferido contra candidatos sem alterar o texto recebido.
        for key, candidates in [('sha256_ementa', ['ementa']), ('texto_sha256', ['texto_integral', 'texto_busca'])]:
            expected = flat.get(key)
            if isinstance(expected, str) and re.fullmatch('[a-fA-F0-9]{64}', expected):
                matches = any(isinstance(flat.get(k), str) and digest(flat[k].encode()) == expected.lower() for k in candidates)
                self.quality['hash_texto_declarado_conferido'] += 1
                self.quality['hash_texto_nao_coincide_com_candidatos_brutos'] += not matches
        raw_hash = hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str, separators=(',', ':')).encode()).digest()
        normalized = normalize_spaces(text)
        text_hash = hashlib.sha256(normalized.encode()).digest() if normalized else None
        doc_hash = hashlib.sha256((tribunal+'|'+str(doc)).encode()).digest() if doc is not None else None
        process_hash = hashlib.sha256((tribunal+'|'+re.sub(r'\W', '', proc)).encode()).digest() if proc else None
        return (line, tribunal, raw_hash, text_hash, doc_hash, process_hash, size)

    def result(self):
        import numpy as np
        fields = []
        for name, stat in sorted(self.fields.items()):
            absent = self.rows-stat['presentes']
            missing = absent+stat['nulos']+stat['vazios_nao_nulos']
            fields.append({'arquivo': self.filename, 'feature': name, 'nivel': 'raiz' if name in self.root_keys else 'aninhada',
                'tipos_observados': dict(stat['tipos']), 'registros': self.rows, 'campo_ausente': absent,
                'valor_nulo': stat['nulos'], 'vazio_nao_nulo': stat['vazios_nao_nulos'],
                'preenchidos': self.rows-missing, 'percentual_ausente_nulo_vazio': missing/self.rows if self.rows else None,
                'cardinalidade_observada': len(stat['uniques']),
                'cardinalidade_modo': 'limite_inferior_amostra_inicial' if stat['limite_cardinalidade'] else 'exata',
                'max_caracteres': stat['max_chars']})
        lengths = np.array(self.lengths, dtype='int64')
        return {'arquivo': self.filename, 'registros_lidos': self.rows,
                'features_raiz': sorted(self.root_keys), 'quantidade_features_raiz': len(self.root_keys),
                'quantidade_features_incluindo_aninhadas': len(fields), 'features': fields,
                'tribunais': dict(self.courts), 'metodos_identificacao': dict(self.methods),
                'qualidade': dict(self.quality), 'campos_texto_selecionados': dict(self.text_fields),
                'datas_ano': dict(self.years), 'data_minima': self.minimum, 'data_maxima': self.maximum,
                'categorias': {k: dict(v.most_common(30)) for k, v in self.categories.items()},
                'dominios_origem': dict(self.domains),
                'tamanho_texto': {'n': len(lengths), 'min': int(lengths.min()) if len(lengths) else None,
                    'media': float(lengths.mean()) if len(lengths) else None, 'max': int(lengths.max()) if len(lengths) else None,
                    'p50': float(np.quantile(lengths, .5)) if len(lengths) else None,
                    'p95': float(np.quantile(lengths, .95)) if len(lengths) else None},
                'histograma_chars': dict(Counter('vazio' if v == 0 else '<80' if v < 80 else '80-499' if v < 500
                    else '500-1999' if v < 2000 else '2000-9999' if v < 10000 else '>=10000' for v in self.lengths))}


def records(path, issues):
    """Erros de JSONL são contados por linha; erro em Parquet/JSON interrompe só o arquivo."""
    import pyarrow.parquet as pq
    import ijson
    if path.suffix.lower() == '.parquet':
        parquet = pq.ParquetFile(path)
        issues['registros_declarados_metadata'] = parquet.metadata.num_rows
        issues['schema_parquet'] = str(parquet.schema_arrow.remove_metadata())
        issues['row_groups'] = parquet.metadata.num_row_groups
        offset = 0
        for batch in parquet.iter_batches(batch_size=128, use_threads=False):
            for item in batch.to_pylist():
                offset += 1
                yield offset, item
    elif path.suffix.lower() == '.jsonl':
        with path.open(encoding='utf-8-sig') as handle:
            for number, line in enumerate(handle, 1):
                issues['linhas_fisicas'] = number
                if not line.strip():
                    issues['linhas_vazias'] = issues.get('linhas_vazias', 0)+1
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    issues['linhas_json_invalidas'] = issues.get('linhas_json_invalidas', 0)+1
                    continue
                if not isinstance(record, dict):
                    issues['registros_nao_objeto'] = issues.get('registros_nao_objeto', 0)+1
                    continue
                yield number, record
    else:
        with path.open('rb') as handle:
            for number, record in enumerate(ijson.items(handle, 'item', use_float=True), 1):
                if not isinstance(record, dict):
                    issues['registros_nao_objeto'] = issues.get('registros_nao_objeto', 0)+1
                    continue
                yield number, record


def audit_file(entry, connection):
    path = Path(entry['caminho_original'])
    profile = Profile(path.name)
    issues = {}
    connection.execute('DELETE FROM records WHERE arquivo_id=?', (entry['arquivo_id'],))
    connection.commit()
    buffer = []
    status, error = 'concluido', None
    try:
        for line, record in records(path, issues):
            buffer.append((entry['arquivo_id'], *profile.add(record, line)))
            if len(buffer) == 512:
                connection.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?)', buffer)
                connection.commit()
                buffer.clear()
            if profile.rows % 10000 == 0:
                print(f'{path.name}: {profile.rows} registros auditados', flush=True)
    except Exception as exc:
        status = 'leitura_parcial' if profile.rows else 'erro_leitura'
        error = type(exc).__name__
        issues['diagnostico_erro'] = 'Não foi possível ler integralmente o arquivo; conferir integridade e obter novamente a origem. Não foi feita reparação silenciosa.'
    if buffer:
        connection.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?)', buffer)
    connection.commit()
    stat = path.stat()
    if stat.st_size != entry['bytes'] or stat.st_mtime_ns != entry['mtime_ns']:
        status = 'origem_alterada_durante_auditoria'
    result = profile.result()
    result.update(arquivo_id=entry['arquivo_id'], status_leitura=status, tipo_erro=error, leitura=issues)
    return result


def duplicates(connection):
    summaries, groups, per_file = [], [], []
    for column, name in [('record_hash', 'registro_identico_canonico'), ('text_hash', 'texto_igual_apos_normalizar_espacos'),
                         ('document_hash', 'chave_documental_candidata'), ('process_hash', 'mesmo_processo_nao_implica_duplicata')]:
        query = f'SELECT COUNT(*), SUM(n), SUM(n-1) FROM (SELECT COUNT(*) n FROM records WHERE {column} IS NOT NULL GROUP BY {column} HAVING COUNT(*)>1)'
        n, affected, excess = connection.execute(query).fetchone()
        summaries.append({'criterio': name, 'grupos_repetidos': n, 'registros_nos_grupos': affected or 0, 'repeticoes_excedentes': excess or 0})
        query = f'SELECT hex({column}), COUNT(*), COUNT(DISTINCT arquivo_id), GROUP_CONCAT(DISTINCT arquivo_id) FROM records WHERE {column} IS NOT NULL GROUP BY {column} HAVING COUNT(*)>1 ORDER BY COUNT(*) DESC LIMIT 100'
        groups.extend({'criterio': name, 'fingerprint': h, 'registros': n, 'arquivos': files, 'arquivos_ids': ids}
                      for h, n, files, ids in connection.execute(query))
        query = f'SELECT arquivo_id, SUM(n-1) FROM (SELECT arquivo_id, COUNT(*) n FROM records WHERE {column} IS NOT NULL GROUP BY arquivo_id,{column} HAVING COUNT(*)>1) GROUP BY arquivo_id'
        per_file.extend({'arquivo_id': file, 'criterio': name, 'repeticoes_excedentes_internas': n} for file, n in connection.execute(query))
    return summaries, groups, per_file


def run(root, paths):
    root = Path(root)
    entries = inventory(paths)
    key = digest(json.dumps([{'arquivo': e['arquivo'], 'sha256': e.get('sha256'), 'bytes': e.get('bytes')} for e in entries], sort_keys=True).encode())
    protocol = hash_file(__file__)
    folder = root/'dados/relatorios/jurisprudencia/auditoria'/key/protocol
    folder.mkdir(parents=True, exist_ok=True)
    private = root/'tmp/jurisprudencia_auditoria'/key/protocol
    private.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(private/'fingerprints.sqlite')
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('CREATE TABLE IF NOT EXISTS records (arquivo_id TEXT, linha INTEGER, tribunal TEXT, record_hash BLOB, text_hash BLOB, document_hash BLOB, process_hash BLOB, chars INTEGER)')
    profiles = []
    write_json(folder/'inventario.json', entries)
    for entry in entries:
        if not entry['existe']:
            profiles.append({'arquivo_id': entry['arquivo_id'], 'arquivo': entry['arquivo'], 'status_leitura': 'ausente', 'registros_lidos': 0, 'features': [], 'tribunais': {}, 'qualidade': {}})
            continue
        checkpoint = folder/'perfis'/f'{entry["arquivo_id"]}.json'
        if checkpoint.exists():
            result = json.loads(checkpoint.read_text(encoding='utf-8'))
            stored = connection.execute('SELECT COUNT(*) FROM records WHERE arquivo_id=?', (entry['arquivo_id'],)).fetchone()[0]
            if stored == result['registros_lidos']:
                profiles.append(result)
                print('Checkpoint preservado:', entry['arquivo'], result['status_leitura'], flush=True)
                continue
        print('Auditando:', entry['arquivo'], flush=True)
        result = audit_file(entry, connection)
        result['codigo_auditor_efetivo'] = protocol
        write_json(checkpoint, result)
        profiles.append(result)
        print('Concluído:', entry['arquivo'], result['status_leitura'], result['registros_lidos'], flush=True)
    duplicate_summary, duplicate_groups, duplicate_files = duplicates(connection)
    courts = [{'tribunal': t, 'registros_lidos': n} for t, n in connection.execute('SELECT tribunal,COUNT(*) FROM records GROUP BY tribunal ORDER BY tribunal')]
    unique_records = connection.execute('SELECT COUNT(DISTINCT record_hash) FROM records').fetchone()[0]
    connection.close()
    by_hash = Counter(e.get('sha256') for e in entries if e.get('sha256'))
    summary = {'protocolo': PROTOCOL, 'inventario_sha256': key, 'codigo_auditor_sha256': protocol,
        'gerado_em_utc': datetime.now(timezone.utc).isoformat(), 'data_referencia': str(date.today()),
        'arquivos_recebidos': len(entries), 'arquivos_presentes': sum(e['existe'] for e in entries),
        'bytes_recebidos': sum(e.get('bytes', 0) for e in entries),
        'arquivos_concluidos': sum(p['status_leitura']=='concluido' for p in profiles),
        'arquivos_com_falha_ou_leitura_parcial': sum(p['status_leitura']!='concluido' for p in profiles),
        'copias_arquivos_identicos_excedentes': sum(n-1 for n in by_hash.values()),
        'registros_lidos': sum(p['registros_lidos'] for p in profiles),
        'registros_canonicos_distintos': unique_records, 'tribunais_observados': courts,
        'licencas_e_repositorios_originais': 'Não atestados: faltam manifestos/URLs de distribuição/licenças das origens. Campos fonte/url são declarações dos dados.',
        'escopo': 'Auditoria estrutural integral dos registros legíveis; não comprova autenticidade, atualização, mérito jurídico ou representatividade.',
        'privacidade': 'Sem exportação de decisões, nomes de partes ou CPFs nos relatórios; detecção automatizada de PII é triagem e não anonimização.'}
    rows = []
    for p, entry in zip(profiles, entries):
        rows.append({'arquivo_id': entry['arquivo_id'], 'arquivo': entry['arquivo'], 'formato': entry['formato'],
            'bytes': entry.get('bytes'), 'sha256': entry.get('sha256'), 'status': p['status_leitura'],
            'registros_declarados_metadata': p.get('leitura', {}).get('registros_declarados_metadata'),
            'registros_lidos': p['registros_lidos'], 'features_raiz': p.get('quantidade_features_raiz', 0),
            'features_incluindo_aninhadas': p.get('quantidade_features_incluindo_aninhadas', 0),
            'tribunais': json.dumps(p['tribunais'], ensure_ascii=False), 'tipo_erro': p.get('tipo_erro')})
    write_csv(folder/'inventario_arquivos.csv', rows)
    feature_rows = [{**f, 'tipos_observados': json.dumps(f['tipos_observados'], ensure_ascii=False)} for p in profiles for f in p['features']]
    write_csv(folder/'dicionario_features.csv', feature_rows)
    quality_rows = [{'arquivo_id': p['arquivo_id'], 'arquivo': p['arquivo'], 'indicador': k, 'ocorrencias': v,
                     'registros_lidos': p['registros_lidos']} for p in profiles for k, v in p['qualidade'].items()]
    write_csv(folder/'qualidade_dados.csv', quality_rows)
    write_csv(folder/'tribunais.csv', courts, ['tribunal', 'registros_lidos'])
    write_csv(folder/'duplicatas_resumo.csv', duplicate_summary)
    write_csv(folder/'duplicatas_grupos_fingerprints.csv', duplicate_groups, ['criterio','fingerprint','registros','arquivos','arquivos_ids'])
    write_csv(folder/'duplicatas_por_arquivo.csv', duplicate_files, ['arquivo_id','criterio','repeticoes_excedentes_internas'])
    write_json(folder/'resumo_auditoria.json', summary)
    write_json(folder/'perfis_arquivos.json', profiles)
    write_json(root/'dados/relatorios/jurisprudencia/auditoria/auditoria_ativa.json', {'pasta': str(folder.relative_to(root)), 'inventario_sha256': key, 'codigo_auditor_sha256': protocol})
    return folder, summary, profiles
