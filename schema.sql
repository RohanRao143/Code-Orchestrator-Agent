-- ALTER TABLE app_context_symbols
-- ADD COLUMN IF NOT EXISTS qualified_name TEXT,
-- ADD COLUMN IF NOT EXISTS parent_symbol_id BIGINT
--     REFERENCES app_context_symbols(symbol_id)
--     ON DELETE CASCADE,
-- ADD COLUMN IF NOT EXISTS signature_hash VARCHAR(128);



-- ALTER TABLE app_context_dependencies
-- ADD COLUMN IF NOT EXISTS source_symbol_id BIGINT
--     REFERENCES app_context_symbols(symbol_id)
--     ON DELETE CASCADE,
-- ADD COLUMN IF NOT EXISTS target_symbol_id BIGINT
--     REFERENCES app_context_symbols(symbol_id)
--     ON DELETE CASCADE;





-- CREATE INDEX IF NOT EXISTS idx_context_symbols_file
-- ON app_context_symbols(context_file_id);

-- CREATE INDEX IF NOT EXISTS idx_context_symbols_name
-- ON app_context_symbols(symbol_name);

-- CREATE INDEX IF NOT EXISTS idx_context_symbols_qualified_name
-- ON app_context_symbols(qualified_name);

-- CREATE INDEX IF NOT EXISTS idx_context_symbols_parent
-- ON app_context_symbols(parent_symbol_id);

-- CREATE INDEX IF NOT EXISTS idx_context_dependencies_source_file
-- ON app_context_dependencies(source_file_id);

-- CREATE INDEX IF NOT EXISTS idx_context_dependencies_target_file
-- ON app_context_dependencies(target_file_id);

-- CREATE INDEX IF NOT EXISTS idx_context_dependencies_source_symbol
-- ON app_context_dependencies(source_symbol_id);

-- CREATE INDEX IF NOT EXISTS idx_context_dependencies_target_symbol
-- ON app_context_dependencies(target_symbol_id);

-- CREATE INDEX IF NOT EXISTS idx_context_dependencies_type
-- ON app_context_dependencies(dependency_type);



-- ALTER TABLE app_context_chunks
-- ADD COLUMN IF NOT EXISTS primary_symbol_id BIGINT
--     REFERENCES app_context_symbols(symbol_id)
--     ON DELETE SET NULL;

-- ALTER TABLE app_context_symbols
-- ADD COLUMN IF NOT EXISTS signature TEXT;

-- ALTER TABLE app_context_dependencies
-- ADD COLUMN IF NOT EXISTS target_file_id BIGINT
--     REFERENCES app_context_files(context_file_id)
--     ON DELETE CASCADE;

-- ALTER TABLE app_context_dependencies
-- ADD COLUMN IF NOT EXISTS target_file_id BIGINT
--     REFERENCES app_context_files(context_file_id)
--     ON DELETE CASCADE;


-- ============================================================
-- APP CONTEXT SNAPSHOTS
-- ============================================================
-- Stores immutable indexing snapshots for a project.
--
-- A snapshot represents the state of the indexed repository at
-- a particular point in time.
-- ============================================================

-- CREATE TABLE IF NOT EXISTS app_context_snapshots (
--     snapshot_id BIGSERIAL PRIMARY KEY,

--     context_project_id INT NOT NULL
--         REFERENCES app_context_projects(context_project_id)
--         ON DELETE CASCADE,

--     snapshot_hash VARCHAR(128) NOT NULL,

--     file_count INT NOT NULL DEFAULT 0,

--     created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

--     CONSTRAINT uq_context_snapshot_project_hash
--         UNIQUE (
--             context_project_id,
--             snapshot_hash
--         )
-- );


-- ============================================================
-- INDEXES
-- ============================================================

-- CREATE INDEX IF NOT EXISTS idx_context_snapshots_project
-- ON app_context_snapshots(context_project_id);

-- CREATE INDEX IF NOT EXISTS idx_context_snapshots_created
-- ON app_context_snapshots(created_at DESC);

-- CREATE INDEX IF NOT EXISTS idx_context_snapshots_project_created
-- ON app_context_snapshots(
--     context_project_id,
--     created_at DESC
-- );


-- ============================================================
-- OPTIONAL: LATEST SNAPSHOT HELPER VIEW
-- ============================================================

-- CREATE OR REPLACE VIEW latest_app_context_snapshots AS
-- SELECT DISTINCT ON (context_project_id)
--     snapshot_id,
--     context_project_id,
--     snapshot_hash,
--     file_count,
--     created_at
-- FROM app_context_snapshots
-- ORDER BY
--     context_project_id,
--     created_at DESC;



ALTER TABLE agent_tasks
ADD COLUMN IF NOT EXISTS 
change_type VARCHAR(50) DEFAULT 'edit'