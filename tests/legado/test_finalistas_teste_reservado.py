import contextlib,io,json,re,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np,pandas as pd
from worker.ingestao.jurisprudencia import finalistas_chunking as sweep,teste_final_chunking as final
from worker.ingestao.jurisprudencia import chunking_suporte as base,audit

class Tokenizer:
    def __call__(self,text,**kwargs):return {'offset_mapping':[(m.start(),m.end()) for m in re.finditer(r'\S+',text)]}
    def encode(self,text,**kwargs):return list(range(len(text.split())))

class FinalProtocolTests(unittest.TestCase):
    def test_complete_alternative_must_be_available_in_frozen_corpus(self):
        q=dict(alternativas_suporte=[[dict(registro_id='a'),dict(registro_id='b')]])
        self.assertFalse(final.source_available(q,{'a':{}}))
        q['alternativas_suporte'].append([dict(registro_id='a')])
        self.assertTrue(final.source_available(q,{'a':{}}))
    def test_cannot_open_reserved_questions_before_freeze(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):final.reserved_for_annotation(Path(d))
    def test_changed_frozen_protocol_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'avaliacao/dados/jurisprudencia';p.mkdir(parents=True)
            (p/'protocolo_congelado.json').write_text(json.dumps(dict(protocolo={'a':2},sha256=final.canonical({'a':1}))),encoding='utf-8')
            with self.assertRaises(AssertionError):final.load_protocol(root)
    def test_fixed_overlap_preserves_union_and_limit(self):
        text=' '.join('w'+str(i) for i in range(100));d=dict(registro_id='d',texto=text)
        rows=sweep.make_fixed(d,{},Tokenizer(),16,3)
        self.assertEqual(rows[0]['inicio'],0);self.assertEqual(rows[-1]['fim'],len(text))
        self.assertTrue(all(r['tokens']<=16 for r in rows))
        self.assertTrue(any(b['inicio']<a['fim'] for a,b in zip(rows,rows[1:])))
        for a,b in zip(rows,rows[1:]):self.assertLessEqual(b['inicio'],a['fim'])
        for r in rows:self.assertEqual(r['texto'],text[r['inicio']:r['fim']])
    def test_seven_grid_entries_include_overlap_and_broad_sizes(self):
        self.assertEqual(len(sweep.GRID),7)
        self.assertEqual({s for s,o in sweep.GRID if o==0},{256,500,1000,2500,5000})
        self.assertIn((500,50),sweep.GRID);self.assertIn((500,100),sweep.GRID)
    def test_final_execution_missing_document_and_no_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'avaliacao/dados/jurisprudencia').mkdir(parents=True)
            report=root/'dados/relatorios/fake_final';report.mkdir(parents=True)
            corpus=root/'corpus';corpus.write_text('texto da decisão',encoding='utf-8')
            text='texto da decisão';sha=base.sha(text)
            row=dict(registro_id='d',chunk_id='u',texto=text,texto_sha256=sha,inicio=0,fim=len(text),
                campo_texto='inteiro_teor',tokens=3,contexto_inicio=0,contexto_fim=len(text))
            queries=[dict(query_id='q'+str(i),pergunta='pergunta '+str(i)) for i in range(7)]
            gold=[]
            for i,q in enumerate(queries):
                if i==6:gold.append(dict(q,avaliacao='comportamental',alternativas_suporte=[]));continue
                ref=dict(registro_id='fora' if i==1 else 'd',campo_texto='inteiro_teor',inicio=0,fim=5)
                gold.append(dict(q,avaliacao='suporte_intervalos',alternativas_suporte=[[ref]]))
            state=dict(root=root,report=report,questions=queries,gold=gold,eligible=gold[:6],docs={'d':dict(texto=text)},
                units={'i':[row]},variants={'fixa':('i',None),'paragrafo':('i',5)},tokenizer=Tokenizer(),
                identity='fixture',config=dict(protocolo_sha256='p',gabarito_sha256='g'),
                protocol=dict(orcamentos=[500,1000,2500,5000],arquivo_corpus='corpus',corpus_sha256=audit.hash_file(corpus)))
            v=np.zeros(1024,dtype=np.float32);v[0]=1
            vectors={sha:v,**{base.sha(q['pergunta']):v for q in queries}}
            def encode(_):
                audit.write_json(report/'execucao_encoder.json',dict(consultas_codificadas=[q['query_id'] for q in queries],reserva_codificada=False))
                return vectors,{}
            with patch.object(final,'prepare',return_value=state),patch.object(final.piloto_bge,'encode',side_effect=encode) as mock_encoder:
                with contextlib.redirect_stdout(io.StringIO()):summary=final.run(root)
                self.assertTrue(np.allclose(summary.cobertura_2500,5/6))
                self.assertTrue(summary.perguntas_com_intervalo.eq(6).all())
                curve=pd.read_csv(report/'cobertura.csv')
                self.assertTrue(curve[curve.query_id.eq('q1')].cobertura.eq(0).all())
                self.assertFalse(curve[curve.query_id.eq('q1')].documento_suporte_no_corpus.any())
                self.assertTrue(curve[curve.query_id.eq('q6')].cobertura.isna().all())
                with self.assertRaisesRegex(ValueError,'concluído'):final.run(root)
                self.assertEqual(mock_encoder.call_count,1)
            self.assertTrue(json.loads((report/'execucao_encoder.json').read_text())['reserva_codificada'])
            self.assertTrue((root/'avaliacao/dados/jurisprudencia/teste_final_iniciado.json').exists())

if __name__=='__main__':unittest.main()
