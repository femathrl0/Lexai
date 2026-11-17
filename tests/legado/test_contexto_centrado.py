import re,unittest
from worker.ingestao.jurisprudencia import contexto_centrado as ctx,chunking_suporte as base

class Tokenizer:
    def __call__(self,text,**kwargs):return dict(offset_mapping=[(m.start(),m.end()) for m in re.finditer(r'\S+',text)])
    def encode(self,text,**kwargs):return list(range(len(text.split())))

def unit(text,a,b,ident='d',key='u'):
    return dict(registro_id=ident,inicio=a,fim=b,texto=text[a:b],texto_sha256=base.sha(text[a:b]),
        tokens=len(text[a:b].split()),contexto_inicio=0,contexto_fim=len(text),chunk_id=key,rank=1)

class BudgetTests(unittest.TestCase):
    def test_ignored_trailing_whitespace_is_not_encoder_truncation(self):
        from worker.ingestao.jurisprudencia.experimento_orcamento import encoder_retained
        row=dict(inicio=0,fim=20)
        kept=encoder_retained(row,dict(truncado=False,fim_retido=18))
        self.assertEqual(kept['fim'],20)
    def test_actual_encoder_cut_uses_original_unit_origin(self):
        from worker.ingestao.jurisprudencia.experimento_orcamento import encoder_retained
        row=dict(inicio=20,fim=40,unidade_indexada_inicio=10)
        kept=encoder_retained(row,dict(truncado=True,fim_retido=15))
        self.assertEqual(kept['fim'],25)
    def test_context_centers_on_hit_not_section_start(self):
        text=' '.join('w'+str(i) for i in range(40));a=text.index('w30');b=text.index('w32')
        pack=ctx.Packer({'d':dict(texto=text)},Tokenizer())
        selected,used,_,_=pack.pack([unit(text,a,b)],10,section=True)
        self.assertEqual(used,10);self.assertIn('w30',selected[0]['texto']);self.assertIn('w33',selected[0]['texto'])
        self.assertNotIn('w0 ',selected[0]['texto'])
    def test_budget_can_take_more_than_five_units(self):
        docs={str(i):dict(texto='palavra') for i in range(20)}
        ranking=[unit('palavra',0,7,str(i),str(i)) for i in range(20)]
        selected,used,_,examined=ctx.Packer(docs,Tokenizer()).pack(ranking,12)
        self.assertEqual(len(selected),12);self.assertEqual(used,12);self.assertEqual(examined,12)
    def test_overlap_not_counted_twice(self):
        text='a b c d e f g h i j'
        r=unit(text,4,7);pack=ctx.Packer({'d':dict(texto=text)},Tokenizer())
        selected,used,_,_=pack.pack([r,r],20,window_tokens=6)
        self.assertEqual(used,6)
        intervals=sorted((r['inicio'],r['fim']) for r in selected)
        self.assertTrue(all(a[1]<=b[0] for a,b in zip(intervals,intervals[1:])))
    def test_large_plain_section_is_cut_not_skipped(self):
        text=' '.join('w'+str(i) for i in range(100));r=unit(text,0,len(text))
        selected,used,cuts,_=ctx.Packer({'d':dict(texto=text)},Tokenizer()).pack([r],5)
        self.assertEqual(used,5);self.assertEqual(cuts,1);self.assertTrue(selected[0]['texto'].startswith('w0'))
    def test_window_near_edge_preserves_hit(self):
        text='a b c d e f g h i j';r=unit(text,18,19)
        selected,used,_,_=ctx.Packer({'d':dict(texto=text)},Tokenizer()).pack([r],6,window_tokens=6)
        self.assertEqual(used,6);self.assertTrue(selected[0]['texto'].endswith('j'))
    def test_section_window_does_not_cross_parent_scope(self):
        text='a b c d e f g h i j';r=dict(unit(text,10,11),contexto_inicio=8,contexto_fim=15)
        selected,used,_,_=ctx.Packer({'d':dict(texto=text)},Tokenizer()).pack([r],20,section=True)
        self.assertEqual(selected[0]['inicio'],8);self.assertEqual(selected[0]['fim'],15);self.assertEqual(used,4)
    def test_returned_offsets_reproduce_delivered_text(self):
        text='um dois três quatro cinco seis sete oito nove dez'
        selected,used,_,_=ctx.Packer({'d':dict(texto=text)},Tokenizer()).pack([unit(text,14,25)],5,window_tokens=7)
        self.assertLessEqual(used,5)
        for r in selected:self.assertEqual(r['texto'],text[r['inicio']:r['fim']])
    def test_no_gold_is_an_input_to_context_selection(self):
        import inspect
        signature=str(inspect.signature(ctx.Packer.pack))
        self.assertNotIn('gold',signature);self.assertNotIn('evidencia',signature)

if __name__=='__main__':unittest.main()
