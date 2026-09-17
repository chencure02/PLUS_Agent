CREATE TABLE IF NOT EXISTS simulation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT '',
    thread_id TEXT NOT NULL DEFAULT '',
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
    user_id TEXT NOT NULL DEFAULT '',
    thread_id TEXT NOT NULL DEFAULT '',
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
    user_id TEXT NOT NULL DEFAULT '',
    thread_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL,
    title TEXT,
    summary TEXT,
    messages_json TEXT,
    key_decisions_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_summaries_session_created ON conversation_summaries(session_id, created_at);

CREATE TABLE IF NOT EXISTS workflow_states (
    thread_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    status TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_workflow_states_status ON workflow_states(status, updated_at);

CREATE TABLE IF NOT EXISTS workflow_runs (
    workflow_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    thread_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    target_year INTEGER,
    state_json TEXT NOT NULL,
    artifacts_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_user_thread ON workflow_runs(user_id, thread_id, updated_at);

CREATE TABLE IF NOT EXISTS memory_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT '',
    thread_id TEXT NOT NULL DEFAULT '',
    workflow_id TEXT,
    run_id INTEGER,
    step_name TEXT,
    artifact_key TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    path TEXT,
    value_json TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memory_artifacts_user_thread ON memory_artifacts(user_id, thread_id, created_at);
