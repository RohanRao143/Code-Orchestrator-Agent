


CREATE TABLE app_context_chunks (
    context_chunk_id BIGSERIAL PRIMARY KEY,

    context_file_id INT NOT NULL
        REFERENCES app_context_files(context_file_id)
        ON DELETE CASCADE,

    chunk_index INT NOT NULL,

    start_line INT,

    end_line INT,

    content TEXT NOT NULL,

    content_hash VARCHAR(128),

    embedding vector(1536),

    metadata JSONB DEFAULT '{}'::jsonb,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(context_file_id, chunk_index)
);
