"use client";

import { Ban, ChevronLeft, ChevronRight, Pencil, Save, X } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  API_BASE_URL,
  apiFetch,
  getStoredAuthToken,
  type ExpertTaskListItem,
  type ExpertLlmConfigOption,
  type LlmMessage,
  type LlmSession,
  type TaskDetail,
  type TaskDraft
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type SessionMessageMap = Record<number, LlmMessage[]>;
type ComparisonSessionMeta = {
  sessionId: number;
  label: string;
  modelName: string;
};

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

function findLatestGeneratedAnswerId(messages: LlmMessage[]) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "assistant" && message.generated_answer_id) {
      return message.generated_answer_id;
    }
  }
  return null;
}

function normalizeAnswerText(value: string | null | undefined) {
  return (value ?? "").trim();
}

function pickDefaultLlmConfigIds(configs: ExpertLlmConfigOption[]) {
  const usable = configs.filter((item) => item.is_enabled && item.has_api_key);
  const primary = usable.find((item) => item.is_primary);
  if (primary) return [primary.id];
  return usable[0] ? [usable[0].id] : [];
}

const MAX_SELECTED_LLM_CONFIGS = 2;

const actionButtonClassName =
  "h-12 min-w-[118px] rounded-2xl px-5 text-sm font-medium shadow-sm";

export default function ExpertTaskDetailPage() {
  const params = useParams<{ taskId: string }>();
  const router = useRouter();
  const taskId = params.taskId;
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [scores, setScores] = useState<ScoreState>(initialScoreState);
  const [selectedCandidateId, setSelectedCandidateId] = useState<number | null>(null);
  const [editableGeneratedAnswerText, setEditableGeneratedAnswerText] = useState("");
  const [editableSourceAnswerId, setEditableSourceAnswerId] = useState<number | null>(null);
  const [isEditingGeneratedAnswer, setIsEditingGeneratedAnswer] = useState(false);
  const [isQuestionExpanded, setIsQuestionExpanded] = useState(false);
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<number | null>(null);
  const [sessionMessagesMap, setSessionMessagesMap] = useState<SessionMessageMap>({});
  const [comparisonSessions, setComparisonSessions] = useState<ComparisonSessionMeta[]>([]);
  const [availableLlmConfigs, setAvailableLlmConfigs] = useState<ExpertLlmConfigOption[]>([]);
  const [selectedLlmConfigIds, setSelectedLlmConfigIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [llmPrompt, setLlmPrompt] = useState("");
  const [llmBusy, setLlmBusy] = useState(false);
  const [autoReviewing, setAutoReviewing] = useState(false);
  const [pollingSessionId, setPollingSessionId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [abandoning, setAbandoning] = useState(false);
  const [jumpingPrevious, setJumpingPrevious] = useState(false);
  const [jumpingNext, setJumpingNext] = useState(false);
  const [isLlmModalOpen, setIsLlmModalOpen] = useState(false);
  const llmTextareaRef = useRef<HTMLTextAreaElement | null>(null);

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
      setSessionMessagesMap((current) => ({ ...current, [sessionId]: data }));
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 LLM 消息失败");
      return null;
    }
  }

  async function loadAvailableLlmConfigs() {
    try {
      const data = await apiFetch<ExpertLlmConfigOption[]>(
        `/api/expert/tasks/${taskId}/llm/configs`
      );
      setAvailableLlmConfigs(data);
      setSelectedLlmConfigIds((current) =>
        current.length > 0 ? current : pickDefaultLlmConfigIds(data)
      );
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载模型列表失败");
      return [];
    }
  }

  useEffect(() => {
    async function bootstrap() {
      setLoading(true);
      setError(null);
      try {
        await apiFetch(`/api/expert/tasks/${taskId}/start`, { method: "POST" });
        const [data, llmConfigs] = await Promise.all([
          apiFetch<TaskDetail>(`/api/expert/tasks/${taskId}`),
          apiFetch<ExpertLlmConfigOption[]>(`/api/expert/tasks/${taskId}/llm/configs`)
        ]);
        setDetail(data);
        setAvailableLlmConfigs(llmConfigs);
        setSelectedLlmConfigIds((current) =>
          current.length > 0 ? current : pickDefaultLlmConfigIds(llmConfigs)
        );
        const savedPayload = resolveSavedPayload(data);
        const initialCandidateId =
          savedPayload?.payload.adopted_rewrite_answer_id ?? data.current_answer.id;
        setSelectedCandidateId(initialCandidateId);
        if (savedPayload) {
          setScores(normalizeDraftPayload(savedPayload.payload));
        }
        if (initialCandidateId !== data.current_answer.id) {
          const initialCandidate =
            data.candidate_answers.find((item) => item.id === initialCandidateId) ?? null;
          const editedAnswerText = normalizeAnswerText(
            savedPayload?.payload.adopted_rewrite_answer_text
          );
          setEditableSourceAnswerId(initialCandidateId);
          setEditableGeneratedAnswerText(
            editedAnswerText || initialCandidate?.answer_text || ""
          );
        } else {
          setEditableSourceAnswerId(null);
          setEditableGeneratedAnswerText("");
        }
        setIsEditingGeneratedAnswer(false);
        const activeSession = data.llm_sessions.find((session) => session.status === "active");
        const firstSession = data.llm_sessions[0];
        if (firstSession) {
          setSelectedSessionId(firstSession.id);
          const llmMessages = await apiFetch<LlmMessage[]>(
            `/api/expert/tasks/${taskId}/llm/sessions/${firstSession.id}/messages`
          );
          setSessionMessagesMap((current) => ({ ...current, [firstSession.id]: llmMessages }));
          const generatedAnswerId = findLatestGeneratedAnswerId(llmMessages);
          if (generatedAnswerId && !savedPayload?.payload.adopted_rewrite_answer_id) {
            setSelectedCandidateId(generatedAnswerId);
          }
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
      let sessionMessages: LlmMessage[] | null = null;
      if (targetSession) {
        sessionMessages = await loadMessages(targetSession.id);
      }
      if (cancelled) return;

      if (!targetSession || targetSession.status === "completed") {
        setPollingSessionId(null);
        const generatedAnswerId = sessionMessages
          ? findLatestGeneratedAnswerId(sessionMessages)
          : null;
        if (generatedAnswerId) {
          setSelectedCandidateId(generatedAnswerId);
        }
        setNotice(
          generatedAnswerId
            ? `LLM 结果已自动同步，并已选中本轮生成的候选答案 #${generatedAnswerId}。`
            : "LLM 结果已自动同步到当前页面。"
        );
        return;
      }
      if (targetSession.status === "failed") {
        setPollingSessionId(null);
        setError("LLM 任务失败，请稍后重试。");
        return;
      }
      if (attempts >= 60) {
        setPollingSessionId(null);
        setNotice("LLM 请求仍在处理中，你可以稍后回到本页继续查看。");
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

  useEffect(() => {
    if (!isLlmModalOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const timeoutId = window.setTimeout(() => {
      llmTextareaRef.current?.focus();
    }, 0);

    function handleKeydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsLlmModalOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeydown);
    return () => {
      window.clearTimeout(timeoutId);
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeydown);
    };
  }, [isLlmModalOpen]);

  async function handleLlmAssist() {
    if (!detail) return;
    setLlmBusy(true);
    setNotice(null);
    setError(null);
    try {
      const latestSessionCandidateId = findLatestGeneratedAnswerId(messages);
      const promptText =
        llmPrompt.trim() ||
        "请基于当前问题、当前答案和已填写评分，评估这条答案是否合适，并给出更适合作为标准答案候选的修正版。";
      const targetAnswerId =
        latestSessionCandidateId ?? selectedCandidateId ?? detail.current_answer.id;
      const chosenConfigIds =
        selectedLlmConfigIds.length > 0
          ? selectedLlmConfigIds
          : pickDefaultLlmConfigIds(availableLlmConfigs);
      const usableConfigIds = Array.from(
        new Set(
          chosenConfigIds.filter((configId) =>
            availableLlmConfigs.some(
              (item) => item.id === configId && item.is_enabled && item.has_api_key
            )
          )
        )
      );
      if (usableConfigIds.length === 0) {
        throw new Error("当前没有可用模型，请先在后台启用并配置 API Key。");
      }

      const sessionEntries: Array<{ configId: number; sessionId: number }> = [];
      for (const configId of usableConfigIds) {
        const reusableSession = sessions.find((session) => session.llm_config_id === configId);
        if (reusableSession) {
          sessionEntries.push({ configId, sessionId: reusableSession.id });
          continue;
        }
        const created = await apiFetch<{ session_id: number }>(
          `/api/expert/tasks/${taskId}/llm/sessions`,
          {
            method: "POST",
            body: JSON.stringify({ purpose: "rewrite", llm_config_id: configId })
          }
        );
        sessionEntries.push({ configId, sessionId: created.session_id });
      }

      const liveEntry =
        sessionEntries.find((item) => item.sessionId === selectedSessionId) ?? sessionEntries[0];
      setComparisonSessions(
        sessionEntries.map((entry) => {
          const config = availableLlmConfigs.find((item) => item.id === entry.configId);
          return {
            sessionId: entry.sessionId,
            label: config?.name ?? `模型 #${entry.configId}`,
            modelName: config?.model_name ?? ""
          };
        })
      );
      setSelectedSessionId(liveEntry.sessionId);
      if (selectedSessionId !== liveEntry.sessionId) {
        await loadMessages(liveEntry.sessionId);
      }

      async function streamSessionRequest(sessionId: number) {
        const authToken = getStoredAuthToken();
        const now = new Date().toISOString();
        const tempUserMessageId = -Date.now() - sessionId;
        const tempAssistantMessageId = tempUserMessageId - 100000;

        setSessionMessagesMap((current) => ({
          ...current,
          [sessionId]: [
            ...(current[sessionId] ?? []),
            {
              id: tempUserMessageId,
              role: "user",
              content: promptText,
              target_answer_id: targetAnswerId,
              generated_answer_id: null,
              review_json: null,
              created_at: now
            },
            {
              id: tempAssistantMessageId,
              role: "assistant",
              content: "",
              target_answer_id: targetAnswerId,
              generated_answer_id: null,
              review_json: null,
              created_at: now
            }
          ]
        }));

        const response = await fetch(
          `${API_BASE_URL}/api/expert/tasks/${taskId}/llm/sessions/${sessionId}/stream`,
          {
            method: "POST",
            headers: {
              ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
              "Content-Type": "application/json"
            },
            body: JSON.stringify({
              content: promptText,
              target_answer_id: targetAnswerId,
              score_context: scores
            }),
            cache: "no-store"
          }
        );
        if (!response.ok || !response.body) {
          const text = await response.text();
          throw new Error(text || `request failed: ${response.status}`);
        }

        const decoder = new TextDecoder();
        const reader = response.body.getReader();
        let buffer = "";
        let streamedAssistantText = "";
        let streamedCandidateAnswerId: number | null = null;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split("\n\n");
          buffer = events.pop() ?? "";

          for (const rawEvent of events) {
            const lines = rawEvent.split("\n");
            const eventName =
              lines.find((line) => line.startsWith("event:"))?.slice(6).trim() ?? "message";
            const dataText = lines
              .filter((line) => line.startsWith("data:"))
              .map((line) => line.slice(5).trim())
              .join("\n");
            const eventPayload = dataText
              ? (JSON.parse(dataText) as Record<string, unknown>)
              : {};

            if (eventName === "delta") {
              const chunk =
                typeof eventPayload.content === "string" ? eventPayload.content : "";
              if (chunk) {
                streamedAssistantText += chunk;
                setSessionMessagesMap((current) => ({
                  ...current,
                  [sessionId]: (current[sessionId] ?? []).map((message) =>
                    message.id === tempAssistantMessageId
                      ? { ...message, content: streamedAssistantText }
                      : message
                  )
                }));
              }
            }

            if (eventName === "done") {
              streamedCandidateAnswerId =
                typeof eventPayload.candidate_answer_id === "number"
                  ? eventPayload.candidate_answer_id
                  : null;
            }

            if (eventName === "error") {
              throw new Error(
                typeof eventPayload.detail === "string"
                  ? eventPayload.detail
                  : "LLM 流式请求失败"
              );
            }
          }
        }

        return streamedCandidateAnswerId;
      }

      const candidateAnswerIds = (
        await Promise.all(
          sessionEntries.map((entry) =>
            streamSessionRequest(entry.sessionId)
          )
        )
      ).filter((value): value is number => typeof value === "number");

      await loadDetail();
      await Promise.all(sessionEntries.map((entry) => loadMessages(entry.sessionId)));
      if (candidateAnswerIds.length > 0) {
        setSelectedCandidateId(candidateAnswerIds[0]);
      }
      setLlmPrompt("");
      window.setTimeout(() => {
        llmTextareaRef.current?.focus();
      }, 0);
      setNotice(
        candidateAnswerIds.length > 0
          ? `LLM 已完成，共生成 ${candidateAnswerIds.length} 条候选答案。`
          : "LLM 已流式完成。"
      );
    } catch (err) {
      await loadDetail();
      if (selectedSessionId) {
        await loadMessages(selectedSessionId);
      }
      setError(err instanceof Error ? err.message : "LLM 请求失败");
    } finally {
      setLlmBusy(false);
    }
  }

  async function handleAutoReview() {
    if (!detail) return;
    setAutoReviewing(true);
    setError(null);
    setNotice(null);
    try {
      const autoReviewConfigId =
        selectedLlmConfigIds.length === 1
          ? selectedLlmConfigIds[0]
          : pickDefaultLlmConfigIds(availableLlmConfigs)[0] ?? null;
      const result = await apiFetch<{
        session_id: number;
        candidate_answer_id: number | null;
        score_context: {
          correctness_rating: string;
          completeness_rating: string;
          relevance_rating: string;
          clarity_rating: string;
          risk_flag: string;
          reasoning_completeness?: string | null;
          reasoning_consistency?: string | null;
          reasoning_support?: string | null;
          overall_decision: string;
          quick_comment_codes: string[];
        };
      }>(`/api/expert/tasks/${taskId}/llm/auto-review`, {
        method: "POST",
        body: JSON.stringify({
          target_answer_id: selectedCandidateId ?? detail.current_answer.id,
          llm_config_id: autoReviewConfigId
        })
      });

      setScores((current) => ({
        ...current,
        correctness_rating: result.score_context.correctness_rating ?? current.correctness_rating,
        completeness_rating:
          result.score_context.completeness_rating ?? current.completeness_rating,
        relevance_rating: result.score_context.relevance_rating ?? current.relevance_rating,
        clarity_rating: result.score_context.clarity_rating ?? current.clarity_rating,
        risk_flag: result.score_context.risk_flag ?? current.risk_flag,
        reasoning_completeness: result.score_context.reasoning_completeness ?? "",
        reasoning_consistency: result.score_context.reasoning_consistency ?? "",
        reasoning_support: result.score_context.reasoning_support ?? "",
        overall_decision: result.score_context.overall_decision ?? current.overall_decision,
        quick_comment_codes: result.score_context.quick_comment_codes ?? []
      }));
      setSelectedSessionId(result.session_id);
      if (result.candidate_answer_id) {
        setSelectedCandidateId(result.candidate_answer_id);
      }
      await loadDetail();
      await loadMessages(result.session_id);
      setNotice("自动化评测已完成，结构化评分和 LLM辅助生成答案已回填。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "自动化评测失败");
    } finally {
      setAutoReviewing(false);
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
          adopted_rewrite_answer_id: selectedCandidateId,
          adopted_rewrite_answer_text: hasEditedGeneratedAnswer
            ? normalizeAnswerText(editableGeneratedAnswerText)
            : null
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

  async function goToAdjacentTask(direction: "previous" | "next", currentTaskId?: number) {
    const taskList = await apiFetch<ExpertTaskListItem[]>("/api/expert/tasks");
    const availableTasks = taskList.filter(
      (item) => item.status === "pending" || item.status === "in_progress"
    );
    const currentId = currentTaskId ?? Number(taskId);
    const currentIndex = availableTasks.findIndex((item) => item.id === currentId);
    const targetTask =
      currentIndex >= 0
        ? availableTasks[currentIndex + (direction === "next" ? 1 : -1)]
        : availableTasks[0];

    if (targetTask) {
      router.push(`/expert/tasks/${targetTask.id}`);
      return true;
    }
    router.push("/expert/tasks");
    return false;
  }

  async function handlePreviousTask() {
    setJumpingPrevious(true);
    setError(null);
    setNotice(null);
    try {
      const found = await goToAdjacentTask("previous", Number(taskId));
      if (!found) {
        setNotice("当前没有上一条待处理任务，已返回任务列表。");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "跳转上一题失败");
    } finally {
      setJumpingPrevious(false);
    }
  }

  async function handleNextTask() {
    setJumpingNext(true);
    setError(null);
    setNotice(null);
    try {
      const found = await goToAdjacentTask("next", Number(taskId));
      if (!found) {
        setNotice("当前没有下一条待处理任务，已返回任务列表。");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "跳转下一题失败");
    } finally {
      setJumpingNext(false);
    }
  }

  async function handleAbandonTask() {
    setAbandoning(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/expert/tasks/${taskId}/abandon`, {
        method: "POST"
      });
      setNotice("已放弃当前评测，正在跳转到下一题。");
      window.setTimeout(() => {
        void goToAdjacentTask("next", Number(taskId));
      }, 600);
    } catch (err) {
      setError(err instanceof Error ? err.message : "放弃评测失败");
    } finally {
      setAbandoning(false);
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
            scores.overall_decision === "rewrite" ? selectedCandidateId : null,
          adopted_rewrite_answer_text:
            scores.overall_decision === "rewrite" && hasEditedGeneratedAnswer
              ? normalizeAnswerText(editableGeneratedAnswerText)
              : null
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
      setNotice(
        isSubmitted
          ? "评测已重新提交，正在跳转到下一题。"
          : "评测提交成功，正在跳转到下一题。"
      );
      window.setTimeout(() => {
        void goToAdjacentTask("next", Number(taskId));
      }, 700);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeleteSession(sessionId: number) {
    setDeletingSessionId(sessionId);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/expert/tasks/${taskId}/llm/sessions/${sessionId}`, {
        method: "DELETE"
      });
      if (pollingSessionId === sessionId) {
        setPollingSessionId(null);
      }

      const latest = await loadDetail();
      const remainingSessions = (latest?.llm_sessions ?? []).filter((session) => session.id !== sessionId);
      setSessionMessagesMap((current) => {
        const next = { ...current };
        delete next[sessionId];
        return next;
      });
      setComparisonSessions((current) =>
        current.filter((session) => session.sessionId !== sessionId)
      );
      if (selectedSessionId === sessionId) {
        const nextSessionId = remainingSessions[0]?.id ?? null;
        setSelectedSessionId(nextSessionId);
        if (nextSessionId) {
          await loadMessages(nextSessionId);
        } else {
          setSessionMessagesMap({});
        }
      }
      setNotice(`会话 #${sessionId} 已删除。`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除会话失败");
    } finally {
      setDeletingSessionId(null);
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
  const messages = selectedSessionId ? sessionMessagesMap[selectedSessionId] ?? [] : [];
  const candidates = detail?.candidate_answers ?? [];
  const isPolling = pollingSessionId !== null;
  const isSubmitted = detail?.task.status === "submitted";
  const isCotQa = detail?.qa_item.technical_type_code === "cot_qa";
  const activeCandidate =
    candidates.find((answer) => answer.id === selectedCandidateId) ?? detail?.current_answer ?? null;
  const showingGeneratedAnswer = Boolean(
    detail && activeCandidate && activeCandidate.id !== detail.current_answer.id
  );
  const hasEditedGeneratedAnswer = Boolean(
    showingGeneratedAnswer &&
      normalizeAnswerText(editableGeneratedAnswerText) &&
      normalizeAnswerText(editableGeneratedAnswerText) !== normalizeAnswerText(activeCandidate?.answer_text)
  );
  const displayedGeneratedAnswerText =
    showingGeneratedAnswer && editableGeneratedAnswerText
      ? editableGeneratedAnswerText
      : activeCandidate?.answer_text ?? "";

  useEffect(() => {
    if (!detail) return;
    if (!activeCandidate || activeCandidate.id === detail.current_answer.id) {
      setEditableSourceAnswerId(null);
      setEditableGeneratedAnswerText("");
      setIsEditingGeneratedAnswer(false);
      return;
    }
    if (activeCandidate.id !== editableSourceAnswerId) {
      setEditableSourceAnswerId(activeCandidate.id);
      setEditableGeneratedAnswerText(activeCandidate.answer_text);
      setIsEditingGeneratedAnswer(false);
    }
  }, [activeCandidate, detail, editableSourceAnswerId]);

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
                答案 v{detail.current_answer.version_no}
                {detail.current_answer.source_model
                  ? ` / ${detail.current_answer.source_model}`
                  : ""}
              </p>
              <p className="mt-2 leading-8 text-muted-foreground">
                {detail.current_answer.answer_text}
              </p>
            </div>
            {showingGeneratedAnswer ? (
              <div className="rounded-[28px] border border-emerald-200 bg-emerald-50 p-5">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-emerald-700">
                    {hasEditedGeneratedAnswer
                      ? "LLM辅助生成答案 + 用户编辑"
                      : "LLM辅助生成答案"}
                    {activeCandidate?.version_no ? ` / v${activeCandidate.version_no}` : ""}
                  </p>
                  <Button
                    size="sm"
                    variant="secondary"
                    className="bg-white/80 text-emerald-800 ring-1 ring-emerald-200 hover:bg-white"
                    onClick={() => setIsEditingGeneratedAnswer((current) => !current)}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                    {isEditingGeneratedAnswer ? "完成编辑" : "编辑"}
                  </Button>
                </div>
                {isEditingGeneratedAnswer ? (
                  <textarea
                    className="mt-3 min-h-[180px] w-full rounded-[20px] border border-emerald-200 bg-white px-4 py-3 leading-7 text-emerald-950 outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100"
                    value={displayedGeneratedAnswerText}
                    onChange={(event) => setEditableGeneratedAnswerText(event.target.value)}
                  />
                ) : (
                  <p className="mt-2 whitespace-pre-wrap leading-8 text-emerald-950">
                    {displayedGeneratedAnswerText}
                  </p>
                )}
              </div>
            ) : null}
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

      <section className="rounded-[32px] border border-border bg-white p-5 shadow-soft">
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium text-foreground">操作区</p>
            <p className="mt-1 text-sm text-muted-foreground">
              `自动化评测` 会自动回填结构化评分和 LLM辅助生成答案；`LLM辅助评测` 用于打开对话框继续和模型讨论与改写；圆形图标按钮依次用于 `上一题`、`下一题`、`放弃评测`、`暂存`；`提交评测` 用于正式提交结果。
            </p>
          </div>
          <div className="flex flex-nowrap items-center justify-center gap-3 overflow-x-auto pb-1">
            <Button
              variant="secondary"
              className={`${actionButtonClassName} min-w-[110px] shrink-0 bg-amber-50 text-amber-700 ring-1 ring-amber-200 hover:bg-amber-100`}
              disabled={jumpingPrevious}
              onClick={() => void handlePreviousTask()}
              title={jumpingPrevious ? "跳转上一题中" : "上一题"}
              aria-label={jumpingPrevious ? "跳转上一题中" : "上一题"}
            >
              <ChevronLeft className="h-4 w-4" />
              <span>{jumpingPrevious ? "跳转中…" : "上一题"}</span>
            </Button>
            <Button
              variant="secondary"
              className={`${actionButtonClassName} min-w-[110px] shrink-0 bg-sky-50 text-sky-700 ring-1 ring-sky-200 hover:bg-sky-100`}
              disabled={jumpingNext}
              onClick={() => void handleNextTask()}
              title={jumpingNext ? "跳转下一题中" : "下一题"}
              aria-label={jumpingNext ? "跳转下一题中" : "下一题"}
            >
              <ChevronRight className="h-4 w-4" />
              <span>{jumpingNext ? "跳转中…" : "下一题"}</span>
            </Button>
            <Button
              className={actionButtonClassName}
              disabled={autoReviewing}
              onClick={() => void handleAutoReview()}
            >
              {autoReviewing ? "自动评测中…" : "自动化评测"}
            </Button>
            <Button
              className={`${actionButtonClassName} bg-stone-900 text-white hover:bg-stone-800`}
              variant="secondary"
              onClick={() => setIsLlmModalOpen(true)}
            >
              LLM辅助评测
            </Button>
            <Button
              size="icon"
              variant="secondary"
              className="shrink-0 bg-rose-50 text-rose-700 ring-1 ring-rose-200 hover:bg-rose-100"
              disabled={abandoning}
              onClick={() => void handleAbandonTask()}
              title={abandoning ? "放弃评测中" : "放弃评测"}
              aria-label={abandoning ? "放弃评测中" : "放弃评测"}
            >
              <Ban className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              variant="secondary"
              className="shrink-0 bg-white text-foreground ring-1 ring-border hover:bg-stone-100"
              disabled={savingDraft}
              onClick={() => void handleSaveDraft()}
              title={savingDraft ? "暂存中" : "暂存"}
              aria-label={savingDraft ? "暂存中" : "暂存"}
            >
              <Save className="h-4 w-4" />
            </Button>
            <Button
              className={`${actionButtonClassName} bg-emerald-600 text-white hover:bg-emerald-500`}
              disabled={submitting}
              onClick={() => void handleSubmit()}
            >
              {submitting ? "提交中…" : "提交评测"}
            </Button>
          </div>
        </div>
      </section>

      {isLlmModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/40 p-4 backdrop-blur-sm">
          <div className="flex max-h-[92vh] w-full max-w-[1600px] flex-col overflow-hidden rounded-[32px] border border-border bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <div>
                <p className="text-sm text-muted-foreground">LLM 辅助评测</p>
                <h3 className="text-xl font-semibold text-foreground">当前任务 #{detail.task.id}</h3>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setSelectedSessionId(null);
                    setComparisonSessions([]);
                    setNotice("已切换为新对话，下一次发送会创建新的 LLM 会话。");
                  }}
                >
                  新建对话
                </Button>
                <Button variant="secondary" size="sm" onClick={() => setIsLlmModalOpen(false)}>
                  关闭
                </Button>
              </div>
            </div>

            <div className="border-b border-border bg-[linear-gradient(180deg,#fafaf9_0%,#f5f5f4_100%)] px-6 py-3">
              <div className="grid gap-3 lg:grid-cols-[1.15fr_0.85fr]">
                <div className="rounded-[20px] border border-border bg-white px-4 py-3 shadow-sm">
                  <div className="flex items-start gap-3">
                    <span className="rounded-full bg-stone-100 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                      问题
                    </span>
                    <button
                      type="button"
                      className={`min-w-0 flex-1 text-left text-sm leading-6 text-foreground ${
                        isQuestionExpanded ? "" : "line-clamp-1"
                      }`}
                      onClick={() => setIsQuestionExpanded((current) => !current)}
                      title={isQuestionExpanded ? "收起问题全文" : detail.qa_item.question_text}
                    >
                      {detail.qa_item.question_text}
                    </button>
                  </div>
                </div>
                <div className="rounded-[20px] border border-border bg-white px-4 py-3 shadow-sm">
                  <div className="flex items-start gap-3">
                    <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-emerald-700">
                      答案
                    </span>
                    <p className="min-w-0 flex-1 text-sm leading-6 text-muted-foreground">
                      当前选中答案 #{selectedCandidateId ?? detail.current_answer.id}
                    </p>
                  </div>
                </div>
              </div>
              <div className="mt-3 rounded-[20px] border border-border bg-white px-4 py-4 shadow-sm">
                <p className="text-sm font-medium text-foreground">本轮使用模型</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  最多同时选择两个模型；默认会选中主模型。发送后会按所选模型分别生成候选答案。
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {availableLlmConfigs.map((config) => {
                    const selected = selectedLlmConfigIds.includes(config.id);
                    return (
                      <button
                        key={config.id}
                        type="button"
                        disabled={!config.has_api_key || llmBusy}
                        className={`rounded-full border px-4 py-2 text-sm transition ${
                          selected
                            ? "border-stone-900 bg-stone-900 text-white"
                            : "border-border bg-white text-foreground hover:bg-stone-50"
                        } disabled:cursor-not-allowed disabled:opacity-45`}
                        onClick={() =>
                          setSelectedLlmConfigIds((current) => {
                            if (current.includes(config.id)) {
                              return current.filter((item) => item !== config.id);
                            }
                            if (current.length >= MAX_SELECTED_LLM_CONFIGS) {
                              setNotice("LLM辅助评测最多同时选择两个模型。");
                              return current;
                            }
                            return [...current, config.id];
                          })
                        }
                      >
                        <span>{config.name}</span>
                        <span className="ml-2 text-xs opacity-80">{config.model_name}</span>
                        {config.is_primary ? <span className="ml-2 text-xs opacity-80">主</span> : null}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {sessions.length === 0 ? (
                  <span className="text-sm text-muted-foreground">当前还没有 LLM 会话。</span>
                ) : null}
                {sessions.map((session: LlmSession) => (
                  <div
                    key={session.id}
                    className={`inline-flex items-center overflow-hidden rounded-full border ${
                      selectedSessionId === session.id
                        ? "border-stone-900 bg-stone-900 text-white"
                        : "border-border bg-white text-foreground"
                    }`}
                  >
                    <button
                      type="button"
                      className="h-9 px-4 text-sm"
                      onClick={() => {
                        setSelectedSessionId(session.id);
                        void loadMessages(session.id);
                      }}
                    >
                      会话 #{session.id}
                      {session.llm_config_name ? ` · ${session.llm_config_name}` : ""}
                      {session.llm_model_name ? ` / ${session.llm_model_name}` : ""}
                    </button>
                    <button
                      type="button"
                      className={`flex h-9 w-9 items-center justify-center border-l ${
                        selectedSessionId === session.id
                          ? "border-white/20 text-white/85 hover:bg-white/10"
                          : "border-border text-muted-foreground hover:bg-rose-50 hover:text-rose-700"
                      } disabled:pointer-events-none disabled:opacity-40`}
                      disabled={session.status === "active" || deletingSessionId === session.id}
                      onClick={() => void handleDeleteSession(session.id)}
                      title={
                        session.status === "active"
                          ? "会话处理中，暂时不能删除"
                          : deletingSessionId === session.id
                            ? "删除中"
                            : `删除会话 #${session.id}`
                      }
                      aria-label={
                        session.status === "active"
                          ? "会话处理中，暂时不能删除"
                          : deletingSessionId === session.id
                            ? "删除中"
                            : `删除会话 #${session.id}`
                      }
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto bg-[linear-gradient(180deg,#ffffff_0%,#fafaf9_100%)] px-6 py-5">
              {comparisonSessions.length >= 2 ? (
                <div className="grid gap-4 xl:grid-cols-2">
                  {comparisonSessions.map((sessionMeta) => {
                    const sessionMessages = sessionMessagesMap[sessionMeta.sessionId] ?? [];
                    return (
                      <div
                        key={sessionMeta.sessionId}
                        className="rounded-[28px] border border-border bg-white p-4 shadow-sm"
                      >
                        <div className="mb-4 flex items-center justify-between gap-3 border-b border-border pb-3">
                          <div>
                            <p className="font-medium text-foreground">{sessionMeta.label}</p>
                            <p className="text-sm text-muted-foreground">
                              会话 #{sessionMeta.sessionId}
                              {sessionMeta.modelName ? ` / ${sessionMeta.modelName}` : ""}
                            </p>
                          </div>
                          <Button
                            size="sm"
                            variant={
                              selectedSessionId === sessionMeta.sessionId ? "default" : "secondary"
                            }
                            onClick={() => {
                              setSelectedSessionId(sessionMeta.sessionId);
                              void loadMessages(sessionMeta.sessionId);
                            }}
                          >
                            {selectedSessionId === sessionMeta.sessionId ? "当前查看" : "切换为主视图"}
                          </Button>
                        </div>

                        <div className="space-y-4">
                          {sessionMessages.length === 0 ? (
                            <div className="rounded-[24px] border border-dashed border-border bg-stone-50 p-6 text-sm text-muted-foreground">
                              当前模型还没有返回内容。
                            </div>
                          ) : null}

                          {sessionMessages.map((message) => {
                            const messageCandidate = message.generated_answer_id
                              ? candidates.find((answer) => answer.id === message.generated_answer_id)
                              : null;
                            const isMessageCandidateSelected =
                              message.generated_answer_id !== null &&
                              selectedCandidateId === message.generated_answer_id;

                            return (
                              <div
                                key={message.id}
                                className={`rounded-[24px] border p-4 text-sm leading-7 ${
                                  message.role === "user"
                                    ? "border-emerald-200 bg-emerald-50 text-emerald-950"
                                    : "border-border bg-stone-50 text-muted-foreground"
                                }`}
                              >
                                <div className="mb-2 flex flex-wrap items-center gap-2">
                                  <Badge variant={message.role === "user" ? "success" : "muted"}>
                                    {message.role === "user" ? "专家输入" : "模型输出"}
                                  </Badge>
                                  {message.generated_answer_id ? (
                                    <Badge variant="success">
                                      候选答案 #{message.generated_answer_id}
                                    </Badge>
                                  ) : null}
                                  <span className="text-xs text-muted-foreground">
                                    {formatDate(message.created_at)}
                                  </span>
                                </div>
                                <div className="whitespace-pre-wrap">{message.content}</div>
                                {messageCandidate ? (
                                  <div className="mt-4 rounded-[20px] border border-border bg-white p-4">
                                    <div className="flex flex-wrap items-center justify-between gap-3">
                                      <div className="flex flex-wrap gap-2">
                                        <Badge variant="success">
                                          候选答案 #{messageCandidate.id}
                                        </Badge>
                                        <Badge variant="muted">v{messageCandidate.version_no}</Badge>
                                      </div>
                                      <Button
                                        size="sm"
                                        variant={
                                          isMessageCandidateSelected ? "default" : "secondary"
                                        }
                                        onClick={() => setSelectedCandidateId(messageCandidate.id)}
                                      >
                                        {isMessageCandidateSelected ? "当前已选中" : "选为提交答案"}
                                      </Button>
                                    </div>
                                    <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-muted-foreground">
                                      {messageCandidate.answer_text}
                                    </p>
                                  </div>
                                ) : null}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
              <div className="space-y-4">
                {messages.length === 0 ? (
                  <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
                    这里会展示专家输入和 LLM 输出。
                    <br />
                    你可以直接输入“这版哪里不合适”，让 LLM 继续辅助评测和改写。
                  </div>
                ) : null}

                {messages.map((message) => {
                  const messageCandidate = message.generated_answer_id
                    ? candidates.find((answer) => answer.id === message.generated_answer_id)
                    : null;
                  const isMessageCandidateSelected =
                    message.generated_answer_id !== null &&
                    selectedCandidateId === message.generated_answer_id;

                  return (
                    <div
                      key={message.id}
                      className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[88%] rounded-[28px] border p-4 text-sm leading-7 shadow-sm ${
                          message.role === "user"
                            ? "border-emerald-200 bg-[linear-gradient(180deg,#ecfdf5_0%,#d1fae5_100%)] text-emerald-950"
                            : "border-border bg-white text-muted-foreground"
                        }`}
                      >
                        <div className="mb-2 flex flex-wrap items-center gap-2">
                          <Badge variant={message.role === "user" ? "success" : "muted"}>
                            {message.role === "user" ? "专家输入" : "LLM输出"}
                          </Badge>
                          {message.target_answer_id ? (
                            <Badge variant="warning">基于答案 #{message.target_answer_id}</Badge>
                          ) : null}
                          {message.generated_answer_id ? (
                            <Badge variant="success">
                              生成候选 #{message.generated_answer_id}
                            </Badge>
                          ) : null}
                          <span className="text-xs text-muted-foreground">
                            {formatDate(message.created_at)}
                          </span>
                        </div>
                        <div className="whitespace-pre-wrap">{message.content}</div>
                        {messageCandidate ? (
                          <div className="mt-4 rounded-[24px] border border-border bg-stone-50 p-4">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div className="flex flex-wrap gap-2">
                                <Badge variant="success">候选答案 #{messageCandidate.id}</Badge>
                                <Badge variant="muted">v{messageCandidate.version_no}</Badge>
                                {messageCandidate.parent_answer_id ? (
                                  <Badge variant="muted">
                                    基于 #{messageCandidate.parent_answer_id}
                                  </Badge>
                                ) : null}
                              </div>
                              <Button
                                size="sm"
                                variant={isMessageCandidateSelected ? "default" : "secondary"}
                                onClick={() => setSelectedCandidateId(messageCandidate.id)}
                              >
                                {isMessageCandidateSelected ? "当前已选中" : "选为提交答案"}
                              </Button>
                            </div>
                            <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-muted-foreground">
                              {messageCandidate.answer_text}
                            </p>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
              )}
            </div>

            <div className="border-t border-border bg-[linear-gradient(180deg,#fafaf9_0%,#f5f5f4_100%)] px-6 py-4">
              <div className="rounded-[28px] border border-border bg-white p-4 shadow-sm">
                <textarea
                  ref={llmTextareaRef}
                  className="field-textarea"
                  placeholder="告诉 LLM 你觉得哪里还不好，例如：第二句太绝对，请改得更保守，并补充适用前提。"
                  value={llmPrompt}
                  onChange={(event) => setLlmPrompt(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    if (!llmBusy) {
                      void handleLlmAssist();
                    }
                  }
                }}
                />
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                  <Button size="sm" disabled={llmBusy} onClick={() => void handleLlmAssist()}>
                    {llmBusy ? "发送中…" : "发送给 LLM"}
                  </Button>
              </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
