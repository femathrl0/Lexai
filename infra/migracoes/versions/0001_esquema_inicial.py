"""Esquema inicial: contas, consentimentos, tarefas, resultados e os dois índices.

Revision ID: 0001
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Dimensão do BGE-M3 (modelo usado no lex_clt.ai); muda por migração se o benchmark escolher outro.
DIM = 1024


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(f"""
    CREATE TABLE contas (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        email text UNIQUE NOT NULL,
        senha_hash text NOT NULL,              -- Argon2
        criada_em timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE sessoes (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        conta_id uuid NOT NULL REFERENCES contas(id) ON DELETE CASCADE,
        expira_em timestamptz NOT NULL
    );
    CREATE TABLE consentimentos (
        id bigserial PRIMARY KEY,
        conta_id uuid NOT NULL REFERENCES contas(id) ON DELETE CASCADE,
        tarefa_id text NOT NULL,
        guardar boolean NOT NULL,
        prazo_exclusao timestamptz,
        registrado_em timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE tarefas (
        id text PRIMARY KEY,
        conta_id uuid REFERENCES contas(id) ON DELETE CASCADE,
        fila text NOT NULL CHECK (fila IN ('documentos','perguntas','ingestao_juridica')),
        estado text NOT NULL DEFAULT 'na_fila',
        tentativas int NOT NULL DEFAULT 0 CHECK (tentativas <= 2),
        original_chave text,                   -- objeto no MinIO, só com opt-in
        criada_em timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE resultados (
        tarefa_id text NOT NULL REFERENCES tarefas(id) ON DELETE CASCADE,
        ordem int NOT NULL,
        evento jsonb NOT NULL,
        versoes jsonb,                         -- ids de modelos, prompt e índices (RNF03)
        PRIMARY KEY (tarefa_id, ordem)         -- reentrega não duplica (idempotência)
    );
    CREATE TABLE corpus_juridico (
        id text NOT NULL,
        versao text NOT NULL,
        estado text NOT NULL CHECK (estado IN ('candidata','em_uso','historico')),
        tipo_fonte text NOT NULL CHECK (tipo_fonte IN ('lei','sumula','oj','ementa')),
        fonte text NOT NULL,
        referencia text NOT NULL,              -- ex.: CLT art. 477; Súmula 437
        texto text NOT NULL,
        vigencia_inicio date,
        vigencia_fim date,                     -- revogado sai da busca e fica no histórico
        embedding vector({DIM}) NOT NULL,
        tsv tsvector GENERATED ALWAYS AS (to_tsvector('portuguese', texto)) STORED,
        PRIMARY KEY (id, versao)
    );
    CREATE INDEX corpus_juridico_tsv ON corpus_juridico USING gin (tsv);
    CREATE INDEX corpus_juridico_vec ON corpus_juridico USING hnsw (embedding vector_cosine_ops);
    CREATE INDEX corpus_juridico_filtro ON corpus_juridico (estado, tipo_fonte);
    CREATE TABLE trechos_usuario (
        id text NOT NULL,
        conta_id uuid NOT NULL REFERENCES contas(id) ON DELETE CASCADE,
        tarefa_id text NOT NULL REFERENCES tarefas(id) ON DELETE CASCADE,
        parte text NOT NULL,
        texto text NOT NULL,
        posicao jsonb NOT NULL,
        embedding vector({DIM}) NOT NULL,
        tsv tsvector GENERATED ALWAYS AS (to_tsvector('portuguese', texto)) STORED,
        expira_em timestamptz,                 -- sem opt-in: fim da sessão
        PRIMARY KEY (conta_id, id)
    );
    CREATE INDEX trechos_usuario_conta ON trechos_usuario (conta_id);
    CREATE INDEX trechos_usuario_tsv ON trechos_usuario USING gin (tsv);
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS trechos_usuario, corpus_juridico, resultados, tarefas, consentimentos, sessoes, contas;
    """)
