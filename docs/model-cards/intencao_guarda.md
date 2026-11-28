# Model card — intenção da guarda de entrada (regras)

- **Estágio:** em uso (`worker/evidencia/guardas.verificar_entrada`, dono: Eng. de IA).
- **Uso pretendido:** decidir se a pergunta é respondida, encaminhada (caso concreto), recusada (consulta individual, fora do escopo, outra jurisdição) ou tratada como institucional, **antes** de chamar a LLM.
- **Métricas:** 35 casos reais (guardas + demo): F1 1,00, 0 erro grave. Rascunho por molde (486 casos, 30% de teste): F1 0,91, 1 erro grave. O TF-IDF de caracteres + LR treinado no rascunho não generaliza (F1 0,56 nos reais). [Relatório](../../treino/relatorios/intencao.md).
- **Erro grave:** caso concreto ou consulta individual tratado como pergunta informativa.
- **Limitações:** rascunho com rótulo de molde (aguarda aceite); paráfrases com erro de digitação são onde as regras erram.
- **Aprovação da Curadoria:** pendente.
