"""Six domain tables and the fixed embedding contract."""

import json
from alembic import op
from sqlalchemy import text
from rag.config import Settings

revision = "0001_knowledge"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    dimension = Settings().embedding_dimension
    connection.exec_driver_sql(f"""
    CREATE TABLE devices (
      id uuid PRIMARY KEY, name varchar(200) NOT NULL, model varchar(200) NOT NULL,
      manufacturer varchar(200) NOT NULL, description text NOT NULL, metadata jsonb NOT NULL DEFAULT '{{}}',
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
    CREATE UNIQUE INDEX devices_identity ON devices(lower(name),lower(model),lower(manufacturer));
    CREATE INDEX devices_model ON devices(model);
    CREATE INDEX devices_manufacturer ON devices(manufacturer);
    CREATE TABLE issues (
      id uuid PRIMARY KEY, device_id uuid NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
      title varchar(300) NOT NULL, category varchar(100) NOT NULL, symptoms text NOT NULL,
      possible_cause text NOT NULL, description text NOT NULL, embedding vector({dimension}) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT issues_device_title UNIQUE(device_id,title));
    CREATE INDEX ix_issues_device_id ON issues(device_id);
    CREATE INDEX issues_category ON issues(category);
    CREATE TABLE documents (
      id uuid PRIMARY KEY, title varchar(300) NOT NULL, document_type varchar(100) NOT NULL,
      file_path text NOT NULL, version varchar(100) NOT NULL, status varchar(20) NOT NULL,
      metadata jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT documents_status_valid CHECK(status IN ('uploaded','processing','ready','failed')));
    CREATE INDEX ix_documents_status ON documents(status);
    CREATE INDEX documents_type ON documents(document_type);
    CREATE TABLE device_documents (
      device_id uuid NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
      document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
      PRIMARY KEY(device_id,document_id));
    CREATE INDEX device_documents_document ON device_documents(document_id);
    CREATE TABLE document_chunks (
      id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
      content text NOT NULL, embedding vector({dimension}) NOT NULL, section_heading text,
      section_path text, page_number integer, chunk_index integer NOT NULL, metadata jsonb NOT NULL,
      CONSTRAINT document_chunks_order UNIQUE(document_id,chunk_index),
      CONSTRAINT document_chunks_index_valid CHECK(chunk_index >= 0),
      CONSTRAINT document_chunks_page_valid CHECK(page_number IS NULL OR page_number > 0));
    CREATE INDEX ix_document_chunks_document_id ON document_chunks(document_id);
    CREATE TABLE issue_evidence (
      issue_id uuid NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
      chunk_id uuid NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
      evidence_type varchar(40) NOT NULL, PRIMARY KEY(issue_id,chunk_id),
      CONSTRAINT issue_evidence_type_valid CHECK(evidence_type IN
        ('possible_cause','diagnostic_procedure','resolution','supporting_observation')));
    CREATE INDEX issue_evidence_chunk ON issue_evidence(chunk_id);
    """)
    contract = json.dumps({"embedding_contract": Settings().embedding_contract})
    # Values are operator configuration; quote as SQL literals, never interpolate secrets.
    literal = "'" + contract.replace("'", "''") + "'"
    connection.execute(text(f"COMMENT ON TABLE issues IS {literal}"))
    connection.execute(text(f"COMMENT ON TABLE document_chunks IS {literal}"))
    for table in ["issues", "document_chunks"]:
        connection.execute(
            text(f"CREATE INDEX {table}_embedding_hnsw ON {table} USING hnsw (embedding vector_cosine_ops)")
        )
    connection.execute(
        text(
            "CREATE INDEX documents_content_version ON documents ((metadata->'_source'->>'sha256'), version)"
        )
    )
    connection.execute(
        text(
            "CREATE UNIQUE INDEX documents_upload_identity ON documents "
            "((metadata->'_source'->>'sha256'), lower(title), lower(document_type), version)"
        )
    )
    connection.execute(
        text("CREATE INDEX chunks_fts ON document_chunks USING gin (to_tsvector('english', content))")
    )
    connection.execute(
        text(
            "CREATE INDEX issues_fts ON issues USING gin "
            "(to_tsvector('english', title || ' ' || symptoms || ' ' || possible_cause || ' ' || description))"
        )
    )


def downgrade():
    for table in ["issue_evidence", "document_chunks", "device_documents", "documents", "issues", "devices"]:
        op.drop_table(table)
    # Do not remove a shared database extension.
