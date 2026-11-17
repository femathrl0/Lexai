"""Envia a base reduzida de jurisprudência para um dataset do Hugging Face e confere a integridade.

Envia: os 19 Parquets da versão PLN ativa (data/parquet/), o JSONL consolidado (data/jsonl/) e os
manifestos (manifestos/). Exige login prévio (`hf auth login`) e recusa repositório público.
Ao final, compara tamanho e SHA-256 (LFS) de cada arquivo remoto com o arquivo local.

Uso: python scripts/enviar_huggingface_base_reduzida.py laaaii/lex_ai
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from worker.ingestao.jurisprudencia import audit  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    from huggingface_hub import HfApi
    repo = sys.argv[1]
    api = HfApi()
    if not api.repo_info(repo, repo_type='dataset').private:
        raise RuntimeError('Repositório público: a base contém dados pessoais; torne-o privado antes do envio.')
    pln = json.loads((ROOT / 'dados/processed/jurisprudencia/pln_leve/ativa.json').read_text(encoding='utf-8'))
    exportacao = ROOT / 'dados/processed/jurisprudencia/exportacao/base_reduzida'
    envios = {f'dados/parquet/{p.name}': p for p in sorted((ROOT / pln['pasta_dados']).glob('f??.parquet'))}
    envios['dados/jsonl/jurisprudencia_pln_leve.jsonl'] = exportacao / 'jurisprudencia_pln_leve.jsonl'
    envios['manifestos/manifesto_jsonl.json'] = exportacao / 'manifesto_jsonl.json'
    envios['manifestos/manifesto_base_reduzida.json'] = ROOT / 'dados/relatorios/jurisprudencia/base_reduzida/manifesto_base_reduzida.json'
    envios['manifestos/resumo_pln.json'] = ROOT / pln['pasta_relatorios'] / 'resumo_pln.json'
    if len([k for k in envios if k.startswith('dados/parquet/')]) != 19:
        raise RuntimeError('Esperados 19 Parquets na versão PLN ativa.')
    locais = {}
    for destino, origem in envios.items():
        locais[destino] = (origem.stat().st_size, audit.hash_file(origem))
        print(f'Enviando {destino} ({origem.stat().st_size / 1e6:,.1f} MB)...', flush=True)
        api.upload_file(path_or_fileobj=str(origem), path_in_repo=destino, repo_id=repo, repo_type='dataset',
                        commit_message=f'Base reduzida de jurisprudência: {destino}')
    remotos = {f.path: f for f in api.list_repo_tree(repo, repo_type='dataset', recursive=True, expand=True)
               if getattr(f, 'size', None) is not None}
    falhas = []
    for destino, (tamanho, sha) in locais.items():
        r = remotos.get(destino)
        sha_remoto = r.lfs.sha256 if r is not None and getattr(r, 'lfs', None) else None
        ok = r is not None and r.size == tamanho and (sha_remoto is None or sha_remoto == sha)
        if not ok:
            falhas.append(destino)
        print(f"{'OK ' if ok else 'ERRO'} {destino} | {tamanho:,} bytes | sha256 {'conferido' if sha_remoto else 'sem LFS (arquivo pequeno)'}")
    if falhas:
        raise RuntimeError(f'Arquivos divergentes no repositório: {falhas}')
    print(f'Envio concluído e conferido: {len(locais)} arquivos em https://huggingface.co/datasets/{repo}')


if __name__ == '__main__':
    main()
