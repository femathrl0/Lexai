from pathlib import Path
from unittest.mock import patch
import copy,json,tempfile,unittest
import numpy as np,pyarrow as pa,pyarrow.parquet as pq
from worker.ingestao.jurisprudencia import embeddings_definitivos as emb,chunking_definitivo as chunks
from worker.ingestao.jurisprudencia import proxima_etapa
from worker.evidencia.indices import jurisprudencia_pgvector as store


def row(text,ident):
    return dict(chunk_id=ident,registro_id='doc_'+ident,texto=text,texto_sha256=chunks.base.sha(text),tokens=4,tokens_com_especiais=6)


class FakeTokenizer:
    def encode(self,text,**kwargs):return text.split()


class FakeModel:
    tokenizer=FakeTokenizer()
    def encode(self,texts,**kwargs):
        out=np.zeros((len(texts),1024),dtype=np.float32)
        for i,text in enumerate(texts):out[i,int(chunks.base.sha(text)[:4],16)%1024]=1
        return out


class EmbeddingTests(unittest.TestCase):
    def test_invalid_vectors_rejected(self):
        for v in [np.zeros((2,1024),dtype=np.float32),np.ones((1,10),dtype=np.float32),np.full((1,1024),np.nan,dtype=np.float32)]:
            with self.assertRaises(ValueError):emb.validate_vectors(v,len(v))

    def test_swapped_vectors_or_ids_rejected(self):
        rows=[row('texto um','a'),row('texto dois','b')];v=FakeModel().encode([r['texto'] for r in rows]);m=emb.mapping_for(rows,v)
        emb.validate_mapping(rows,v,m)
        with self.assertRaises(ValueError):emb.validate_mapping(rows,v[::-1].copy(),m)
        altered=copy.deepcopy(m);altered[0]['chunk_id']='outro'
        with self.assertRaises(ValueError):emb.validate_mapping(rows,v,altered)

    def test_no_start_before_full_chunking_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            with patch('worker.ingestao.jurisprudencia.chunking_definitivo_relatorio.load',return_value={'report':p}):
                with self.assertRaises(ValueError):emb.prepare(p)

    def test_cache_reuse_checkpoint_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data=root/'vectors';report=root/'reports';data.mkdir();report.mkdir()
            rows=[row('mesmo texto','a'),row('mesmo texto','b')];inputfile=root/'chunks.parquet';pq.write_table(pa.Table.from_pylist(rows),inputfile)
            batch=dict(arquivo_id='f01',batch=0,chunks_arquivo='chunks.parquet',chunks_sha256=chunks.audit.hash_file(inputfile))
            state=dict(root=root,data=data,report=report,batches=[batch],identity='teste',config=dict(backbone={'device':'cpu'},backbone_sha256='fake',chunks_esperados=2))
            with patch.object(emb.backbone,'load_model',return_value=FakeModel()),patch.object(emb.backbone,'check_legislation',return_value={'status':'teste'}):
                _,result=emb._run(state,None)
                self.assertEqual(result['chunks_restantes'],0)
                checkpoint=json.loads((report/'lote_f01_000000.json').read_text(encoding='utf-8'))
                self.assertEqual(checkpoint['textos_novos_codificados'],1)
                vectorfile=root/checkpoint['vetores_arquivo'];original=vectorfile.read_bytes()
                _,again=emb._run(state,None)
                self.assertEqual(again['chunks_vetorizados'],2);self.assertEqual(vectorfile.read_bytes(),original)
                vectorfile.write_bytes(original+b'alterado')
                with self.assertRaises(ValueError):emb._run(state,None)

    def test_pgvector_rejects_changed_text_or_metadata(self):
        r=row('texto','a');v=FakeModel().encode(['texto']);m=emb.mapping_for([r],v)[0]
        stored=(r['chunk_id'],r['registro_id'],r['texto_sha256'],m['vector_sha256'],v[0],r['texto'],{k:x for k,x in r.items() if k!='texto'})
        store.verify_stored(r,m,stored)
        wrong=list(stored);wrong[5]='texto alterado'
        with self.assertRaises(ValueError):store.verify_stored(r,m,tuple(wrong))

    def test_pgvector_requires_completed_embeddings(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):store.import_verified({'report':Path(folder)})

    def test_schema_does_not_write_legislation_tables(self):
        self.assertIn('lex_jurisprudencia',store.DDL)
        self.assertNotIn('lex_clt.',store.DDL)

    def test_resource_question_blocks_full_scale_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=root/proxima_etapa.POLICY;p.parent.mkdir(parents=True)
            chunks.atomic_json(p,{'estado':'aguardando_escolha_recurso','corpus_chunking':'corpus'})
            with patch.object(proxima_etapa,'input_ready',return_value=True),patch.object(emb,'run') as encode:
                proxima_etapa.run(root)
                encode.assert_not_called()
            record=json.loads((p.parent/'encadeamento.json').read_text(encoding='utf-8'))
            self.assertFalse(record['geracao_embeddings_iniciada'])


if __name__=='__main__':unittest.main()
