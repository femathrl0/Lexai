"""Migra os artefatos dos experimentos do notebook 04 da base completa para a base reduzida.

Os 187 documentos usados nos experimentos e na avaliação estão na base reduzida com textos idênticos;
mudam somente os identificadores (registro_id), os caminhos das etapas e os hashes dos arquivos da base.

Etapas:
  1. Arquiva uma cópia integral dos artefatos originais em data/arquivo_base_completa/ (uma única vez).
  2. Monta o mapa de substituição: registro_id antigo -> novo; pastas de cada etapa (auditoria, EDA,
     estrutura, CPF, PLN, revisão, automação); hashes de shards, CSVs e resumos, pareados pelos resumos.
  3. Reescreve JSON/JSONL/CSV/MD/TXT e Parquet dos experimentos e da avaliação, recalculando em cadeia
     os hashes dos próprios artefatos até um ponto fixo. Registros de arquivos protegidos ({caminho: hash})
     passam a refletir o estado atual.
  4. Grava a amostra fixada do chunking (mesmos 120 documentos e ordem, IDs novos), atualiza os dois
     prefixos de ID no código e as fontes do notebook 04, e confere que não restou referência antiga.
Cópias de código executado (*.py) e caches SQLite não são alterados.
"""
from pathlib import Path
import json
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from worker.ingestao.jurisprudencia import audit  # noqa: E402

DIRS = ['dados/relatorios/jurisprudencia/' + d for d in ('chunking', 'chunking_avancado', 'chunking_suporte', 'piloto_bge',
        'orcamento_centrado', 'finalistas', 'teste_final', 'complementar', 'controles_dificeis')] + \
       ['dados/chunks/jurisprudencia/' + d for d in ('avancado', 'complementar', 'experimentos', 'finalistas',
        'orcamento_centrado', 'piloto_bge', 'suporte')] + ['avaliacao/dados/jurisprudencia']
ARQUIVO = ROOT / 'dados/arquivo_base_completa'
PONTEIROS = ROOT / 'dados/relatorios/jurisprudencia/base_completa_ponteiros'
NB04 = ROOT / 'notebooks/02_jurisprudencia/04_experimentos_chunking_jurisprudencia.ipynb'
TEXTO = {'.json', '.jsonl', '.csv', '.md', '.txt'}
HEX = re.compile(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])')
PREFIXOS = ('0002e549', '00a2e4bd')


def ler(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def arquivar():
    for d in DIRS:
        origem, destino = ROOT / d, ARQUIVO / d
        if origem.exists() and not destino.exists():
            shutil.copytree(origem, destino)
    for p in (NB04, ROOT / 'src/jurisprudencia/piloto_bge.py', ROOT / 'src/jurisprudencia/experimento_orcamento.py'):
        destino = ARQUIVO / p.relative_to(ROOT)
        if not destino.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, destino)
    print('Originais arquivados em', ARQUIVO, flush=True)


def pares_de_etapas():
    """(pasta antiga, pasta nova) e arquivos de resumo de cada etapa."""
    def antigo(rel):
        return ler(PONTEIROS / rel.replace('/', '__'))
    pares = []
    for rel, chaves in [('dados/relatorios/jurisprudencia/auditoria/auditoria_ativa.json', ['pasta']),
                        ('dados/relatorios/jurisprudencia/eda/eda_ativa.json', ['pasta']),
                        ('dados/processed/jurisprudencia/estrutura_ativa.json', ['pasta_dados', 'pasta_relatorios']),
                        ('dados/processed/jurisprudencia/protecao_cpf/ativa.json', ['pasta_dados', 'pasta_relatorios']),
                        ('dados/processed/jurisprudencia/pln_leve/ativa.json', ['pasta_dados', 'pasta_relatorios']),
                        ('dados/relatorios/jurisprudencia/revisao/revisao_ativa.json', ['pasta', 'pasta_dados']),
                        ('dados/relatorios/jurisprudencia/automacao/ativa.json', ['pasta_relatorios'])]:
        velho, novo = antigo(rel), ler(ROOT / rel)
        pares += [(velho[k], novo[k]) for k in chaves]
    auto_velho = ler(ROOT / [p for p in pares if 'automacao' in p[0]][0][0] / 'resumo_automatico.json')
    auto_novo = ler(ROOT / [p for p in pares if 'automacao' in p[1]][0][1] / 'resumo_automatico.json')
    pares.append((auto_velho['pasta_dados'], auto_novo['pasta_dados']))
    return pares


def caminhos(pares):
    mapa = {}
    for velho, novo in pares:
        for a, b in ((velho, novo), (velho.replace('\\', '/'), novo.replace('\\', '/')),
                     (velho.replace('/', '\\').replace('\\', '\\\\'), novo.replace('/', '\\').replace('\\', '\\\\'))):
            mapa[a] = b
    return dict(sorted(mapa.items(), key=lambda kv: -len(kv[0])))


def parear(velho, novo, mapa, chave=''):
    if 'codigo' in chave or 'finalizador' in chave or 'recuperacao_sha256' in chave or chave == 'executor_sha256':
        return
    if isinstance(velho, dict) and isinstance(novo, dict):
        for k in velho.keys() & novo.keys():
            parear(velho[k], novo[k], mapa, k)
    elif isinstance(velho, list) and isinstance(novo, list):
        if all(isinstance(x, dict) and 'arquivo_id' in x for x in velho + novo):
            nv = {x['arquivo_id']: x for x in novo}
            for x in velho:
                if x['arquivo_id'] in nv:
                    parear(x, nv[x['arquivo_id']], mapa, chave)
        elif len(velho) == len(novo):
            for a, b in zip(velho, novo):
                parear(a, b, mapa, chave)
    elif isinstance(velho, str) and isinstance(novo, str) and velho != novo and HEX.fullmatch(velho) and HEX.fullmatch(novo):
        mapa[velho] = novo


def hashes_das_etapas(pares):
    mapa = {}
    for velho, novo in pares:
        a, b = ROOT / velho, ROOT / novo
        for p in a.glob('*'):
            q = b / p.name
            if not (p.is_file() and q.is_file()):
                continue
            if p.suffix == '.json':
                parear(ler(p), ler(q), mapa)
            if p.stat().st_size < 64 * 1024 ** 2 and q.stat().st_size < 64 * 1024 ** 2:
                ha, hb = audit.hash_file(p), audit.hash_file(q)
                if ha != hb:
                    mapa[ha] = hb
    return mapa


def substituir_texto(texto, ids, hashes, paths):
    texto = HEX.sub(lambda m: ids.get(m.group(), hashes.get(m.group(), m.group())), texto)
    for a, b in paths.items():
        if a in texto:
            texto = texto.replace(a, b)
    return texto


def atualizar_protegidos(valor):
    """Dicionários {caminho do repositório: sha256} passam a refletir o arquivo atual."""
    if isinstance(valor, dict):
        for k, v in valor.items():
            if isinstance(v, str) and HEX.fullmatch(v) and ('/' in k or '\\' in k) and (ROOT / k).is_file():
                valor[k] = audit.hash_file(ROOT / k)
            else:
                atualizar_protegidos(v)
    elif isinstance(valor, list):
        for v in valor:
            atualizar_protegidos(v)


def migrar_arquivo(p, ids, hashes, paths):
    import pyarrow as pa
    import pyarrow.parquet as pq
    if p.suffix in TEXTO:
        bruto = p.read_bytes().decode('utf-8')
        novo = substituir_texto(bruto, ids, hashes, paths)
        if p.suffix == '.json':
            try:
                obj = json.loads(novo.lstrip('﻿'))
                antes = json.dumps(obj, sort_keys=True)
                atualizar_protegidos(obj)
                if json.dumps(obj, sort_keys=True) != antes:
                    novo = json.dumps(obj, ensure_ascii=False, indent=2) + '\n'
            except ValueError:
                pass
        if novo != bruto:
            p.write_bytes(novo.encode('utf-8'))
            return True
        return False
    if p.suffix == '.parquet':
        tabela = pq.read_table(p)
        colunas, mudou = [], False
        for nome, coluna in zip(tabela.column_names, tabela.columns):
            tipo = coluna.type
            if pa.types.is_string(tipo) or pa.types.is_large_string(tipo):
                valores = coluna.to_pylist()
                novos = [substituir_texto(v, ids, hashes, paths) if isinstance(v, str) else v for v in valores]
            elif pa.types.is_list(tipo) and pa.types.is_string(tipo.value_type):
                valores = coluna.to_pylist()
                novos = [[substituir_texto(x, ids, hashes, paths) if isinstance(x, str) else x for x in v]
                         if v is not None else None for v in valores]
            else:
                colunas.append(coluna)
                continue
            if novos != valores:
                mudou = True
                colunas.append(pa.chunked_array([pa.array(novos, type=tipo)]))
            else:
                colunas.append(coluna)
        if mudou:
            pq.write_table(pa.Table.from_arrays(colunas, schema=tabela.schema), p, compression='zstd')
        return mudou
    return False


def canonical(valor):
    import hashlib
    return hashlib.sha256(json.dumps(valor, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def recalcular_hashes_de_conteudo(hashes):
    """Hashes do próprio conteúdo (protocolo congelado: sha256 = canonical(protocolo)), propagados em cadeia."""
    p = ROOT / 'avaliacao/dados/jurisprudencia/protocolo_congelado.json'
    valor = ler(p)
    novo = canonical(valor['protocolo'])
    if novo == valor['sha256']:
        return 0
    hashes[valor['sha256']] = novo
    antes = audit.hash_file(p)
    valor['sha256'] = novo
    with p.open('w', encoding='utf-8') as f:
        json.dump(valor, f, ensure_ascii=False, indent=2)  # Mesmo formato de teste_final_chunking.freeze.
    hashes[antes] = audit.hash_file(p)
    return 1


def residuos(ids_antigos, hashes, paths):
    restantes = {}
    for d in DIRS:
        for p in (ROOT / d).rglob('*'):
            if not p.is_file() or p.suffix not in TEXTO | {'.parquet'}:
                continue
            if p.suffix == '.parquet':
                import pyarrow.parquet as pq
                texto = ' '.join(str(v) for c in pq.read_table(p).columns for v in c.to_pylist() if isinstance(v, (str, list)))
            else:
                texto = p.read_text(encoding='utf-8', errors='ignore')
            n = sum(1 for t in HEX.findall(texto) if t in ids_antigos or t in hashes) + sum(texto.count(a) for a in paths)
            if n:
                restantes[str(p.relative_to(ROOT))] = n
    return restantes


def main():
    import pandas as pd
    sys.stdout.reconfigure(encoding='utf-8')
    arquivar()
    mapa = pd.read_parquet(ROOT / 'dados/relatorios/jurisprudencia/base_reduzida/mapa_registro_id.parquet')
    ids = dict(zip(mapa.registro_id_base_completa, mapa.registro_id_novo))
    pares = pares_de_etapas()
    paths = caminhos(pares)
    hashes = hashes_das_etapas(pares)
    print(f'Mapa: {len(ids):,} IDs, {len(paths)} caminhos, {len(hashes)} hashes de etapas', flush=True)
    arquivos = [p for d in DIRS for p in (ROOT / d).rglob('*') if p.is_file() and p.suffix in TEXTO | {'.parquet'}]
    for rodada in range(1, 30):
        alterados = recalcular_hashes_de_conteudo(hashes)
        for p in arquivos:
            antes = audit.hash_file(p)
            if migrar_arquivo(p, ids, hashes, paths):
                alterados += 1
                hashes[antes] = audit.hash_file(p)
        print(f'Rodada {rodada}: {alterados} arquivos alterados', flush=True)
        if not alterados:
            break
    else:
        raise RuntimeError('Hashes em cadeia não convergiram.')
    # Amostra fixada: os 120 documentos da amostra original do chunking, na mesma ordem, com IDs novos.
    # Recalculada com a mesma regra de chunking.select_sample sobre o índice automático da base completa.
    indice_velho = ROOT / ler(ROOT / [v for v, n in pares if 'automacao' in v and 'reports' in v][0] / 'resumo_automatico.json')['indice']
    df = pd.read_parquet(indice_velho)
    df = df[df.candidato_consolidado & df.split_proposto.ne('teste')].copy()
    df['faixa'] = pd.cut(df.texto_caracteres, [0, 500, 2000, 10000, 50000, float('inf')], right=False).astype(str)
    df = df.sort_values('registro_id')
    df['ordem_estrato'] = df.groupby(['arquivo_id', 'tribunal', 'tipo_conteudo_declarado', 'faixa'], observed=True).cumcount()
    originais = sorted(df.sort_values(['ordem_estrato', 'registro_id']).head(120).registro_id)
    config = dict(amostra_ids=originais)
    amostra = [ids[i] for i in originais]
    audit.write_json(ROOT / 'dados/relatorios/jurisprudencia/base_reduzida/amostra_chunking_fixada.json',
                     dict(descricao='Amostra do chunking (notebook 04) fixada na migração para a base reduzida: mesmos '
                          'documentos e mesma ordem da amostra estratificada original, com registro_id novos.',
                          registro_ids=amostra))
    prefixos = {}
    for pre in PREFIXOS:
        velho = [i for i in ids if i.startswith(pre) and i in set(config['amostra_ids'])]
        if len(velho) != 1:
            raise RuntimeError(f'Prefixo {pre} ambíguo ou ausente na amostra.')
        prefixos[pre] = ids[velho[0]][:8]
    for nome in ('piloto_bge.py', 'experimento_orcamento.py'):
        p = ROOT / 'src/jurisprudencia' / nome
        t = p.read_text(encoding='utf-8')
        for a, b in prefixos.items():
            t = t.replace(f"'{a}'", f"'{b}'")
        p.write_text(t, encoding='utf-8')
    nb = json.loads(NB04.read_text(encoding='utf-8'))
    for c in nb['cells']:
        fonte = ''.join(c['source'])
        nova = substituir_texto(fonte, ids, hashes, paths)
        for a, b in prefixos.items():
            nova = nova.replace(a, b)
        if nova != fonte:
            c['source'] = nova.splitlines(keepends=True)
    NB04.write_text(json.dumps(nb, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    restantes = residuos(set(ids), {k for k in hashes if k not in set(hashes.values())}, paths)
    audit.write_json(ROOT / 'dados/relatorios/jurisprudencia/base_reduzida/migracao_experimentos_04.json',
                     dict(ids_mapeados=len(ids), caminhos_mapeados=len(paths), hashes_mapeados=len(hashes),
                          prefixos=prefixos, arquivo_originais=str(ARQUIVO.relative_to(ROOT)),
                          residuos=restantes))
    print('Prefixos:', prefixos)
    print('Resíduos da base completa:', restantes or 'nenhum')


if __name__ == '__main__':
    main()
