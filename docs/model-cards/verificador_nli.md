# Model card — verificador NLI `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` (revisão `8adb042d`) + regras de saída

- **Estágio:** em uso por fixação (`worker/modelos/em_uso.yml`, limiar `sustenta` 0,55 e sobreposição lexical 0,2); registrado no MLflow como `verificador_nli` (alias `candidato`).
- **Uso pretendido:** último portão da resposta: cada frase só é publicada se o trecho citado a **sustenta**. O julgamento é o do Agente de Validação: regras de saída (conselho, promessa, número ou prazo fora do trecho, sobreposição lexical < 0,2) e depois o NLI na melhor janela do trecho (artigo inteiro, caput e cada parágrafo/inciso com o começo do caput), com o número conferido na janela que sustentou.
- **Fora do escopo:** julgar se a resposta está completa ou é útil (isso é da avaliação com LLM como juiz, #16).
- **Dados de avaliação:** 105 pares-ouro v1 (`avaliacao/pares_ouro/verificador_v1.jsonl`: 68 sustenta, 24 contradiz, 13 não trata; 67 frases reais da bateria de 17/11 e 38 adversariais). **Rótulos em rascunho**, aguardam o aceite da Curadoria.
- **Baseline comparado:** sobreposição lexical sozinha e outros NLI multilíngues (`treino/benchmark_nli.py`).
- **Métricas (Validação completa, limiar 0,55):** precisão **0,912**, recall 0,912 — atinge o portão de precisão ≥ 0,90. Só o NLI, sem as regras: precisão 0,816. Nos adversariais a precisão cai para ~0,58: as contradições sutis escritas a partir do texto da fonte ainda passam. [Calibração](../../avaliacao/agentes/resultados/2026-11-24_calibracao_nli_E_janela_lexical_20.md).
- **Calibração:** limiar escolhido pela regra "menor limiar com precisão ≥ 0,90" **nos mesmos pares** em que é medido — o número é otimista até existir um conjunto separado de pares.
- **Erros graves encontrados:** frase contraditada pelo trecho liberada (contradição sutil de alcance, p. ex. generalizar um parágrafo que vale só para um caso).
- **Memória e latência no M4:** 279 M parâmetros, 1,5 GB; 133 ms por par, ~3 s por resposta de 10 frases (MPS). Na CPU ~7× mais lento.
- **Limitações:** pares só de legislação; poucos "não trata"; janela de 512 tokens.
- **Run do MLflow:** experimentos `benchmark_nli` e `registro_verificador_nli`.
- **Aprovação da Curadoria:** pendente (rótulos dos pares e limiar).
