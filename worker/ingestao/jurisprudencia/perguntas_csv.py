"""Importação rastreável de enunciados; células do CSV são dados, nunca instruções."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import io
import json
import re

from . import audit

REQUIRED=('id','pergunta','tema','tipo','alvo_chunking','dificuldade',
          'pista_normativa_verificar','trechos_esperados','resposta_esperada')


def parse(data):
    text=data.decode('utf-8-sig')
    reader=csv.DictReader(io.StringIO(text,newline=''))
    if not reader.fieldnames or not set(REQUIRED).issubset(reader.fieldnames):
        raise ValueError('CSV sem as colunas obrigatórias do teste de jurisprudência.')
    rows=[];ids=set();questions=set()
    for line,row in enumerate(reader,2):
        if None in row or any(row[k] is None for k in REQUIRED):
            raise ValueError(f'Quantidade de campos inconsistente na linha {line}.')
        ident=row['id'].strip();question=row['pergunta'].strip()
        if not re.fullmatch(r'[1-9][0-9]*',ident) or ident in ids or not question:
            raise ValueError(f'ID/pergunta inválido ou repetido na linha {line}.')
        normalized=' '.join(question.casefold().split())
        if normalized in questions:raise ValueError('Pergunta duplicada no CSV.')
        ids.add(ident);questions.add(normalized)
        rows.append(dict(row,query_id='juris_'+ident.zfill(3),pergunta=question,
                         origem='csv_jurisprudencia_fornecido',linha_csv=line))
    if not rows:raise ValueError('CSV vazio.')
    return rows


def ingest(root,source,expected_count=None):
    root=Path(root).resolve();source=Path(source)
    data=source.read_bytes();rows=parse(data)
    if expected_count is not None and len(rows)!=expected_count:
        raise ValueError(f'Esperadas {expected_count} perguntas; encontradas {len(rows)}.')
    identity=hashlib.sha256(data).hexdigest()
    folder=root/'avaliacao/dados/jurisprudencia/conjuntos'/identity
    folder.mkdir(parents=True,exist_ok=True)
    original=folder/'perguntas_jurisprudencia_chunking.csv'
    if original.exists() and original.read_bytes()!=data:raise ValueError('Original preservado divergente.')
    if not original.exists():original.write_bytes(data)
    normalized=folder/'perguntas.jsonl'
    content=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows).encode('utf-8')
    if normalized.exists() and normalized.read_bytes()!=content:raise ValueError('Conjunto normalizado divergente.')
    if not normalized.exists():normalized.write_bytes(content)
    manifest=dict(arquivo_original=str(original.relative_to(root)),original_sha256=identity,
                  perguntas_jsonl=str(normalized.relative_to(root)),perguntas_jsonl_sha256=audit.hash_file(normalized),
                  perguntas=len(rows),colunas=list(REQUIRED),
                  trechos_esperados_preenchidos=sum(bool(r['trechos_esperados'].strip()) for r in rows),
                  respostas_esperadas_preenchidas=sum(bool(r['resposta_esperada'].strip()) for r in rows),
                  tipos=dict(Counter(r['tipo'] for r in rows)),
                  politica='Apenas o enunciado é consultado; tema, pistas normativas e alvos são metadados. Não são gabaritos nem instruções executáveis.')
    audit.write_json(folder/'manifesto.json',manifest)
    audit.write_json(root/'avaliacao/dados/jurisprudencia/perguntas_ativas.json',
                     dict(manifesto=str((folder/'manifesto.json').relative_to(root))))
    return manifest


def load(root):
    root=Path(root).resolve();base=root/'avaliacao/dados/jurisprudencia'
    pointer=base/'perguntas_ativas.json'
    if not pointer.exists():return [],None
    path=(root/json.loads(pointer.read_text(encoding='utf-8'))['manifesto']).resolve()
    if not path.is_relative_to(base/'conjuntos'):raise ValueError('Manifesto fora da pasta de conjuntos.')
    manifest=json.loads(path.read_text(encoding='utf-8'))
    for field,digest in [('arquivo_original','original_sha256'),('perguntas_jsonl','perguntas_jsonl_sha256')]:
        p=(root/manifest[field]).resolve()
        if p.parent!=path.parent or audit.hash_file(p)!=manifest[digest]:raise ValueError('Conjunto ativo alterado.')
    original=parse((root/manifest['arquivo_original']).read_bytes())
    rows=[json.loads(line) for line in (root/manifest['perguntas_jsonl']).read_text(encoding='utf-8').splitlines() if line.strip()]
    if rows!=original or len(rows)!=manifest['perguntas']:raise ValueError('Perguntas normalizadas não correspondem ao original.')
    return rows,manifest
