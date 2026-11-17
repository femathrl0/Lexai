# Notebooks de jurisprudência

1. [Auditoria](01_auditoria_jurisprudencia.ipynb): inventário, esquemas e diagnóstico das fontes.
2. [Análise exploratória dos dados](02_eda_jurisprudencia.ipynb): cobertura, distribuição, texto e alertas.
3. [Limpeza, estruturação e verificação automática](03_limpeza_estruturacao_jurisprudencia.ipynb): normalização, proteção de CPFs, PLN, [fontes e proveniência](03_limpeza_estruturacao_jurisprudencia.ipynb#fontes-proveniencia), [verificações automáticas](03_limpeza_estruturacao_jurisprudencia.ipynb#verificacao-automatica), relações e validação final.
4. [Chunking e suporte decisório](04_experimentos_chunking_jurisprudencia.ipynb): três bases e três híbridas, suporte contínuo por intervalos, budgets iguais, testes de integridade, bootstrap pareado, diagnóstico de falhas e separação prospectiva entre ajuste e teste final. Consulte o [protocolo avançado](../../docs/avaliacao_chunking_avancada.md).


5. [Chunking definitivo](05_chunking_definitivo_jurisprudencia.ipynb): aplicação da janela de 500 tokens com 100 de sobreposição a um recorte de indexação de 20.000 documentos dos candidatos consolidados do notebook 03 (amostra estratificada que inclui os 187 documentos dos experimentos; 303.257 chunks), em lotes retomáveis, com vínculos documentais, verificação de integridade e manifesto versionado. O painel distingue progresso parcial de corpus integral validado; embeddings e pgvector são etapas seguintes.

6. [Embeddings e indexação](06_embeddings_indexacao_jurisprudencia.ipynb): vetores BGE-M3 dos 303.257 chunks do recorte de indexação, calculados na GPU do Kaggle em FP16 e gravados em float32, conferidos por hash, norma e mapeamento e importados localmente. A coleção fica no pgvector, no schema `lex_jurisprudencia`, no mesmo banco da legislação, sem alterar as tabelas dela.

As células Markdown atuais são a referência editorial. Atualizações de código e resultados devem preservar seus textos, títulos e organização, conforme [AGENTS.md](AGENTS.md).
