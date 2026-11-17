import unittest

from worker.evidencia.recuperador import rrf
from avaliacao import recuperacao as av


class TestRRF(unittest.TestCase):
    def test_item_presente_nas_duas_listas_fica_na_frente(self):
        ordem, escores = rrf([['a', 'b', 'c'], ['c', 'a', 'd']], k=60)
        self.assertEqual(ordem[0], 'a')
        self.assertAlmostEqual(escores['a'], 1 / 61 + 1 / 62)
        self.assertEqual(set(ordem), {'a', 'b', 'c', 'd'})

    def test_lista_vazia_nao_quebra(self):
        ordem, _ = rrf([[], ['x']])
        self.assertEqual(ordem, ['x'])


class TestRelevancia(unittest.TestCase):
    def test_artigo_e_norma_precisam_coincidir(self):
        q = dict(fonte='legislacao', norma='codigos/clt.md', artigo='Art. 4º')
        self.assertTrue(av.relevante(q, ('legislacao', 'x'), dict(caminho_relativo='codigos/clt.md', artigo_ref='Art. 4')))
        self.assertFalse(av.relevante(q, ('legislacao', 'x'), dict(caminho_relativo='codigos/cpc.md', artigo_ref='Art. 4º')))
        self.assertFalse(av.relevante(q, ('legislacao', 'x'), dict(caminho_relativo='codigos/clt.md', artigo_ref='Art. 40')))

    def test_jurisprudencia_usa_registro(self):
        q = dict(fonte='jurisprudencia', registros={'r1'})
        self.assertTrue(av.relevante(q, ('jurisprudencia', 'r1'), {}))
        self.assertFalse(av.relevante(q, ('legislacao', 'r1'), {}))


class TestCobertura(unittest.TestCase):
    def test_cobertura_parcial_e_melhor_alternativa(self):
        q = dict(alternativas=[
            [dict(registro_id='r1', campo_texto='inteiro_teor', inicio=100, fim=200)],
            [dict(registro_id='r2', campo_texto='inteiro_teor', inicio=0, fim=50)]])
        chunks = [dict(unidade='r1', metadata=dict(campo_texto='inteiro_teor', inicio=150, fim=400)),
                  dict(unidade='r2', metadata=dict(campo_texto='inteiro_teor', inicio=0, fim=60))]
        self.assertAlmostEqual(av.cobertura_suporte(q, chunks), 1.0)
        self.assertAlmostEqual(av.cobertura_suporte(q, chunks[:1]), 0.5)

    def test_sobreposicao_entre_chunks_nao_conta_duas_vezes(self):
        q = dict(alternativas=[[dict(registro_id='r1', campo_texto='inteiro_teor', inicio=0, fim=100)]])
        chunks = [dict(unidade='r1', metadata=dict(campo_texto='inteiro_teor', inicio=0, fim=80)),
                  dict(unidade='r1', metadata=dict(campo_texto='inteiro_teor', inicio=60, fim=100))]
        self.assertAlmostEqual(av.cobertura_suporte(q, chunks), 1.0)


if __name__ == '__main__':
    unittest.main()
