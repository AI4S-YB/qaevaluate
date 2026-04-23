export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8100";

type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
};

export function getStoredAuthToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const token = window.localStorage.getItem("qaevaluate.auth");
  if (!token) {
    return null;
  }
  try {
    return (JSON.parse(token) as { token?: string }).token ?? null;
  } catch {
    return null;
  }
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const parsedToken = getStoredAuthToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(parsedToken ? { Authorization: `Bearer ${parsedToken}` } : {}),
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });

  if (!response.ok) {
    const text = await response.text();
    try {
      const parsed = JSON.parse(text) as { detail?: string };
      throw new Error(parsed.detail || text || `request failed: ${response.status}`);
    } catch {
      throw new Error(text || `request failed: ${response.status}`);
    }
  }

  const payload = (await response.json()) as ApiEnvelope<T>;
  return payload.data;
}

export type ExpertTaskListItem = {
  id: number;
  qa_item_id: number;
  answer_id: number;
  task_type: "initial_review" | "dispute_review" | "final_confirm";
  status: "pending" | "in_progress" | "submitted" | "expired" | "cancelled";
  assigned_at: string;
  expires_at: string | null;
  application_name: string;
  business_tags_json: string | null;
  metadata_json: string | null;
  technical_type_code: string | null;
  technical_type_name: string | null;
  question_summary: string;
};

export type ExpertHistoryItem = {
  id: number;
  task_id: number;
  qa_item_id: number;
  answer_id: number;
  correctness_rating: string;
  completeness_rating: string;
  relevance_rating: string;
  clarity_rating: string;
  risk_flag: string;
  overall_decision: "pass" | "rewrite" | "fail";
  quick_comment_codes: string[];
  adopted_rewrite_answer_id: number | null;
  adopted_rewrite_answer_text: string | null;
  submitted_at: string;
  task_type: "initial_review" | "dispute_review" | "final_confirm";
  question_text: string;
  question_summary: string;
  application_name: string;
  aggregate_final_decision: "pass" | "rewrite" | "fail" | "pending" | null;
  agreement_score: number | null;
  review_count: number | null;
  final_standard_answer_id: number | null;
  final_standard_answer_text: string | null;
  llm_session_count: number;
  adopted_became_final: boolean;
};

export type TaskDetail = {
  task: {
    id: number;
    qa_item_id: number;
    answer_id: number;
    task_type: "initial_review" | "dispute_review" | "final_confirm";
    status: "pending" | "in_progress" | "submitted" | "expired" | "cancelled";
    assigned_at: string;
    started_at: string | null;
    submitted_at: string | null;
  };
  qa_item: {
    id: number;
    application_name: string;
    question_text: string;
    context_text: string | null;
    tags_json: string | null;
    business_tags_json: string | null;
    metadata_json: string | null;
    technical_type_code: string | null;
    technical_type_name: string | null;
    source: string | null;
  };
  current_answer: {
    id: number;
    answer_text: string;
    answer_type: string;
    source_model: string | null;
    version_no: number;
  };
  candidate_answers: Array<{
    id: number;
    answer_text: string;
    answer_type: string;
    source_model: string | null;
    parent_answer_id: number | null;
    version_no: number;
    created_at: string;
  }>;
  llm_sessions: Array<{
    id: number;
    purpose: string;
    status: string;
    created_at: string;
    llm_config_id: number | null;
    llm_config_name: string | null;
    llm_model_name: string | null;
  }>;
  draft: unknown;
  submitted_record: TaskDraft | null;
};

export type TaskDraft = {
  payload: {
    correctness_rating?: string | null;
    completeness_rating?: string | null;
    relevance_rating?: string | null;
    clarity_rating?: string | null;
    risk_flag?: string | null;
    reasoning_completeness?: string | null;
    reasoning_consistency?: string | null;
    reasoning_support?: string | null;
    overall_decision?: string | null;
    quick_comment_codes?: string[];
    adopted_rewrite_answer_id?: number | null;
    adopted_rewrite_answer_text?: string | null;
  };
  updated_at: string;
};

export type ExpertUser = {
  id: number;
  username: string;
  full_name: string;
  organization: string | null;
  title: string | null;
  status: "pending" | "approved" | "rejected" | "disabled";
  created_at: string;
  allow_cross_business_review: boolean;
  applications: Array<{
    id: number;
    name: string;
  }>;
  business_tags: Array<{
    id: number;
    name: string;
  }>;
};

export type ImportBatch = {
  id: number;
  name: string;
  source: string | null;
  source_batch_name: string | null;
  external_batch_id: string | null;
  file_path: string | null;
  import_status: "uploaded" | "parsed" | "failed";
  application_id: number | null;
  application_name: string | null;
  uploader_user_id: number | null;
  uploader_username: string | null;
  uploader_full_name: string | null;
  business_tags_json: string | null;
  technical_type_code: string | null;
  technical_type_name: string | null;
  total_count: number;
  success_count: number;
  fail_count: number;
  created_at: string;
};

export type ImportFailure = {
  id: number;
  row_no: number;
  external_id: string | null;
  question_preview: string | null;
  error_message: string;
  raw_payload_json: string | null;
  created_at: string;
};

export type ImportFailureDetail = {
  batch: {
    id: number;
    name: string;
    import_status: "uploaded" | "parsed" | "failed";
    application_id: number | null;
    application_name: string | null;
    source_batch_name: string | null;
    external_batch_id: string | null;
    uploader_user_id: number | null;
    uploader_username: string | null;
    uploader_full_name: string | null;
    business_tags_json: string | null;
    technical_type_code: string | null;
    technical_type_name: string | null;
    total_count: number;
    success_count: number;
    fail_count: number;
  };
  failures: ImportFailure[];
};

export type AdminImportBatchDetail = {
  batch: {
    id: number;
    name: string;
    source: string | null;
    source_batch_name: string | null;
    external_batch_id: string | null;
    file_path: string | null;
    import_status: "uploaded" | "parsed" | "failed";
    application_id: number | null;
    application_name: string | null;
    uploader_user_id: number | null;
    uploader_username: string | null;
    uploader_full_name: string | null;
    business_tags_json: string | null;
    technical_type_code: string | null;
    technical_type_name: string | null;
    total_count: number;
    success_count: number;
    fail_count: number;
    self_review_status: "none" | "queued" | "pending" | "in_progress" | "submitted";
    peer_review_status: "none" | "queued" | "pending" | "in_progress" | "completed";
    created_at: string;
  };
  failures: ImportFailure[];
  items: Array<{
    id: number;
    external_id: string | null;
    status: string;
    question_text: string;
    question_summary: string;
    context_text: string | null;
    source: string | null;
    source_model: string | null;
    metadata_json: string | null;
    current_answer_id: number | null;
    current_answer_text: string | null;
    review_task_total: number;
    review_task_submitted: number;
  }>;
};

export type ExpertImportBatch = {
  id: number;
  name: string;
  source: string | null;
  source_batch_name: string | null;
  external_batch_id: string | null;
  file_path: string | null;
  import_status: "uploaded" | "parsed" | "failed";
  application_id: number | null;
  application_name: string | null;
  business_tags_json: string | null;
  technical_type_code: string | null;
  technical_type_name: string | null;
  uploader_user_id: number | null;
  total_count: number;
  success_count: number;
  fail_count: number;
  self_review_status: "none" | "queued" | "pending" | "in_progress" | "submitted";
  peer_review_status: "none" | "queued" | "pending" | "in_progress" | "completed";
  self_review_total: number;
  self_review_submitted: number;
  peer_review_total: number;
  peer_review_submitted: number;
  created_at: string;
};

export type ExpertImportBatchDetail = {
  batch: Omit<
    ExpertImportBatch,
    "self_review_total" | "self_review_submitted" | "peer_review_total" | "peer_review_submitted"
  >;
  failures: ImportFailure[];
  items: Array<{
    id: number;
    external_id: string | null;
    status: string;
    question_text: string;
    question_summary: string;
    source: string | null;
    source_model: string | null;
    metadata_json: string | null;
    current_answer_id: number | null;
    current_answer_text: string | null;
    self_review_task_status: string | null;
    peer_review_total: number;
    peer_review_submitted: number;
  }>;
};

export type ExpertImportPushPayload = {
  name: string;
  source: string;
  source_batch_name?: string;
  external_batch_id?: string;
  application_id: number;
  technical_type_code: string;
  business_tag_codes: string[];
  rows: Array<{
    id?: string;
    question: string;
    answer?: string;
    context?: string;
    difficulty?: string;
    source?: string;
    model?: string;
    metadata?: Record<string, unknown>;
    candidate_answers?: Array<{
      answer: string;
    }>;
  }>;
  auto_parse?: boolean;
  create_self_review?: boolean;
};

export type ApplicationItem = {
  id: number;
  name: string;
  description: string | null;
  is_active: number;
  created_at: string;
};

export type AdminApplicationItem = ApplicationItem & {
  total_qas: number;
  reviewed_qas: number;
  pending_aggregate_qas: number;
  closed_qas: number;
  expert_count: number;
};

export type AdminApplicationBusinessTagItem = {
  id: number;
  code: string;
  name: string;
  qa_count: number;
  reviewed_qas: number;
  closed_qas: number;
  expert_count: number;
};

export type QaListItem = {
  id: number;
  external_id: string | null;
  status: string;
  application_name: string;
  business_tags_json: string | null;
  metadata_json: string | null;
  technical_type_code: string | null;
  technical_type_name: string | null;
  review_count: number | null;
  final_decision: string | null;
  agreement_score: number | null;
  current_answer_id: number | null;
  final_standard_answer_id: number | null;
  question_summary: string;
};

export type QaDetail = {
  qa_item: {
    id: number;
    external_id: string | null;
    question_text: string;
    source: string | null;
    status: string;
    application_name: string;
    business_tags_json?: string | null;
    metadata_json?: string | null;
    technical_type_code?: string | null;
    technical_type_name?: string | null;
  };
  answers: Array<{
    id: number;
    answer_text: string;
    answer_type: string;
    source_model: string | null;
    version_no: number;
    created_at: string;
  }>;
  tasks: Array<{
    id: number;
    expert_user_id: number;
    task_type: string;
    status: string;
    assigned_at: string;
    submitted_at: string | null;
  }>;
  records: Array<{
    id: number;
    expert_user_id: number;
    overall_decision: string;
    correctness_rating: string;
    completeness_rating: string;
    relevance_rating: string;
    clarity_rating: string;
    risk_flag: string;
    reasoning_completeness?: string | null;
    reasoning_consistency?: string | null;
    reasoning_support?: string | null;
    quick_comment_codes: string | null;
    created_at: string;
  }>;
  aggregate: {
    current_answer_id: number;
    review_count: number;
    avg_correctness: number | null;
    avg_completeness: number | null;
    avg_relevance: number | null;
    avg_clarity: number | null;
    agreement_score: number | null;
    final_decision: string | null;
    final_standard_answer_id: number | null;
  } | null;
};

export type LlmSession = {
  id: number;
  purpose: string;
  status: string;
  created_at: string;
  llm_config_id: number | null;
  llm_config_name: string | null;
  llm_model_name: string | null;
};

export type LlmMessage = {
  id: number;
  role: "system" | "user" | "assistant";
  content: string;
  target_answer_id: number | null;
  generated_answer_id: number | null;
  review_json: string | null;
  created_at: string;
};

export type MeProfile = {
  id: number;
  username: string;
  role: "admin" | "expert";
  status: string;
  full_name: string;
  organization: string | null;
  title: string | null;
  bio: string | null;
  created_at: string;
  applications: Array<{
    id: number;
    name: string;
  }>;
  business_tags: Array<{
    id: number;
    name: string;
  }>;
  allow_cross_business_review: boolean;
};

export type AdminDashboard = {
  metrics: {
    pending_experts: number;
    pending_qas: number;
    ongoing_tasks: number;
    disputed_qas: number;
    reviewed_qas: number;
    total_qas: number;
    imported_batches: number;
  };
  application_progress: Array<{
    id: number;
    name: string;
    total_qas: number;
    reviewed_qas: number;
  }>;
};

export type AdminAnalyticsSummary = {
  metrics: {
    pass_rate: number;
    rewrite_rate: number;
    dispute_rate: number;
    llm_adoption_rate: number;
  };
  application_breakdown: Array<{
    id: number;
    name: string;
    total_qas: number;
    pass_count: number;
    rewrite_count: number;
    fail_count: number;
    avg_agreement: number | null;
  }>;
  top_experts: Array<{
    id: number;
    full_name: string;
    completed_reviews: number;
  }>;
};

export type QueueJob = {
  job_id: string;
  type: string;
  status: "pending" | "processing" | "done" | "failed";
  filename: string;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  retry_count: number;
  updated_at: string;
  payload: Record<string, unknown>;
  error: string | null;
};

export type QueueMonitor = {
  summary: {
    pending: number;
    processing: number;
    done: number;
    failed: number;
  };
  jobs: QueueJob[];
};

export type ExportJob = {
  id: number;
  job_id: string;
  export_type: "final_dataset" | "review_records" | "disputed_cases";
  application_id: number | null;
  application_name: string | null;
  date_from: string | null;
  date_to: string | null;
  file_format: "json" | "jsonl";
  status: "pending" | "processing" | "done" | "failed";
  file_path: string | null;
  file_name: string | null;
  total_records: number;
  file_size_bytes: number;
  error_message: string | null;
  created_by: number;
  created_by_name?: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type TaxonomyItem = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  qa_count?: number;
};

export type ExpertTaxonomy = {
  technical_types: TaxonomyItem[];
  business_tags: TaxonomyItem[];
};

export type LlmConfigItem = {
  id: number;
  name: string;
  llm_use_case: "evaluation" | "trial";
  provider_code: string;
  provider_type: "openai_compatible";
  base_url: string;
  model_name: string;
  system_prompt: string | null;
  temperature: number;
  is_enabled: boolean;
  is_active: boolean;
  is_trial_enabled: boolean;
  created_at: string;
  updated_at: string;
  api_key_masked: string;
  has_api_key: boolean;
  last_tested_at: string | null;
  last_test_status: "passed" | "failed" | null;
  last_test_message: string | null;
  last_test_latency_ms: number | null;
};

export type ExpertLlmConfigOption = {
  id: number;
  name: string;
  provider_code: string;
  model_name: string;
  is_enabled: boolean;
  is_primary: boolean;
  has_api_key: boolean;
  last_tested_at: string | null;
  last_test_status: "passed" | "failed" | null;
};

export type TrialLlmConfigOption = {
  id: number;
  name: string;
  provider_code: string;
  model_name: string;
  is_enabled: boolean;
  is_trial_enabled: boolean;
  has_api_key: boolean;
  last_tested_at: string | null;
  last_test_status: "passed" | "failed" | null;
};

export type TrialSourceItem = {
  qa_item_id: number;
  answer_id: number;
  question_text: string;
  answer_text: string;
  context_text: string | null;
  application_name: string;
  technical_type_code: string | null;
  technical_type_name: string | null;
  task_type: "initial_review" | "dispute_review" | "final_confirm";
  task_status: string;
  updated_at: string;
  question_summary: string;
};

export type TrialSessionListItem = {
  id: number;
  llm_config_id: number;
  llm_config_name: string | null;
  llm_model_name: string | null;
  title: string;
  status: "active" | "completed" | "failed";
  created_at: string;
  updated_at: string;
};

export type TrialMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type TrialSessionDetail = {
  session: TrialSessionListItem;
  source: {
    qa_item_id: number;
    answer_id: number | null;
    question_text: string;
    answer_text: string | null;
    context_text: string | null;
    application_name: string | null;
    technical_type_code: string | null;
    technical_type_name: string | null;
    question_summary: string;
  } | null;
  messages: TrialMessage[];
};

export type AdminSystemStatus = {
  environment: {
    app_env: string;
    database: {
      path: string;
      exists: boolean;
      size_bytes: number;
    };
    runtime: {
      path: string;
      uploads_count: number;
      exports_count: number;
    };
  };
  llm: {
    total_configs: number;
    active_config: LlmConfigItem | null;
    passed_count: number;
    failed_count: number;
    missing_api_key_count: number;
    configs: LlmConfigItem[];
  };
  queue: {
    summary: {
      pending: number;
      processing: number;
      done: number;
      failed: number;
    };
    recent_failed_jobs: QueueJob[];
    recent_pending_jobs: QueueJob[];
  };
  backups: {
    directory: string;
    total_files: number;
    latest_file: {
      name: string;
      size_bytes: number;
      updated_at: string;
    } | null;
    files: Array<{
      name: string;
      size_bytes: number;
      updated_at: string;
    }>;
  };
};
