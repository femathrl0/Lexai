import copy
import tempfile
import unittest
from pathlib import Path
import re
import pandas as pd
from worker.ingestao.jurisprudencia import chunking_avancado as adv
from worker.ingestao.jurisprudencia import chunking_suporte as base


class Tokenizer:
    def __call__(self,text,**kwargs):return {'offset_mapping':[(m.start(),m.end()) for m in re.finditer(r'\S+',text)]}
    def encode(self,text,add_special_tokens=False,**kwargs):return list(range(len(text.split())+(2 if add_special_tokens else 0)))
    def num_special_tokens_to_add(self,pair=False):return 2


def doc(text):
    return dict(registro_id='doc',texto=text,arquivo_id='fixture',tribunal='FICTICIO',split_proposto='controle',
        grupo_avaliacao='doc',texto_principal_campo='inteiro_teor',parent_arquivo='fixture',parent_sha256=base.sha(text))


class AdvancedTests(unittest.TestCase):
    def setUp(self):self.tokenizer=Tokenizer()
    def test_continuous_coverage_union_no_double_count(self):
        ref=dict(registro_id='d',campo_texto='inteiro_teor',inicio=10,fim=20)
        hits=[dict(ref,inicio=10,fim=14),dict(ref,inicio=12,fim=16)]
        self.assertEqual(adv.ref_fraction(ref,hits),.6)
    def test_continuous_coverage_gap_and_document(self):
        ref=dict(registro_id='d',campo_texto='inteiro_teor',inicio=0,fim=10)
        self.assertEqual(adv.ref_fraction(ref,[dict(ref,fim=4),dict(ref,inicio=6)]),.8)
        self.assertEqual(adv.ref_fraction(ref,[dict(ref,registro_id='outro')]),0)
    def test_alternative_evidence_and_weighted_character_fraction(self):
        a=dict(registro_id='d',campo_texto='inteiro_teor',inicio=0,fim=10)
        b=dict(a,inicio=20,fim=50)
        q=dict(alternativas_suporte=[[a,b]])
        self.assertEqual(adv.support_fraction(q,[a]),.25)
        q['alternativas_suporte'].append([a]);self.assertEqual(adv.support_fraction(q,[a]),1)
    def test_overlapping_gold_intervals_not_double_counted(self):
        a=dict(registro_id='d',campo_texto='inteiro_teor',inicio=0,fim=10)
        b=dict(a,inicio=5,fim=15)
        self.assertEqual(adv.support_fraction(dict(alternativas_suporte=[[a,b]]),[a]),2/3)
    def test_gold_anchors_source_not_chunk(self):
        d=doc('Original sem cortes. Decisão final.');a=d['texto'].index('Decisão')
        ref=adv.original_reference(d,a,len(d['texto']),'dispositivo')
        self.assertEqual(ref['texto_base_sha256'],base.sha(d['texto']))
        self.assertEqual(ref['texto_sha256'],base.sha('Decisão final.'))
        self.assertEqual(ref['inicio'],a)
    def test_changed_original_invalidates_gold(self):
        d=doc('Decisão final.');r=adv.original_reference(d,0,len(d['texto']))
        r['texto_base_sha256']='invalido'
        with self.assertRaises(ValueError):base.validate_questions([dict(query_id='q',pergunta='Qual?',alternativas_suporte=[[r]])],{'doc':d})
    def test_pre_pln_offsets_are_not_mistaken_for_protected(self):
        d=doc('Decisão.');r=adv.original_reference(d,0,len(d['texto']));r['espaco_offsets']='bruto_pre_pln'
        with self.assertRaises(ValueError):base.validate_questions([dict(query_id='q',pergunta='Qual?',alternativas_suporte=[[r]])],{'doc':d})
    def test_long_units_512_and_8192(self):
        d=doc('palavra '*8300)
        rows=adv.build_chunks(d,'paragrafo',self.tokenizer)
        result=adv.unit_audit(rows,{'doc':d},self.tokenizer)
        self.assertEqual(result['acima_512'],1);self.assertEqual(result['acima_8192'],1)
        self.assertEqual(result['vetores_gerados'],0);self.assertEqual(result['vetores_planejados'],1)
    def test_cap_preserves_text_and_limits(self):
        d=doc('FUNDAMENTAÇÃO\n\nHORAS EXTRAS\n\n'+'palavra '*9000)
        rows=adv.build_chunks(d,'secao_teto',self.tokenizer)
        self.assertTrue(all(r['tokens']<=500 for r in rows))
        self.assertEqual(''.join(r['texto'] for r in rows),d['texto'])
        adv.unit_audit(rows,{'doc':d},self.tokenizer)
    def test_minimum_paragraph_merges_short_units_within_section(self):
        d=doc(('palavra '*50+'\n\n')*4)
        rows=adv.build_chunks(d,'paragrafo_minimo',self.tokenizer)
        self.assertEqual(len(rows),2);self.assertGreaterEqual(rows[0]['tokens'],128)
        self.assertEqual(''.join(r['texto'] for r in rows),d['texto'])
    def test_minimum_paragraph_does_not_cross_heading(self):
        d=doc('RELATÓRIO\n\nPedido curto.\n\nFUNDAMENTAÇÃO\n\nDecisão curta.')
        rows=adv.build_chunks(d,'paragrafo_minimo',self.tokenizer);point=d['texto'].index('FUNDAMENTAÇÃO')
        self.assertFalse(any(r['inicio']<point<r['fim'] for r in rows))
    def test_minimum_paragraph_respects_heading_inside_irregular_paragraph(self):
        d=doc('Preâmbulo.\n\nRELATÓRIO\nPedido.\nFUNDAMENTAÇÃO\nDecisão curta.')
        rows=adv.build_chunks(d,'paragrafo_minimo',self.tokenizer);point=d['texto'].index('FUNDAMENTAÇÃO')
        self.assertFalse(any(r['inicio']<point<r['fim'] for r in rows))
        self.assertEqual(''.join(r['texto'] for r in rows),d['texto'])
    def test_expansion_indexes_same_paragraphs_not_parents(self):
        d=doc('RELATÓRIO\n\nPedido.\n\nFUNDAMENTAÇÃO\n\nMotivo A.\n\nMotivo B.')
        a=adv.build_chunks(d,'paragrafo',self.tokenizer);b=adv.build_chunks(d,'paragrafo_secao',self.tokenizer)
        self.assertEqual([(r['inicio'],r['fim']) for r in a],[(r['inicio'],r['fim']) for r in b])
        self.assertTrue(any(r['contexto_fim']>r['fim'] for r in b))
    def test_all_variants_reconstruct_have_boundary_method(self):
        docs,_=base.controlled_cases()
        for d in docs:
            for version in adv.TITLES:
                rows=adv.build_chunks(d,version,self.tokenizer)
                adv.unit_audit(rows,{d['registro_id']:d},self.tokenizer)
                self.assertTrue(all(r['metodo_fronteira'] for r in rows))
    def test_audit_detects_corrupt_source_slice(self):
        d=doc('Texto jurídico íntegro.');rows=adv.build_chunks(d,'paragrafo',self.tokenizer)
        rows[0]['texto']='alterado'
        with self.assertRaises(ValueError):adv.unit_audit(rows,{'doc':d},self.tokenizer)
    def test_ambiguity_is_not_unknown_or_not_applicable(self):
        d=doc('Texto sem estrutura.')
        a=adv.unit_audit(adv.build_chunks(d,'paragrafo',self.tokenizer),{'doc':d},self.tokenizer)
        self.assertIsNone(a['fracao_tema_ambiguo'])
        rows=adv.build_chunks(d,'secao_tema',self.tokenizer);rows[0]['tema']='multiplos_temas'
        b=adv.unit_audit(rows,{'doc':d},self.tokenizer);self.assertEqual(b['fracao_tema_ambiguo'],1)
    def test_budget_never_exceeds_limit_and_deduplicates(self):
        d=doc('palavra '*6000);rows=adv.build_chunks(d,'paragrafo',self.tokenizer)
        for budget in adv.BUDGETS:
            ctx,used,cuts=adv.context_at_budget(rows+rows,{'doc':d},self.tokenizer,budget)
            self.assertLessEqual(used,budget);self.assertEqual(used,budget)
            self.assertEqual(len(ctx),1);self.assertEqual(cuts,1)
    def test_budget_expansion_keeps_retrieved_nucleus_first(self):
        d=doc('RELATÓRIO\n\n'+'antigo '*1000+'\n\nFUNDAMENTAÇÃO\n\n'+'motivo '*1000+'\n\nDecisão essencial.')
        rows=adv.build_chunks(d,'paragrafo_secao',self.tokenizer);last=rows[-1]
        ctx,used,_=adv.context_at_budget([last],{'doc':d},self.tokenizer,500)
        self.assertEqual(ctx[0]['inicio'],last['inicio']);self.assertIn('Decisão essencial.',ctx[0]['texto'])
        self.assertLessEqual(used,500)
    def test_coverage_monotone_with_budget(self):
        d=doc('palavra '*2000);rows=adv.build_chunks(d,'paragrafo',self.tokenizer)
        q=dict(alternativas_suporte=[[adv.original_reference(d,0,len(d['texto']))]])
        values=[adv.support_fraction(q,adv.context_at_budget(rows,{'doc':d},self.tokenizer,b)[0]) for b in adv.BUDGETS]
        self.assertEqual(values,sorted(values))
    def test_encoder_loss_is_simulated_not_actual(self):
        d=doc('palavra '*9000+'DECISÃO.');r=adv.original_reference(d,d['texto'].index('DECISÃO'),len(d['texto']))
        q=dict(query_id='q',alternativas_suporte=[[r]])
        rows=adv.build_chunks(d,'paragrafo',self.tokenizer)
        diagnosis=adv.diagnose(q,rows,rows,self.tokenizer)
        self.assertEqual(diagnosis['truncamento_encoder_real'],'nao_aplicavel_encoder_nao_executado')
        self.assertGreater(diagnosis['perda_suporte_simulada_encoder_8192'],0)
    def test_failure_wrong_document_wrong_span_and_boundary(self):
        d=doc('palavra '*1000);ref=adv.original_reference(d,10,100);q=dict(query_id='q',alternativas_suporte=[[ref]])
        rows=adv.build_chunks(d,'janela_500',self.tokenizer)
        other=dict(rows[0],registro_id='outro')
        self.assertTrue(adv.diagnose(q,[other],rows,self.tokenizer)['acordao_errado'])
        self.assertTrue(adv.diagnose(q,[rows[-1]],rows,self.tokenizer)['trecho_errado'])
        point=rows[0]['fim'];q['alternativas_suporte']=[[adv.original_reference(d,point-5,point+5)]]
        self.assertTrue(adv.diagnose(q,[rows[0]],rows,self.tokenizer)['evidencia_cortada_na_recuperacao'])
    def test_section_misclassification_needs_reference_label(self):
        d=doc('RELATÓRIO\n\nPedido.');ref=adv.original_reference(d,0,len(d['texto']),'fundamentacao')
        q=dict(query_id='q',alternativas_suporte=[[ref]]);rows=adv.build_chunks(d,'secao_tema',self.tokenizer)
        self.assertTrue(adv.diagnose(q,rows,rows,self.tokenizer)['secao_mal_classificada'])
        ref.pop('secao_esperada');self.assertIsNone(adv.diagnose(q,rows,rows,self.tokenizer)['secao_mal_classificada'])
    def test_paired_wins_ties_losses_bootstrap_same_seed(self):
        rows=[dict(escopo='teste',orcamento=500,query_id=str(i),versao=v,suporte_fracao=x)
              for i,(a,b) in enumerate([(1,0),(0,1),(.5,.5)]) for v,x in [('a',a),('b',b)]]
        frame=pd.DataFrame(rows);one=adv.paired(frame,replicas=300);two=adv.paired(frame,replicas=300)
        pd.testing.assert_frame_equal(one,two)
        row=one.iloc[0];self.assertEqual((row.vitorias,row.empates,row.derrotas),(1,1,1));self.assertEqual(row.n,3)
    def test_missing_gold_not_ties_or_zero(self):
        frame=pd.DataFrame([dict(escopo='real',orcamento=500,query_id='q',versao=v,suporte_fracao=None) for v in ['a','b']])
        result=adv.paired(frame).iloc[0]
        self.assertEqual(result.n,0);self.assertIsNone(result.empates);self.assertEqual(result.status,'sem_gabarito')
    def test_fixed_split_disjoint_and_family_intact(self):
        queries=[dict(query_id=str(i),tema='vínculo (PJ)' if i<4 else 'tema '+str(i)) for i in range(30)]
        a=adv.assign_splits(queries);self.assertEqual(a,adv.assign_splits(queries))
        self.assertEqual(len(a),30);self.assertEqual(len({r['query_id'] for r in a}),30)
        self.assertEqual(len({r['particao'] for r in a if r['familia_tematica']=='vínculo'}),1)
        self.assertEqual({r['particao'] for r in a},{'ajuste','teste_final'})
    def test_final_does_not_repeat_existing_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lock=root/'avaliacao/dados/jurisprudencia/teste_final_iniciado.json';lock.parent.mkdir(parents=True);lock.write_text('{}')
            with self.assertRaises(ValueError):adv.prepare(root,final=True)
    def test_freeze_requires_completed_adjustment(self):
        with self.assertRaises(ValueError):adv.freeze(dict(partition='teste_final'))
        with self.assertRaises(ValueError):adv.freeze(dict(partition='ajuste',complete=False))
    def test_frozen_protocol_is_idempotent_but_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=dict(root=Path(tmp),partition='ajuste',complete=True,split_records=[],config=dict(
                csv_perguntas_sha256='csv',corpus_documentos=[],codigo_avancado_sha256='a',
                codigo_sha256='b',codigo_cobertura_sha256='c',tokenizer_backend_sha256='t'))
            path=adv.freeze(state);before=path.read_bytes()
            self.assertEqual(adv.freeze(state),path);self.assertEqual(path.read_bytes(),before)
            state['config']['codigo_avancado_sha256']='alterado'
            with self.assertRaises(ValueError):adv.freeze(state)
            self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':unittest.main()
