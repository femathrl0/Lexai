"""Controles autorais adversariais: não são acórdãos nem perguntas do teste final."""
from pathlib import Path
import pandas as pd
from . import audit,chunking,chunking_suporte as base,chunking_avancado as adv

def cases():
    docs,questions=base.controlled_cases()
    for q in questions:
        d=next(d for d in docs if d['registro_id']==q['alternativas_suporte'][0][0]['registro_id'])
        q['alternativas_suporte']=[[adv.original_reference(d,g[0]['inicio'],g[0]['fim'])] for g in q['alternativas_suporte']]
        q['desafio']='controle_basico'
    designs=[
      ('Epsilon','precedente_citado_oposto',
       'A parte cita decisão de outro processo: "Foram deferidas horas extras". A citação não é o resultado deste julgamento.',
       ['Neste julgamento Epsilon, o recurso de horas extras é deserto. Não se examina o mérito do pedido.'],
       'Não conhecer do recurso de horas extras por deserção.'),
      ('Zeta','negacao_e_pedido',
       'A parte insiste: horas extras devidas, horas extras deferidas, condenação em horas extras.',
       ['No caso Zeta, não ficou comprovada a sobrejornada. O tribunal rejeita o pedido de horas extras; não há condenação neste tema.'],
       'Negar provimento ao recurso sobre horas extras.'),
      ('Eta','dois_temas_dispositivo_parcial',
       'O recurso pede horas extras e indenização por dano moral. A parte narra jornadas extensas.',
       ['No caso Eta, o capítulo de horas extras não supera a admissibilidade. Só o dano moral tem exame de mérito e é acolhido.'],
       'Não conhecer do capítulo de horas extras e dar provimento somente quanto ao dano moral.'),
      ('Theta','regime_temporal',
       'A parte invoca o pagamento integral do intervalo em qualquer período, inclusive depois da mudança normativa.',
       ['No caso Theta, o período examinado termina antes da mudança normativa. Por esse recorte, concede-se a hora integral; não se decide sobre o período posterior.'],
       'Dar provimento quanto à hora integral no período anterior à mudança normativa.'),
      ('Iota','evidencias_separadas',
       'O pedido trata de horas extras e de prescrição. As alegações não são o julgamento.',
       ['No caso Iota, a pretensão relativa ao primeiro período está prescrita.',
        'No caso Iota, o segundo período não está prescrito, mas a prova demonstra jornada regular: horas extras indeferidas.'],
       'Reconhecer prescrição do primeiro período e rejeitar horas extras do segundo período.'),
      ('Kappa','fronteira_janela',
       'A parte relata horas extras repetidamente. O relato não contém a solução.',
       ['No caso Kappa, os cartões foram invalidados por uniformidade e a prova testemunhal confirmou a jornada excedente. Por essa combinação de provas, são deferidas horas extras no período delimitado.'],
       'Dar provimento para deferir horas extras segundo a prova e o período delimitado.'),
      ('Lambda','evidencia_apos_8192',
       'A parte relata horas extras, mas o relato não decide o recurso.',
       ['No caso Lambda, a conclusão própria do tribunal é não conhecer do recurso por intempestividade, sem apreciação do mérito de horas extras.'],
       'Não conhecer do recurso por intempestividade.'),
      ('Mu','secao_irregular_e_transcricao',
       'Cópia do recurso da parte: "Requer-se deferimento das horas extras". Transcrição não equivale a decisão.',
       ['No caso Mu, embora o título esteja ausente, este parágrafo contém o fundamento próprio: o pedido de horas extras é rejeitado por prova de pagamento integral.'],
       'Negar provimento ao pedido de horas extras porque houve pagamento integral.')]
    for name,challenge,report,reasons,decision in designs:
        padding=('Registro narrativo sem conclusão judicial. '*100) if name=='Kappa' else ''
        long=('Contexto documental neutro sem decisão. '*2000) if name=='Lambda' else ''
        text=f'CASO FICTÍCIO {name.upper()}\n\nRELATÓRIO\n\n'+(report+'\n\n')*5
        text+=('FUNDAMENTAÇÃO\n\n' if name!='Mu' else 'Observações do julgamento\n\n')
        passages=[]
        for i,reason in enumerate(reasons):
            text+=padding+long+reason+'\n\n';passages.append(reason)
            if name=='Iota' and i==0:text+='Comentário lateral sobre despesas processuais sem efeito no mérito. '*250+'\n\n'
        text+='DISPOSITIVO\n\n'+decision
        ident='dificil_'+name.casefold();d=dict(registro_id=ident,texto=text,arquivo_id='controle_autoral',tribunal='FICTICIO',
            split_proposto='controle_sintetico',grupo_avaliacao=ident,texto_principal_campo='inteiro_teor',
            parent_arquivo='controles_autorais_dificeis',parent_sha256=base.sha(text))
        refs=[adv.original_reference(d,text.index(p),text.index(p)+len(p),'fundamentacao') for p in passages]
        # Fundamento E dispositivo são obrigatórios. Um dispositivo genérico não substitui o fundamento.
        a=text.index(decision,text.index('DISPOSITIVO'))
        refs.append(adv.original_reference(d,a,a+len(decision),'dispositivo'))
        questions.append(dict(query_id='controle_dificil_'+name.casefold(),
            pergunta=f'No caso fictício {name}, o que o próprio tribunal decidiu sobre horas extras ou intervalo, em qual período e houve exame do mérito?',
            origem='sintetica_autoral',desafio=challenge,alternativas_suporte=[refs]))
        docs.append(d)
    return docs,questions

def run(root,tokenizer=None):
    root=Path(root)
    if tokenizer is None:
        from transformers import AutoTokenizer
        tokenizer=AutoTokenizer.from_pretrained('BAAI/bge-m3',local_files_only=True)
    docs,questions=cases();documents={d['registro_id']:d for d in docs};base.validate_questions(questions,documents)
    records=[];checks=[]
    for version in adv.TITLES:
        units=[r for d in docs for r in adv.build_chunks(d,version,tokenizer)]
        checks.append(dict(versao=version,**adv.unit_audit(units,documents,tokenizer)))
        search=base.BM25(units)
        for q in questions:
            ranking=search.search(q['pergunta'],50)
            for budget in adv.BUDGETS:
                selected,used,cuts=adv.context_at_budget(ranking,documents,tokenizer,budget)
                records.append(dict(query_id=q['query_id'],desafio=q['desafio'],versao=version,
                    orcamento=budget,cobertura=adv.support_fraction(q,selected),tokens=used,cortes=cuts))
    identity=base.sha(Path(__file__).read_text(encoding='utf-8')+base.sha(tokenizer.backend_tokenizer.to_str()))
    report=root/'dados/relatorios/jurisprudencia/controles_dificeis'/identity;report.mkdir(parents=True,exist_ok=True)
    audit.write_json(report/'casos_autorais.json',dict(documentos=docs,perguntas=questions))
    audit.write_json(report/'auditoria.json',checks)
    frame=pd.DataFrame(records);frame.to_csv(report/'cobertura.csv',index=False)
    audit.write_json(report/'resumo.json',dict(casos=len(docs),perguntas=len(questions),casos_novos=8,
        recuperador='BM25; testes estruturais do chunking; encoder não executado neste controle',
        isolamento='Separado do gabarito real, do corpus do piloto e das sete perguntas reservadas.',
        controle_encoder='O caso Lambda permite verificar perda simulada acima de 8192; a medição real do encoder consta do piloto BGE.',
        codigo_sha256=audit.hash_file(__file__)))
    audit.write_json(root/'dados/relatorios/jurisprudencia/controles_dificeis/ativa.json',dict(pasta_relatorios=str(report.relative_to(root))))
    return frame,report
