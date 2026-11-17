import unittest

from avaliacao import juiz


class TestJuiz(unittest.TestCase):
    def test_entrada_inclui_fontes_referencia_e_resposta(self):
        fontes = [dict(fonte='legislacao', caminho_relativo='codigos/clt.md', artigo_ref='Art. 73', conteudo='Art. 73. ... 20%'),
                  dict(fonte='jurisprudencia', tribunal='TRT-2', processo='0001-00.2020.5.02.0001', conteudo='Ementa ...')]
        texto = juiz.montar_entrada('Qual o adicional noturno?', 'responder', fontes, 'É de 20% [Fonte 1].', 'Pelo menos 20%.')
        for trecho in ('[Fonte 1] Legislação — codigos/clt.md Art. 73', '[Fonte 2] Jurisprudência — TRT-2',
                       'RESPOSTA DE REFERÊNCIA', 'RESPOSTA A AVALIAR:\nÉ de 20% [Fonte 1].'):
            self.assertIn(trecho, texto)

    def test_sem_referencia_nao_inclui_bloco(self):
        self.assertNotIn('REFERÊNCIA', juiz.montar_entrada('p', 'responder', [], 'r'))

    def test_validacao_do_json(self):
        valido = dict(afirmacoes=[], fidelidade=2, correcao=None, comportamento=2, clareza=2, jurisprudencia_pertinente=[],
                      veredito='aprovada', justificativa='ok')
        self.assertEqual(juiz._validar(dict(valido)), valido)
        with self.assertRaises(ValueError):
            juiz._validar(dict(valido, veredito='talvez'))
        with self.assertRaises(ValueError):
            juiz._validar({k: v for k, v in valido.items() if k != 'fidelidade'})


if __name__ == '__main__':
    unittest.main()
