CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin', 'expert')),
  status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'disabled')),
  full_name TEXT NOT NULL,
  organization TEXT,
  title TEXT,
  bio TEXT,
  allow_cross_business_review INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  approved_at TEXT,
  approved_by INTEGER,
  FOREIGN KEY (approved_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS auth_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  token TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS applications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS technical_types (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 100,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS business_tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 100,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_configs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  llm_use_case TEXT NOT NULL DEFAULT 'evaluation' CHECK(llm_use_case IN ('evaluation', 'trial')),
  provider_code TEXT NOT NULL DEFAULT 'custom_openai',
  provider_type TEXT NOT NULL CHECK(provider_type IN ('openai_compatible')),
  base_url TEXT NOT NULL,
  api_key TEXT NOT NULL,
  model_name TEXT NOT NULL,
  system_prompt TEXT,
  temperature REAL NOT NULL DEFAULT 0.2,
  max_tokens INTEGER NOT NULL DEFAULT 800,
  top_p REAL NOT NULL DEFAULT 0.95,
  is_enabled INTEGER NOT NULL DEFAULT 1,
  is_active INTEGER NOT NULL DEFAULT 0,
  is_trial_enabled INTEGER NOT NULL DEFAULT 0,
  last_tested_at TEXT,
  last_test_status TEXT CHECK(last_test_status IN ('passed', 'failed')),
  last_test_message TEXT,
  last_test_latency_ms INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS expert_applications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  expert_user_id INTEGER NOT NULL,
  application_id INTEGER NOT NULL,
  priority INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  UNIQUE(expert_user_id, application_id),
  FOREIGN KEY (expert_user_id) REFERENCES users(id),
  FOREIGN KEY (application_id) REFERENCES applications(id)
);

CREATE TABLE IF NOT EXISTS expert_business_tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  expert_user_id INTEGER NOT NULL,
  business_tag_id INTEGER NOT NULL,
  priority INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  UNIQUE(expert_user_id, business_tag_id),
  FOREIGN KEY (expert_user_id) REFERENCES users(id),
  FOREIGN KEY (business_tag_id) REFERENCES business_tags(id)
);

CREATE TABLE IF NOT EXISTS dataset_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  source TEXT,
  source_batch_name TEXT,
  external_batch_id TEXT,
  file_path TEXT,
  application_id INTEGER,
  technical_type_id INTEGER,
  business_tags_json TEXT,
  uploader_user_id INTEGER,
  parse_lock_token TEXT,
  parse_lock_acquired_at TEXT,
  self_review_status TEXT NOT NULL DEFAULT 'none' CHECK(self_review_status IN ('none', 'queued', 'pending', 'in_progress', 'submitted')),
  peer_review_status TEXT NOT NULL DEFAULT 'none' CHECK(peer_review_status IN ('none', 'queued', 'pending', 'in_progress', 'completed')),
  import_status TEXT NOT NULL CHECK(import_status IN ('uploaded', 'parsed', 'failed')),
  total_count INTEGER NOT NULL DEFAULT 0,
  success_count INTEGER NOT NULL DEFAULT 0,
  fail_count INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (created_by) REFERENCES users(id),
  FOREIGN KEY (uploader_user_id) REFERENCES users(id),
  FOREIGN KEY (application_id) REFERENCES applications(id),
  FOREIGN KEY (technical_type_id) REFERENCES technical_types(id)
);

CREATE TABLE IF NOT EXISTS dataset_batch_failures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_batch_id INTEGER NOT NULL,
  row_no INTEGER NOT NULL,
  external_id TEXT,
  question_preview TEXT,
  error_message TEXT NOT NULL,
  raw_payload_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (dataset_batch_id) REFERENCES dataset_batches(id)
);

CREATE TABLE IF NOT EXISTS qa_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT,
  technical_type_id INTEGER,
  business_tags_json TEXT,
  application_id INTEGER NOT NULL,
  dataset_batch_id INTEGER,
  question_text TEXT NOT NULL,
  context_text TEXT,
  metadata_json TEXT,
  tags_json TEXT,
  difficulty TEXT,
  source TEXT,
  source_model TEXT,
  status TEXT NOT NULL CHECK(status IN ('draft', 'active', 'in_review', 'reviewed', 'archived')),
  created_at TEXT NOT NULL,
  FOREIGN KEY (technical_type_id) REFERENCES technical_types(id),
  FOREIGN KEY (application_id) REFERENCES applications(id),
  FOREIGN KEY (dataset_batch_id) REFERENCES dataset_batches(id)
);

CREATE TABLE IF NOT EXISTS qa_answers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  qa_item_id INTEGER NOT NULL,
  answer_text TEXT NOT NULL,
  answer_type TEXT NOT NULL CHECK(answer_type IN (
    'imported_candidate',
    'llm_generated_candidate',
    'expert_confirmed_standard',
    'final_standard'
  )),
  source_model TEXT,
  source_user_id INTEGER,
  parent_answer_id INTEGER,
  version_no INTEGER NOT NULL DEFAULT 1,
  is_current INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  FOREIGN KEY (qa_item_id) REFERENCES qa_items(id),
  FOREIGN KEY (source_user_id) REFERENCES users(id),
  FOREIGN KEY (parent_answer_id) REFERENCES qa_answers(id)
);

CREATE TABLE IF NOT EXISTS evaluation_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  qa_item_id INTEGER NOT NULL,
  answer_id INTEGER NOT NULL,
  expert_user_id INTEGER NOT NULL,
  round_no INTEGER NOT NULL DEFAULT 1,
  task_type TEXT NOT NULL CHECK(task_type IN ('initial_review', 'dispute_review', 'final_confirm')),
  status TEXT NOT NULL CHECK(status IN ('pending', 'in_progress', 'submitted', 'expired', 'cancelled')),
  assigned_at TEXT NOT NULL,
  started_at TEXT,
  submitted_at TEXT,
  expires_at TEXT,
  UNIQUE(answer_id, expert_user_id, round_no, task_type),
  FOREIGN KEY (qa_item_id) REFERENCES qa_items(id),
  FOREIGN KEY (answer_id) REFERENCES qa_answers(id),
  FOREIGN KEY (expert_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS expert_task_abandons (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  qa_item_id INTEGER NOT NULL,
  answer_id INTEGER NOT NULL,
  expert_user_id INTEGER NOT NULL,
  task_type TEXT NOT NULL CHECK(task_type IN ('initial_review', 'dispute_review', 'final_confirm')),
  created_at TEXT NOT NULL,
  UNIQUE(answer_id, expert_user_id, task_type),
  FOREIGN KEY (qa_item_id) REFERENCES qa_items(id),
  FOREIGN KEY (answer_id) REFERENCES qa_answers(id),
  FOREIGN KEY (expert_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS evaluation_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL UNIQUE,
  qa_item_id INTEGER NOT NULL,
  answer_id INTEGER NOT NULL,
  expert_user_id INTEGER NOT NULL,
  correctness_rating TEXT NOT NULL CHECK(correctness_rating IN ('good', 'medium', 'bad')),
  completeness_rating TEXT NOT NULL CHECK(completeness_rating IN ('full', 'partial', 'missing')),
  relevance_rating TEXT NOT NULL CHECK(relevance_rating IN ('relevant', 'partial', 'offtopic')),
  clarity_rating TEXT NOT NULL CHECK(clarity_rating IN ('clear', 'normal', 'unclear')),
  risk_flag TEXT NOT NULL CHECK(risk_flag IN ('none', 'factual', 'compliance', 'hallucination')),
  overall_decision TEXT NOT NULL CHECK(overall_decision IN ('pass', 'rewrite', 'fail')),
  reasoning_completeness TEXT CHECK(reasoning_completeness IN ('strong', 'medium', 'weak')),
  reasoning_consistency TEXT CHECK(reasoning_consistency IN ('strong', 'medium', 'weak')),
  reasoning_support TEXT CHECK(reasoning_support IN ('strong', 'medium', 'weak')),
  quick_comment_codes TEXT,
  adopted_rewrite_answer_id INTEGER,
  created_at TEXT NOT NULL,
  FOREIGN KEY (task_id) REFERENCES evaluation_tasks(id),
  FOREIGN KEY (qa_item_id) REFERENCES qa_items(id),
  FOREIGN KEY (answer_id) REFERENCES qa_answers(id),
  FOREIGN KEY (expert_user_id) REFERENCES users(id),
  FOREIGN KEY (adopted_rewrite_answer_id) REFERENCES qa_answers(id)
);

CREATE TABLE IF NOT EXISTS llm_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL,
  qa_item_id INTEGER NOT NULL,
  answer_id INTEGER NOT NULL,
  expert_user_id INTEGER NOT NULL,
  llm_config_id INTEGER,
  llm_config_name TEXT,
  llm_model_name TEXT,
  purpose TEXT NOT NULL CHECK(purpose IN ('fact_check', 'rewrite', 'risk_check', 'compare')),
  status TEXT NOT NULL CHECK(status IN ('active', 'completed', 'failed')),
  created_at TEXT NOT NULL,
  FOREIGN KEY (task_id) REFERENCES evaluation_tasks(id),
  FOREIGN KEY (qa_item_id) REFERENCES qa_items(id),
  FOREIGN KEY (answer_id) REFERENCES qa_answers(id),
  FOREIGN KEY (expert_user_id) REFERENCES users(id),
  FOREIGN KEY (llm_config_id) REFERENCES llm_configs(id)
);

CREATE TABLE IF NOT EXISTS llm_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant')),
  content TEXT NOT NULL,
  target_answer_id INTEGER,
  generated_answer_id INTEGER,
  review_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES llm_sessions(id),
  FOREIGN KEY (target_answer_id) REFERENCES qa_answers(id),
  FOREIGN KEY (generated_answer_id) REFERENCES qa_answers(id)
);

CREATE TABLE IF NOT EXISTS model_trial_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  expert_user_id INTEGER NOT NULL,
  llm_config_id INTEGER NOT NULL,
  llm_config_name TEXT,
  llm_model_name TEXT,
  source_qa_item_id INTEGER,
  source_answer_id INTEGER,
  title TEXT,
  status TEXT NOT NULL CHECK(status IN ('active', 'completed', 'failed')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (expert_user_id) REFERENCES users(id),
  FOREIGN KEY (llm_config_id) REFERENCES llm_configs(id),
  FOREIGN KEY (source_qa_item_id) REFERENCES qa_items(id),
  FOREIGN KEY (source_answer_id) REFERENCES qa_answers(id)
);

CREATE TABLE IF NOT EXISTS model_trial_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES model_trial_sessions(id)
);

CREATE TABLE IF NOT EXISTS evaluation_drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL UNIQUE,
  qa_item_id INTEGER NOT NULL,
  answer_id INTEGER NOT NULL,
  expert_user_id INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (task_id) REFERENCES evaluation_tasks(id),
  FOREIGN KEY (qa_item_id) REFERENCES qa_items(id),
  FOREIGN KEY (answer_id) REFERENCES qa_answers(id),
  FOREIGN KEY (expert_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS qa_aggregates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  qa_item_id INTEGER NOT NULL UNIQUE,
  current_answer_id INTEGER NOT NULL,
  review_count INTEGER NOT NULL DEFAULT 0,
  avg_correctness REAL,
  avg_completeness REAL,
  avg_relevance REAL,
  avg_clarity REAL,
  agreement_score REAL,
  final_decision TEXT CHECK(final_decision IN ('pass', 'rewrite', 'fail', 'pending')),
  final_standard_answer_id INTEGER,
  aggregated_at TEXT NOT NULL,
  FOREIGN KEY (qa_item_id) REFERENCES qa_items(id),
  FOREIGN KEY (current_answer_id) REFERENCES qa_answers(id),
  FOREIGN KEY (final_standard_answer_id) REFERENCES qa_answers(id)
);

CREATE TABLE IF NOT EXISTS export_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL UNIQUE,
  export_type TEXT NOT NULL CHECK(export_type IN ('final_dataset', 'review_records', 'disputed_cases', 'sft_dataset')),
  application_id INTEGER,
  technical_type_codes_json TEXT,
  date_from TEXT,
  date_to TEXT,
  file_format TEXT NOT NULL CHECK(file_format IN ('json', 'jsonl')),
  status TEXT NOT NULL CHECK(status IN ('pending', 'processing', 'done', 'failed')),
  file_path TEXT,
  total_records INTEGER NOT NULL DEFAULT 0,
  file_size_bytes INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  created_by INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  started_at TEXT,
  completed_at TEXT,
  FOREIGN KEY (application_id) REFERENCES applications(id),
  FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS news (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  is_published INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_token ON auth_sessions(token);
CREATE INDEX IF NOT EXISTS idx_technical_types_active ON technical_types(is_active, sort_order);
CREATE INDEX IF NOT EXISTS idx_business_tags_active ON business_tags(is_active, sort_order);
CREATE INDEX IF NOT EXISTS idx_llm_configs_active ON llm_configs(is_active, id DESC);
CREATE INDEX IF NOT EXISTS idx_llm_configs_trial_enabled ON llm_configs(is_trial_enabled, is_enabled, id DESC);
CREATE INDEX IF NOT EXISTS idx_llm_configs_use_case ON llm_configs(llm_use_case, is_enabled, is_active, id DESC);
CREATE INDEX IF NOT EXISTS idx_expert_business_tags_expert ON expert_business_tags(expert_user_id, priority);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dataset_batches_source_uploader_external
  ON dataset_batches(source, uploader_user_id, external_batch_id);
CREATE INDEX IF NOT EXISTS idx_dataset_batches_parse_lock
  ON dataset_batches(import_status, parse_lock_token, parse_lock_acquired_at, id DESC);
CREATE INDEX IF NOT EXISTS idx_qa_items_app_status ON qa_items(application_id, status);
CREATE INDEX IF NOT EXISTS idx_qa_items_technical_type ON qa_items(technical_type_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_qa_items_batch_external
  ON qa_items(dataset_batch_id, external_id);
CREATE INDEX IF NOT EXISTS idx_qa_answers_item_type ON qa_answers(qa_item_id, answer_type);
CREATE INDEX IF NOT EXISTS idx_tasks_expert_status ON evaluation_tasks(expert_user_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_answer_status ON evaluation_tasks(answer_id, status);
CREATE INDEX IF NOT EXISTS idx_task_abandons_answer_expert ON expert_task_abandons(answer_id, expert_user_id);
CREATE INDEX IF NOT EXISTS idx_records_answer ON evaluation_records(answer_id);
CREATE INDEX IF NOT EXISTS idx_sessions_task ON llm_sessions(task_id);
CREATE INDEX IF NOT EXISTS idx_model_trial_sessions_expert ON model_trial_sessions(expert_user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_trial_messages_session ON model_trial_messages(session_id, id ASC);
CREATE INDEX IF NOT EXISTS idx_drafts_task ON evaluation_drafts(task_id);
CREATE INDEX IF NOT EXISTS idx_export_jobs_status ON export_jobs(status);
CREATE INDEX IF NOT EXISTS idx_batch_failures_batch ON dataset_batch_failures(dataset_batch_id, row_no);
CREATE INDEX IF NOT EXISTS idx_news_is_published ON news(is_published);
CREATE INDEX IF NOT EXISTS idx_news_created_at ON news(created_at);

CREATE TABLE IF NOT EXISTS feedbacks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'general',
  user_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_feedbacks_user_id ON feedbacks(user_id);
CREATE INDEX IF NOT EXISTS idx_feedbacks_created_at ON feedbacks(created_at);

CREATE TABLE IF NOT EXISTS model_changelogs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model_name TEXT NOT NULL,
  change_type TEXT NOT NULL CHECK(change_type IN ('added', 'updated')),
  description TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_model_changelogs_created_at ON model_changelogs(created_at);
