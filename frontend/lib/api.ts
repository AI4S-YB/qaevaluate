export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8100";

type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
};

export async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  let parsedToken: string | null = null;
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem("qaevaluate.auth");
    if (token) {
      try {
        parsedToken = (JSON.parse(token) as { token?: string }).token ?? null;
      } catch {
        parsedToken = null;
      }
    }
  }
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
    version_no: number;
    created_at: string;
  }>;
  llm_sessions: Array<{
    id: number;
    purpose: string;
    status: string;
    created_at: string;
  }>;
  draft: unknown;
};

export type TaskDraft = {
  payload: {
    correctness_rating?: string | null;
    completeness_rating?: string | null;
    relevance_rating?: string | null;
    clarity_rating?: string | null;
    risk_flag?: string | null;
    overall_decision?: string | null;
    quick_comment_codes?: string[];
    adopted_rewrite_answer_id?: number | null;
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
  applications: string;
};

export type ImportBatch = {
  id: number;
  name: string;
  source: string | null;
  file_path: string | null;
  import_status: "uploaded" | "parsed" | "failed";
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
    total_count: number;
    success_count: number;
    fail_count: number;
  };
  failures: ImportFailure[];
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

export type QaListItem = {
  id: number;
  external_id: string | null;
  status: string;
  application_name: string;
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
};

export type LlmMessage = {
  id: number;
  role: "system" | "user" | "assistant";
  content: string;
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
