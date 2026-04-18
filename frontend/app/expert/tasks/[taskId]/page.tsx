"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  apiFetch,
  type LlmMessage,
  type LlmSession,
  type TaskDetail,
  type TaskDraft
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const scoreGroups = [
  {
    title: "正确性",
    field: "correctness_rating",
    options: [
      { label: "好", value: "good" },
      { label: "一般", value: "medium" },
      { label: "差", value: "bad" }
    ]
  },
  {
    title: "完整性",
    field: "completeness_rating",
    options: [
      { label: "完整", value: "full" },
      { label: "部分缺失", value: "partial" },
      { label: "明显缺失", value: "missing" }
    ]
  },
  {
    title: "相关性",
    field: "relevance_rating",
    options: [
      { label: "相关", value: "relevant" },
      { label: "部分偏题", value: "partial" },
      { label: "偏题", value: "offtopic" }
    ]
  },
  {
    title: "表达清晰度",
    field: "clarity_rating",
    options: [
      { label: "清晰", value: "clear" },
      { label: "一般", value: "normal" },
      { label: "不清晰", value: "unclear" }
    ]
  }
] as const;

const riskOptions = [
  { label: "无风险", value: "none" },
  { label: "事实风险", value: "factual" },
  { label: "合规风险", value: "compliance" },
  { label: "幻觉风险", value: "hallucination" }
] as const;

const decisionOptions = [
  { label: "通过", value: "pass" },
  { label: "待改写", value: "rewrite" },
  { label: "不通过", value: "fail" }
] as const;

const reasoningGroups = [
  {
    title: "推理链完整性",
    field: "reasoning_completeness",
    options: [
      { label: "强", value: "strong" },
      { label: "一般", value: "medium" },
      { label: "弱", value: "weak" }
    ]
  },
  {
    title: "推理链自洽性",
    field: "reasoning_consistency",
    options: [
      { label: "强", value: "strong" },
      { label: "一般", value: "medium" },
      { label: "弱", value: "weak" }
    ]
  },
  {
    title: "结论与推理一致性",
    field: "reasoning_support",
    options: [
      { label: "强", value: "strong" },
      { label: "一般", value: "medium" },
      { label: "弱", value: "weak" }
    ]
  }
] as const;

const quickCommentOptions = ["事实错误", "遗漏关键点", "表达不清", "偏题", "存在风险", "答案较优"];

type ScoreState = {
  correctness_rating: string;
  completeness_rating: string;
  relevance_rating: string;
  clarity_rating: string;
  risk_flag: string;
  reasoning_completeness: string;
  reasoning_consistency: string;
  reasoning_support: string;
  overall_decision: string;
  quick_comment_codes: string[];
};

const initialScoreState: ScoreState = {
  correctness_rating: "",
  completeness_rating: "",
  relevance_rating: "",
  clarity_rating: "",
  risk_flag: "none",
  reasoning_completeness: "",
  reasoning_consistency: "",
  reasoning_support: "",
  overall_decision: "",
  quick_comment_codes: []
};

function normalizeDraftPayload(draft: TaskDraft["payload"]): ScoreState {
  return {
    correctness_rating: draft.correctness_rating ?? "",
    completeness_rating: draft.completeness_rating ?? "",
    relevance_rating: draft.relevance_rating ?? "",
    clarity_rating: draft.clarity_rating ?? "",
    risk_flag: draft.risk_flag ?? "none",
    reasoning_completeness: draft.reasoning_completeness ?? "",
    reasoning_consistency: draft.reasoning_consistency ?? "",
    reasoning_support: draft.reasoning_support ?? "",
    overall_decision: draft.overall_decision ?? "",
    quick_comment_codes: draft.quick_comment_codes ?? []
  };
}

function resolveSavedPayload(detail: TaskDetail): TaskDraft | null {
  if (detail.draft && typeof detail.draft === "object") {
    return detail.draft as TaskDraft;
  }
  return detail.submitted_record;
}

function parseTags(tagsJson: string | null) {
  if (!tagsJson) return [];
  try {
    const parsed = JSON.parse(tagsJson) as string[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function formatDate(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

export default function ExpertTaskDetailPage() {
  const params = useParams<{ taskId: string }>();
  const taskId = params.taskId;
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [scores, setScores] = useState<ScoreState>(initialScoreState);
  const [selectedCandidateId, setSelectedCandidateId] = useState<number | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<LlmMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [llmPrompt, setLlmPrompt] = useState("");
  const [llmBusy, setLlmBusy] = useState(false);
  const [pollingSessionId, setPollingSessionId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);

  async function loadDetail(showLoading = false) {
    if (showLoading) setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<TaskDetail>(`/api/expert/tasks/${taskId}`);
      setDetail(data);
      setSelectedCandidateId((current) => current ?? data.current_answer.id);
      if (!selectedSessionId && data.llm_sessions.length > 0) {
        setSelectedSessionId(data.llm_sessions[0].id);
      }
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载任务失败");
      return null;
    } finally {
      if (showLoading) setLoading(false);
    }
  }

  async function loadMessages(sessionId: number) {
    try {
      const data = await apiFetch<LlmMessage[]>(
        `/api/expert/tasks/${taskId}/llm/sessions/${sessionId}/messages`
      );
      setMessages(data);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 LLM 消息失败");
      return null;
    }
  }

  useEffect(() => {
    async function bootstrap() {
      setLoading(true);
      setError(null);
      try {
        await apiFetch(`/api/expert/tasks/${taskId}/start`, { method: "POST" });
        const data = await apiFetch<TaskDetail>(`/api/expert/tasks/${taskId}`);
        setDetail(data);
        const savedPayload = resolveSavedPayload(data);
        setSelectedCandidateId(
          savedPayload?.payload.adopted_rewrite_answer_id ?? data.current_answer.id
        );
        if (savedPayload) {
          setScores(normalizeDraftPayload(savedPayload.payload));
        }
        const activeSession = data.llm_sessions.find((session) => session.status === "active");
        const firstSession = data.llm_sessions[0];
        if (firstSession) {
          setSelectedSessionId(firstSession.id);
          const llmMessages = await apiFetch<LlmMessage[]>(
            `/api/expert/tasks/${taskId}/llm/sessions/${firstSession.id}/messages`
          );
          setMessages(llmMessages);
        }
        if (activeSession) {
          setPollingSessionId(activeSession.id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载任务失败");
      } finally {
        setLoading(false);
      }
    }

    if (taskId) {
      void bootstrap();
    }
  }, [taskId]);

  useEffect(() => {
    if (!pollingSessionId) return;

    let cancelled = false;
    let timeoutId: number | undefined;
    let attempts = 0;

    async function poll() {
      attempts += 1;
      const latest = await loadDetail();
      if (cancelled || !latest) return;

      const targetSession = latest.llm_sessions.find((session) => session.id === pollingSessionId);
      if (targetSession) {
        await loadMessages(targetSession.id);
      }
      if (cancelled) return;

      if (!targetSession || targetSession.status === "completed") {
        setPollingSessionId(null);
        setNotice("LLM 结果已自动同步到当前页面。");
        return;
      }
      if (targetSession.status === "failed") {
        setPollingSessionId(null);
        setError("LLM 任务失败，请稍后重试。");
        return;
      }
      if (attempts >= 15) {
        setPollingSessionId(null);
        setNotice("LLM 请求仍在处理中。若 worker 未运行，可稍后回到本页继续查看。");
        return;
      }

      timeoutId = window.setTimeout(() => {
        void poll();
      }, 2000);
    }

    timeoutId = window.setTimeout(() => {
      void poll();
    }, 2000);

    return () => {
      cancelled = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [pollingSessionId]);

  async function handleLlmAction(purpose: "fact_check" | "risk_check" | "compare" | "rewrite") {
    if (!llmPrompt.trim() && purpose !== "rewrite") {
      setError("请先输入一条简短提示词");
      return;
    }

    setLlmBusy(true);
    setNotice(null);
    setError(null);
    try {
      let sessionId: number;
      if (purpose === "rewrite") {
        const result = await apiFetch<{ session_id: number }>(
          `/api/expert/tasks/${taskId}/llm/rewrite`,
          {
            method: "POST",
            body: JSON.stringify({ mode: llmPrompt.trim() || "balanced" })
          }
        );
        sessionId = result.session_id;
      } else {
        const created = await apiFetch<{ session_id: number }>(
          `/api/expert/tasks/${taskId}/llm/sessions`,
          {
            method: "POST",
            body: JSON.stringify({ purpose })
          }
        );
        sessionId = created.session_id;
        await apiFetch(
          `/api/expert/tasks/${taskId}/llm/sessions/${sessionId}/messages`,
          {
            method: "POST",
            body: JSON.stringify({ content: llmPrompt.trim() })
          }
        );
      }

      setSelectedSessionId(sessionId);
      await loadDetail();
      await loadMessages(sessionId);
      setPollingSessionId(sessionId);
      setNotice("LLM 请求已提交，页面会自动刷新消息和候选答案。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "LLM 请求失败");
    } finally {
      setLlmBusy(false);
    }
  }

  async function handleSaveDraft() {
    setSavingDraft(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/expert/tasks/${taskId}/draft`, {
        method: "POST",
        body: JSON.stringify({
          ...scores,
          adopted_rewrite_answer_id: selectedCandidateId
        })
      });
      setNotice("草稿已保存。");
      await loadDetail();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存草稿失败");
    } finally {
      setSavingDraft(false);
    }
  }

  async function handleSubmit() {
    const requiredFields = [
      scores.correctness_rating,
      scores.completeness_rating,
      scores.relevance_rating,
      scores.clarity_rating,
      scores.risk_flag,
      scores.overall_decision
    ];
    if (requiredFields.some((value) => !value)) {
      setError("请先完成评分、风险标记和总体结论");
      return;
    }
    if (
      detail?.qa_item.technical_type_code === "cot_qa" &&
      [
        scores.reasoning_completeness,
        scores.reasoning_consistency,
        scores.reasoning_support
      ].some((value) => !value)
    ) {
      setError("当前是 CoT 题，请补充推理链专项评分");
      return;
    }

    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/expert/tasks/${taskId}/submit`, {
        method: "POST",
        body: JSON.stringify({
          ...scores,
          adopted_rewrite_answer_id:
            scores.overall_decision === "rewrite" ? selectedCandidateId : null
        })
      });
      const latest = await loadDetail();
      if (latest) {
        const savedPayload = resolveSavedPayload(latest);
        if (savedPayload) {
          setScores(normalizeDraftPayload(savedPayload.payload));
          setSelectedCandidateId(
            savedPayload.payload.adopted_rewrite_answer_id ?? latest.current_answer.id
          );
        }
      }
      setNotice(isSubmitted ? "评测已重新提交，已覆盖上一次结果并触发聚合任务。" : "评测已提交，同时已触发聚合任务。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  const tags = useMemo(
    () => (detail ? parseTags(detail.qa_item.tags_json) : []),
    [detail]
  );
  const businessTags = useMemo(
    () => (detail ? parseTags(detail.qa_item.business_tags_json) : []),
    [detail]
  );
  const sessions = detail?.llm_sessions ?? [];
  const candidates = detail?.candidate_answers ?? [];
  const isPolling = pollingSessionId !== null;
  const isSubmitted = detail?.task.status === "submitted";
  const isCotQa = detail?.qa_item.technical_type_code === "cot_qa";

  if (loading) {
    return (
      <div className="rounded-[28px] border border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
        正在加载任务详情…
      </div>
    );
  }

  if (error && !detail) {
    return (
      <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        {error}
      </div>
    );
  }

  if (!detail) {
    return null;
  }

  const taskTypeLabel = detail.task.task_type === "dispute_review" ? "争议复核" : "初评";

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">任务详情 / #{detail.task.id}</p>
          <h2 className="mt-2 font-serif text-4xl">一屏完成评分、核查与改写确认</h2>
        </div>
        <div className="flex flex-wrap gap-3">
          <Badge variant="muted">{detail.qa_item.application_name}</Badge>
          {detail.qa_item.technical_type_name ? (
            <Badge variant="warning">{detail.qa_item.technical_type_name}</Badge>
          ) : null}
          <Badge variant={detail.task.status === "submitted" ? "success" : "default"}>
            {taskTypeLabel}
          </Badge>
          {isSubmitted ? <Badge variant="success">已提交，可再次修改</Badge> : null}
          {tags.map((tag) => (
            <Badge key={tag} variant="warning">
              {tag}
            </Badge>
          ))}
          {businessTags.map((tag) => (
            <Badge key={`business-${tag}`} variant="muted">
              {tag}
            </Badge>
          ))}
        </div>
      </section>

      {error ? (
        <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="rounded-[28px] border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
          {notice}
        </div>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle>问题与待评答案</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="rounded-[28px] border border-border bg-stone-50 p-5">
              <p className="text-sm text-muted-foreground">问题</p>
              <p className="mt-2 text-lg leading-8">{detail.qa_item.question_text}</p>
              {detail.qa_item.context_text ? (
                <p className="mt-3 text-sm leading-7 text-muted-foreground">
                  背景：{detail.qa_item.context_text}
                </p>
              ) : null}
            </div>
            <div className="rounded-[28px] border border-border bg-white p-5">
              <p className="text-sm text-muted-foreground">
                当前答案 v{detail.current_answer.version_no}
                {detail.current_answer.source_model
                  ? ` / ${detail.current_answer.source_model}`
                  : ""}
              </p>
              <p className="mt-2 leading-8 text-muted-foreground">
                {detail.current_answer.answer_text}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-stone-50">
          <CardHeader>
            <CardTitle>结构化评分</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {scoreGroups.map((group) => (
              <div key={group.title} className="space-y-2">
                <p className="text-sm font-medium">{group.title}</p>
                <div className="flex flex-wrap gap-2">
                  {group.options.map((option) => (
                    <Button
                      key={option.value}
                      variant={
                        scores[group.field] === option.value ? "default" : "secondary"
                      }
                      size="sm"
                      onClick={() =>
                        setScores((current) => ({
                          ...current,
                          [group.field]: option.value
                        }))
                      }
                    >
                      {option.label}
                    </Button>
                  ))}
                </div>
              </div>
            ))}

            <div className="space-y-2">
              <p className="text-sm font-medium">风险标记</p>
              <div className="flex flex-wrap gap-2">
                {riskOptions.map((option) => (
                  <Button
                    key={option.value}
                    variant={scores.risk_flag === option.value ? "default" : "secondary"}
                    size="sm"
                    onClick={() =>
                      setScores((current) => ({ ...current, risk_flag: option.value }))
                    }
                  >
                    {option.label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-sm font-medium">总体结论</p>
              <div className="flex flex-wrap gap-2">
                {decisionOptions.map((option) => (
                  <Button
                    key={option.value}
                    variant={
                      scores.overall_decision === option.value ? "default" : "secondary"
                    }
                    size="sm"
                    onClick={() =>
                      setScores((current) => ({ ...current, overall_decision: option.value }))
                    }
                  >
                    {option.label}
                  </Button>
                ))}
              </div>
            </div>

            {isCotQa ? (
              <div className="space-y-4 rounded-[24px] border border-dashed border-border bg-white p-4">
                <p className="text-sm font-medium text-muted-foreground">CoT 专项评审</p>
                {reasoningGroups.map((group) => (
                  <div key={group.title} className="space-y-2">
                    <p className="text-sm font-medium">{group.title}</p>
                    <div className="flex flex-wrap gap-2">
                      {group.options.map((option) => (
                        <Button
                          key={option.value}
                          variant={
                            scores[group.field] === option.value ? "default" : "secondary"
                          }
                          size="sm"
                          onClick={() =>
                            setScores((current) => ({
                              ...current,
                              [group.field]: option.value
                            }))
                          }
                        >
                          {option.label}
                        </Button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            <div className="space-y-2">
              <p className="text-sm font-medium">快速原因标签</p>
              <div className="flex flex-wrap gap-2">
                {quickCommentOptions.map((option) => {
                  const selected = scores.quick_comment_codes.includes(option);
                  return (
                    <Button
                      key={option}
                      variant={selected ? "default" : "secondary"}
                      size="sm"
                      onClick={() =>
                        setScores((current) => ({
                          ...current,
                          quick_comment_codes: selected
                            ? current.quick_comment_codes.filter((item) => item !== option)
                            : [...current.quick_comment_codes, option]
                        }))
                      }
                    >
                      {option}
                    </Button>
                  );
                })}
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <Card>
          <CardHeader className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-3">
              <CardTitle>LLM 对话辅助</CardTitle>
              {isPolling ? <Badge variant="warning">自动刷新中</Badge> : null}
            </div>
            <Button variant="secondary" size="sm" onClick={() => void loadDetail()}>
              手动刷新
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            <textarea
              className="field-textarea"
              placeholder="输入简短提示词，例如：请指出当前答案遗漏的关键点"
              value={llmPrompt}
              onChange={(event) => setLlmPrompt(event.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={llmBusy}
                onClick={() => void handleLlmAction("fact_check")}
              >
                事实检查
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={llmBusy}
                onClick={() => void handleLlmAction("risk_check")}
              >
                风险检查
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={llmBusy}
                onClick={() => void handleLlmAction("compare")}
              >
                比较分析
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={llmBusy}
                onClick={() => void handleLlmAction("rewrite")}
              >
                生成改写
              </Button>
            </div>

            <div className="rounded-[28px] border border-border bg-stone-50 p-4">
              <div className="mb-3 flex flex-wrap gap-2">
                {sessions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">当前还没有 LLM 会话。</p>
                ) : null}
                {sessions.map((session: LlmSession) => (
                  <Button
                    key={session.id}
                    size="sm"
                    variant={selectedSessionId === session.id ? "default" : "secondary"}
                    onClick={() => {
                      setSelectedSessionId(session.id);
                      void loadMessages(session.id);
                    }}
                  >
                    {session.purpose} #{session.id}
                  </Button>
                ))}
              </div>
              <div className="space-y-3">
                {messages.length === 0 ? (
                  <p className="text-sm text-muted-foreground">选择会话后，这里展示消息记录。</p>
                ) : null}
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className="rounded-3xl border border-border bg-white p-4 text-sm leading-7 text-muted-foreground"
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <Badge variant={message.role === "assistant" ? "success" : "muted"}>
                        {message.role}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {formatDate(message.created_at)}
                      </span>
                    </div>
                    {message.content}
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-3">
              <CardTitle>候选标准答案</CardTitle>
              {isPolling ? <Badge variant="warning">等待 LLM 回填</Badge> : null}
            </div>
            <Button variant="secondary" size="sm" onClick={() => void loadDetail()}>
              手动刷新
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {candidates.length === 0 ? (
              <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                当前还没有候选答案。请先触发 LLM 改写，且确保 worker 正在运行。
              </div>
            ) : null}

            {candidates.map((answer, index) => {
              const selected = selectedCandidateId === answer.id;
              return (
                <div key={answer.id} className="rounded-[28px] border border-border bg-stone-50 p-4">
                  <div className="mb-3 flex items-center justify-between gap-4">
                    <div className="flex gap-2">
                      <Badge variant={selected ? "success" : "muted"}>
                        {selected ? "当前推荐" : "可选候选"}
                      </Badge>
                      <Badge variant={index === 0 ? "warning" : "muted"}>
                        {answer.answer_type}
                      </Badge>
                    </div>
                    <Button
                      size="sm"
                      variant={selected ? "default" : "secondary"}
                      onClick={() => setSelectedCandidateId(answer.id)}
                    >
                      {selected ? "已选中" : "选为推荐答案"}
                    </Button>
                  </div>
                  <p className="text-sm leading-7 text-muted-foreground">{answer.answer_text}</p>
                </div>
              );
            })}
            <div className="flex justify-end gap-3">
              <Button
                variant="secondary"
                disabled={savingDraft}
                onClick={() => void handleSaveDraft()}
              >
                {savingDraft ? "保存中…" : "暂存"}
              </Button>
              <Button disabled={submitting} onClick={() => void handleSubmit()}>
                {submitting ? "提交中…" : isSubmitted ? "重新提交并覆盖" : "提交评测"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
