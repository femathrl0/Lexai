import unittest
import pandas as pd
from worker.ingestao.jurisprudencia import avaliacao_complementar as mod
from worker.ingestao.jurisprudencia import chunking_suporte as base


class CharTokenizer:
    def encode(self,text,**kwargs):return list(range(len(text)))
    def __call__(self,text,**kwargs):
        return dict(input_ids=list(range(len(text))))


class ComplementaryTests(unittest.TestCase):
    def test_merge_preserves_sources_and_deduplicates_identifier(self):
        a=dict(registro_id='a',texto='ABC',campo_texto='inteiro_teor')
        b=dict(registro_id='b',texto='ABC',campo_texto='inteiro_teor')
        self.assertEqual(list(mod.merge_documents([[a],[a,b]])),['a','b'])

    def test_conflicting_document_is_rejected(self):
        a=dict(registro_id='a',texto='ABC',campo_texto='inteiro_teor')
        with self.assertRaises(ValueError):mod.merge_documents([[a],[dict(a,texto='ABD')]])

    def test_audit_overlap_has_full_union_but_gap_rejected(self):
        docs={'a':dict(texto='ABCDEF')}
        def row(a,b):
            t='ABCDEF'[a:b]
            return dict(registro_id='a',inicio=a,fim=b,texto=t,texto_sha256=base.sha(t),tokens=len(t),metodo_fronteira='tokens')
        check=mod.audit_units([row(0,4),row(3,6)],docs,CharTokenizer())
        self.assertTrue(check['reconstrucao_sem_lacunas'])
        self.assertEqual(check['caracteres_sobrepostos'],1)
        with self.assertRaises(AssertionError):mod.audit_units([row(0,2),row(3,6)],docs,CharTokenizer())

    def test_bootstrap_keeps_cohorts_and_na_separate(self):
        rows=[]
        for q,a,b in [('held',1,0),('dev',0,1),('behavior',None,None)]:
            for v,c in [('fixa_500_o100',a),('paragrafo_janela_500',b)]:
                rows.append(dict(query_id=q,recuperador='BGE-M3',versao=v,orcamento=2500,cobertura=c))
        result=mod.compare(pd.DataFrame(rows),['held','behavior']).set_index('coorte')
        self.assertEqual(result.loc['reserva_ja_exposta','n'],1)
        self.assertEqual(result.loc['reserva_ja_exposta','delta_media'],1)
        self.assertEqual(result.loc['ajuste_anterior','delta_media'],-1)

    def test_offset_drift_rejected(self):
        from worker.ingestao.jurisprudencia.chunking_avancado import original_reference
        d=dict(registro_id='a',texto='ABCDEF',texto_principal_campo='inteiro_teor')
        q=dict(query_id='q',pergunta='?',alternativas_suporte=[[original_reference(d,1,3)]])
        base.validate_questions([q],{'a':d})
        with self.assertRaises(ValueError):base.validate_questions([q],{'a':dict(d,texto='AXCDEF')})


if __name__=='__main__':unittest.main()
