import json,re,tempfile,unittest
from pathlib import Path
from worker.ingestao.jurisprudencia import piloto_bge as pilot,chunking_avancado as adv
from worker.ingestao.jurisprudencia import controles_chunking_dificeis as controls

class Tokenizer:
    def encode(self,text,add_special_tokens=False,**kwargs):return list(range(len(text.split())+(2 if add_special_tokens else 0)))
    def __call__(self,text,add_special_tokens=True,truncation=False,max_length=None,**kwargs):
        offsets=[(m.start(),m.end()) for m in re.finditer(r'\S+',text)]
        if add_special_tokens:offsets=[(0,0)]+offsets+[(0,0)]
        if truncation and len(offsets)>max_length:offsets=offsets[:max_length-1]+[(0,0)]
        return dict(input_ids=list(range(len(offsets))),offset_mapping=offsets)

class PilotTests(unittest.TestCase):
    def test_encoder_limit_includes_special_tokens_and_keeps_absolute_cut(self):
        tokenizer=Tokenizer();text='um dois três quatro cinco'
        view=pilot.encoder_view(text,tokenizer,limit=5)
        self.assertEqual(view['tokens_com_especiais'],7)
        self.assertEqual(view['tokens_encoder'],5)
        self.assertTrue(view['truncado'])
        self.assertEqual(text[:view['fim_retido']],'um dois três')
    def test_short_encoder_view_does_not_report_truncation(self):
        view=pilot.encoder_view('texto curto',Tokenizer(),8192)
        self.assertFalse(view['truncado']);self.assertEqual(view['fim_retido'],11)
    def test_expansion_cost_counts_parent_once_for_two_children(self):
        text='a b c d e f g h i j'
        docs={'d':dict(texto=text)}
        a=dict(registro_id='d',inicio=0,fim=3,contexto_inicio=0,contexto_fim=len(text),tokens=2)
        b=dict(a,inicio=4,fim=7)
        value=pilot.expanded_cost([a,b],docs,Tokenizer())
        self.assertEqual(value['tokens_indice_top5'],4)
        self.assertEqual(value['tokens_contexto_top5_expandido'],10)
    def test_harder_controls_include_opposite_quote_and_combined_support(self):
        docs,qs=controls.cases();self.assertEqual(len(docs),12);self.assertEqual(len(qs),12)
        q=next(q for q in qs if q['desafio']=='precedente_citado_oposto')
        d=next(d for d in docs if d['registro_id']==q['alternativas_suporte'][0][0]['registro_id'])
        report_end=d['texto'].index('FUNDAMENTAÇÃO')
        self.assertEqual(adv.support_fraction(q,[dict(registro_id=d['registro_id'],campo_texto='inteiro_teor',inicio=0,fim=report_end)]),0)
        refs=q['alternativas_suporte'][0]
        self.assertLess(adv.support_fraction(q,[refs[-1]]),1)
        self.assertEqual(adv.support_fraction(q,refs),1)
    def test_long_control_evidence_is_after_encoder_prefix(self):
        docs,qs=controls.cases();q=next(q for q in qs if q['desafio']=='evidencia_apos_8192')
        ref=q['alternativas_suporte'][0][0];d=next(d for d in docs if d['registro_id']==ref['registro_id'])
        self.assertGreater(len(d['texto'][:ref['inicio']].split()),8192)
    def test_changed_heldout_query_invalidates_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=root/'avaliacao/dados/jurisprudencia';p.mkdir(parents=True)
            q=dict(query_id='reservada',pergunta='texto congelado')
            frozen=dict(perguntas_reservadas=['reservada'],conteudo_reservado_sha256={
                'reservada':adv.base.sha(json.dumps(q,sort_keys=True,ensure_ascii=False))})
            (p/'reserva_piloto_congelada.json').write_text(json.dumps(frozen),encoding='utf-8')
            self.assertEqual(pilot.freeze_guard(root,[q]),{'reservada'})
            with self.assertRaises(AssertionError):pilot.freeze_guard(root,[dict(q,pergunta='alterada')])

if __name__=='__main__':unittest.main()
