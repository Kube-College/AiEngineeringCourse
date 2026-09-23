PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS workflows (
  repo TEXT NOT NULL, issue_number INTEGER NOT NULL, revision TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0,
  approval_revision TEXT, reason TEXT, resume_state TEXT,
  validation_profile TEXT, candidate_sha TEXT, published_sha TEXT, pr_url TEXT,
  review_cycles INTEGER NOT NULL DEFAULT 0,
  stop_requested TEXT, budget_limit INTEGER NOT NULL DEFAULT 5000000,
  PRIMARY KEY (repo, issue_number)
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, repo TEXT NOT NULL, issue_number INTEGER NOT NULL,
  kind TEXT NOT NULL, revision TEXT NOT NULL, actor TEXT NOT NULL,
  payload_json TEXT NOT NULL, canonical_json TEXT NOT NULL, outcome TEXT NOT NULL DEFAULT 'recorded',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dispatches (
  id TEXT PRIMARY KEY, repo TEXT NOT NULL, issue_number INTEGER NOT NULL,
  revision TEXT NOT NULL, role TEXT NOT NULL, attempt INTEGER NOT NULL,
  workspace_id TEXT NOT NULL, conversation_id TEXT, candidate_sha TEXT,
  deadline TEXT NOT NULL, status TEXT NOT NULL, request_hash TEXT,
  result_json TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(repo, issue_number) REFERENCES workflows(repo, issue_number),
  UNIQUE(repo, issue_number, revision, role, attempt)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_dispatch
  ON dispatches((1)) WHERE status IN ('intent', 'retryable', 'created', 'running', 'uncertain', 'stopping');
CREATE TABLE IF NOT EXISTS workspaces (
  id TEXT PRIMARY KEY, repo TEXT NOT NULL, issue_number INTEGER NOT NULL,
  status TEXT NOT NULL, container_id TEXT, image_digest TEXT, storage_id TEXT,
  base_sha TEXT, completed_at TEXT,
  FOREIGN KEY(repo, issue_number) REFERENCES workflows(repo, issue_number)
);
CREATE TABLE IF NOT EXISTS usage (
  repo TEXT NOT NULL, issue_number INTEGER NOT NULL, request_id TEXT NOT NULL,
  dispatch_id TEXT, reserved_microusd INTEGER NOT NULL,
  actual_microusd INTEGER, status TEXT NOT NULL, reported_microusd INTEGER,
  PRIMARY KEY(repo, issue_number, request_id),
  FOREIGN KEY(repo, issue_number) REFERENCES workflows(repo, issue_number)
);
CREATE TABLE IF NOT EXISTS validations (
  id INTEGER PRIMARY KEY, repo TEXT NOT NULL, issue_number INTEGER NOT NULL,
  candidate_sha TEXT NOT NULL, profile TEXT NOT NULL, passed INTEGER NOT NULL,
  evidence_dir TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(repo, issue_number) REFERENCES workflows(repo, issue_number)
);
CREATE TABLE IF NOT EXISTS publications (
  id INTEGER PRIMARY KEY, repo TEXT NOT NULL, issue_number INTEGER NOT NULL,
  candidate_sha TEXT NOT NULL, status TEXT NOT NULL, pr_url TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(repo, issue_number) REFERENCES workflows(repo, issue_number)
);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
