import copy,re,tempfile,unittest
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from worker.ingestao.jurisprudencia import chunking_definitivo as mod
from worker.ingestao.jurisprudencia import audit


class Tokenizer:
    def __call__(self,text,**kwargs):return dict(offset_mapping=[(m.start(),m.end()) for m in re.finditer(r'\S+',text)])
    def encode(self,text,**kwargs):return list(range(len(text.split())))
    def num_special_tokens_to_add(self,**kwargs):return 2


def fixture(text):
    d=dict(registro_id='a'*64,arquivo_id='f01',tribunal='TRT-13',texto_principal_campo='ementa',ementa=text,privacidade_status='cpf_mascarado')
    m=dict(texto_caracteres=len(text),tipo_conteudo_declarado='ementa',tipo_conteudo_inferido='ementa_declarada',grupo_avaliacao='grupo',split_proposto='teste')
    return d,m,dict(arquivo='dados/processed/jurisprudencia/pln_leve/f01.parquet',sha256='origem')


class DefinitiveTests(unittest.TestCase):
    def test_size_overlap_reconstruction_and_stable_ids(self):
        args=fixture(' '.join('palavra'+str(i) for i in range(1201)))
        rows,doc=mod.document_chunks(*args,Tokenizer())
        self.assertEqual(len(rows),3)
        self.assertEqual([r['tokens'] for r in rows],[500,500,401])
        self.assertEqual([r['sobreposicao_anterior_tokens'] for r in rows],[0,100,100])
        self.assertTrue(all(r['split_proposto']=='teste' for r in rows))
        mod.validate_partition(rows,[doc])
        again,_=mod.document_chunks(*args,Tokenizer())
        self.assertEqual([r['chunk_id'] for r in rows],[r['chunk_id'] for r in again])

    def test_source_privacy_and_empty_text_fail_closed(self):
        for text in ['CPF: 123.456.789-09','']:
            with self.assertRaises(ValueError):mod.document_chunks(*fixture(text),Tokenizer())

    def test_changed_text_or_group_rejected_on_reread(self):
        rows,doc=mod.document_chunks(*fixture('não salvo art. 482 § 2º [CPF_REMOVIDO]'),Tokenizer())
        wrong=copy.deepcopy(rows);wrong[0]['texto']=wrong[0]['texto'].replace('não','sim')
        with self.assertRaises(ValueError):mod.validate_partition(wrong,[doc])
        wrong=copy.deepcopy(rows);wrong[0]['split_proposto']='treino'
        with self.assertRaises(ValueError):mod.validate_partition(wrong,[doc])

    def test_gap_and_duplicate_document_rejected(self):
        rows,doc=mod.document_chunks(*fixture(' '.join('w'+str(i) for i in range(1201))),Tokenizer())
        with self.assertRaises(ValueError):mod.validate_partition(rows[1:],[doc])
        with self.assertRaises(ValueError):mod.validate_partition(rows,[doc,doc])

    def test_uniform_schema_for_null_metadata(self):
        rows,doc=mod.document_chunks(*fixture('texto jurídico íntegro'),Tokenizer())
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'chunks_a.parquet';mod.atomic_parquet(rows,path)
            table=pq.read_table(path)
            self.assertEqual(table.schema,mod.CHUNK_SCHEMA)
            mod.validate_partition(table.to_pylist(),[doc])

    def test_second_writer_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            with mod.writer_lock(folder):
                with self.assertRaises(RuntimeError):
                    with mod.writer_lock(folder):pass

    def test_real_checkpoint_resume_and_global_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);sourcepath=root/'dados/processed/jurisprudencia/pln_leve/source.parquet'
            sourcepath.parent.mkdir(parents=True)
            d,m,_=fixture('texto repetido com não e salvo')
            d2=dict(d,registro_id='b'*64)
            pq.write_table(pa.Table.from_pylist([d,d2]),sourcepath)
            source=dict(arquivo=str(sourcepath.relative_to(root)),arquivo_id='f01',sha256=audit.hash_file(sourcepath))
            report=root/'reports';data=root/'dados/chunks';report.mkdir();data.mkdir()
            metadata={doc['registro_id']:dict(m,arquivo_id='f01',tribunal='TRT-13') for doc in [d,d2]}
            state=dict(root=root,report=report,data=data,metadata=metadata,sources=[source],tokenizer=Tokenizer(),
                config=dict(caracteres_esperados=2*len(d['ementa'])),identity='teste')
            _,first=mod.process(state,max_lotes=1)
            self.assertEqual(first['documentos_processados'],2)
            files=list(data.glob('chunks_*.parquet'));self.assertEqual(len(files),1)
            before=files[0].read_bytes()
            _,resumed=mod.process(state)
            self.assertEqual(resumed['chunks'],2);self.assertEqual(before,files[0].read_bytes())
            result=mod.finalize(state)
            self.assertEqual(result['status'],'chunking_validado')
            self.assertEqual(result['ids_chunks_unicos'],2)
            self.assertEqual(result['grupos_chunks_textuais_repetidos'],1)
            self.assertEqual(result['ocorrencias_textuais_excedentes'],1)
            self.assertTrue((report/'manifesto_lotes.json').exists())
            files[0].write_bytes(before+b'alteracao')
            with self.assertRaises(ValueError):mod.process(state)

    def test_partial_corpus_is_not_published_as_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data=root/'data';report=root/'reports';data.mkdir();report.mkdir()
            state=dict(root=root,data=data,report=report,metadata={'faltante':{}},identity='teste',config=dict(caracteres_esperados=20))
            with self.assertRaises(ValueError):mod.finalize(state)
            self.assertFalse((report/'concluido.json').exists())


if __name__=='__main__':unittest.main()
