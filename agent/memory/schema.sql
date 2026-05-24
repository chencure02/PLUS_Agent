CREATE TABLE IF NOT EXISTS simulation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    workflow_json TEXT,
    params_json TEXT,
    output_paths_json TEXT,
    status TEXT DEFAULT 'running',
    error_message TEXT,
    duration_seconds REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES simulation_runs(id),
    tool_name TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    params_json TEXT,
    tmp_content TEXT,
    output_paths_json TEXT,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    UNIQUE(run_id, step_order)
);

CREATE INDEX IF NOT EXISTS idx_run_steps_run_order ON run_steps(run_id, step_order);

CREATE TABLE IF NOT EXISTS user_preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    summary TEXT,
    key_decisions_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_summaries_session_created ON conversation_summaries(session_id, created_at);
