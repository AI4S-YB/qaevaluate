"use client";

import { useEffect, useMemo, useState } from "react";

import {
  API_BASE_URL,
  apiFetch,
  getStoredAuthToken,
  type TrialLlmConfigOption,
  type TrialMessage,
  type TrialSessionDetail,
  type TrialSessionListItem,
  type TrialSourceItem
} from "@/lib/api";
import { MarkdownContent } from "@/components/markdown-content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatTime(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

function taskTypeLabel(taskType: TrialSourceItem["task_type"]) {
  if (taskType === "dispute_review") return "争议复核";
  if (taskType === "final_confirm") return "最终确认";
  return "初评";
}

export default function ExpertModelTrialPage() {
  const [configs, setConfigs] = useState<TrialLlmConfigOption[]>([]);
  const [sources, setSources] = useState<TrialSourceItem[]>([]);
  const [sessions, setSessions] = useState<TrialSessionListItem[]>([]);
  const [selectedConfigId, setSelectedConfigId] = useState<number | null>(null);
  const [selectedSourceKey, setSelectedSourceKey] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [detail, setDetail] = useState<TrialSessionDetail | null>(null);
  const [composer, setComposer] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [sending, setSending] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadBaseData() {
    setLoading(true);
    setError(null);
    try {
      const [configData, sourceData, sessionData] = await Promise.all([
        apiFetch<TrialLlmConfigOption[]>("/api/expert/model-trial/configs"),
        apiFetch<TrialSourceItem[]>("/api/expert/model-trial/sources"),
        apiFetch<TrialSessionListItem[]>("/api/expert/model-trial/sessions")
      ]);
      setConfigs(configData);
      setSources(sourceData);
      setSessions(sessionData);
      setSelectedConfigId((current) => current ?? configData[0]?.id ?? null);
      setSelectedSessionId((current) => current ?? sessionData[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载模型试用页失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadSessionDetail(sessionId: number) {
    try {
      const data = await apiFetch<TrialSessionDetail>(`/api/expert/model-trial/sessions/${sessionId}`);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载会话详情失败");
    }
  }

  useEffect(() => {
    void loadBaseData();
  }, []);

  useEffect(() => {
    if (!selectedSessionId) {
      setDetail(null);
      return;
    }
    void loadSessionDetail(selectedSessionId);
  }, [selectedSessionId]);

  const selectedSource = useMemo(() => {
    if (!selectedSourceKey) return null;
    return sources.find((item) => `${item.qa_item_id}:${item.answer_id}` === selectedSourceKey) ?? null;
  }, [selectedSourceKey, sources]);

  const selectedConfig = useMemo(
    () => configs.find((item) => item.id === selectedConfigId) ?? null,
    [configs, selectedConfigId]
  );

  async function createSession() {
    if (!selectedConfigId) {
      throw new Error("请先选择一个开放试用的模型");
    }
    setCreating(true);
    setError(null);
    setNotice(null);
    try {
      const result = await apiFetch<{ session_id: number }>("/api/expert/model-trial/sessions", {
        method: "POST",
        body: JSON.stringify({
          llm_config_id: selectedConfigId,
          source_qa_item_id: selectedSource?.qa_item_id ?? null,
          source_answer_id: selectedSource?.answer_id ?? null,
          title: selectedSource?.question_summary ?? null
        })
      });
      await loadBaseData();
      setSelectedSessionId(result.session_id);
      setNotice("新试用会话已创建。");
      return result.session_id;
    } finally {
      setCreating(false);
    }
  }

  async function handleSend() {
    const content = composer.trim();
    if (!content) {
      setError("请输入要测试模型的问题或指令");
      return;
    }
    let liveSessionId: number | null = selectedSessionId;
    setSending(true);
    setError(null);
    setNotice(null);
    try {
      const sessionId = selectedSessionId ?? (await createSession());
      liveSessionId = sessionId;
      const authToken = getStoredAuthToken();
      const now = new Date().toISOString();
      const tempUserMessageId = -Date.now();
      const tempAssistantMessageId = tempUserMessageId - 1;

      setSelectedSessionId(sessionId);
      setDetail((current) => {
        const baseDetail =
          current && current.session.id === sessionId
            ? current
            : {
                session: {
                  id: sessionId,
                  llm_config_id: selectedConfigId ?? 0,
                  llm_config_name: selectedConfig?.name ?? null,
                  llm_model_name: selectedConfig?.model_name ?? null,
                  title: selectedSource?.question_summary ?? selectedConfig?.name ?? `会话 #${sessionId}`,
                  status: "active" as const,
                  created_at: now,
                  updated_at: now
                },
                source: selectedSource
                  ? {
                      qa_item_id: selectedSource.qa_item_id,
                      answer_id: selectedSource.answer_id,
                      question_text: selectedSource.question_text,
                      answer_text: selectedSource.answer_text,
                      context_text: selectedSource.context_text,
                      application_name: selectedSource.application_name,
                      technical_type_code: selectedSource.technical_type_code,
                      technical_type_name: selectedSource.technical_type_name,
                      question_summary: selectedSource.question_summary
                    }
                  : null,
                messages: []
              };
        return {
          ...baseDetail,
          session: {
            ...baseDetail.session,
            status: "active",
            updated_at: now
          },
          messages: [
            ...baseDetail.messages,
            {
              id: tempUserMessageId,
              role: "user",
              content,
              created_at: now
            },
            {
              id: tempAssistantMessageId,
              role: "assistant",
              content: "",
              created_at: now
            }
          ]
        };
      });

      const response = await fetch(
        `${API_BASE_URL}/api/expert/model-trial/sessions/${sessionId}/stream`,
        {
          method: "POST",
          headers: {
            ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ content }),
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
            const chunk = typeof eventPayload.content === "string" ? eventPayload.content : "";
            if (!chunk) continue;
            streamedAssistantText += chunk;
            setDetail((current) => {
              if (!current || current.session.id !== sessionId) return current;
              return {
                ...current,
                messages: current.messages.map((message) =>
                  message.id === tempAssistantMessageId
                    ? { ...message, content: streamedAssistantText }
                    : message
                )
              };
            });
          }

          if (eventName === "error") {
            throw new Error(
              typeof eventPayload.detail === "string"
                ? eventPayload.detail
                : "模型试用流式请求失败"
            );
          }
        }
      }

      setComposer("");
      await Promise.all([loadBaseData(), loadSessionDetail(sessionId)]);
      setSelectedSessionId(sessionId);
      setNotice("模型已流式完成。");
    } catch (err) {
      if (liveSessionId) {
        await Promise.all([loadBaseData(), loadSessionDetail(liveSessionId)]);
      }
      setError(err instanceof Error ? err.message : "模型试用失败");
    } finally {
      setSending(false);
    }
  }

  async function handleDeleteSession(sessionId: number) {
    setDeletingId(sessionId);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/expert/model-trial/sessions/${sessionId}`, { method: "DELETE" });
      const nextSessions = sessions.filter((item) => item.id !== sessionId);
      setSessions(nextSessions);
      if (selectedSessionId === sessionId) {
        setSelectedSessionId(nextSessions[0]?.id ?? null);
        if (nextSessions.length === 0) {
          setDetail(null);
        }
      }
      setNotice(`会话 #${sessionId} 已删除。`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除会话失败");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-3 border-b border-border pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm uppercase tracking-[0.16em] text-muted-foreground">Model Trial</p>
          <h2 className="mt-2 font-serif text-4xl">模型试用工作台</h2>
          <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground">
            这里用于检查训练或微调模型的问答表现，不进入正式 QA 评测。试用模型与评测模型完全隔离。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={creating || !selectedConfigId} onClick={() => void createSession()}>
            {creating ? "创建中…" : "新建试用会话"}
          </Button>
          <Button variant="secondary" onClick={() => void loadBaseData()}>
            刷新
          </Button>
        </div>
      </section>

      {error ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {notice}
        </div>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[300px_1fr]">
        <Card className="rounded-lg border border-border shadow-none">
          <CardHeader className="border-b border-border bg-stone-50">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-xl">会话列表</CardTitle>
              <span className="text-xs text-muted-foreground">{sessions.length} 条</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 p-3">
            {sessions.map((session) => (
              <div
                key={session.id}
                className={`rounded-md border px-3 py-3 ${
                  selectedSessionId === session.id
                    ? "border-stone-900 bg-stone-900 text-white"
                    : "border-border bg-white"
                }`}
              >
                <button
                  type="button"
                  className="w-full text-left"
                  onClick={() => setSelectedSessionId(session.id)}
                >
                  <p className="line-clamp-2 text-sm font-medium">{session.title}</p>
                  <p className="mt-2 text-xs opacity-80">
                    {session.llm_config_name || "未命名模型"} / {formatTime(session.updated_at)}
                  </p>
                </button>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <Badge variant={selectedSessionId === session.id ? "default" : "muted"}>
                    {session.status}
                  </Badge>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={deletingId === session.id}
                    onClick={() => void handleDeleteSession(session.id)}
                  >
                    {deletingId === session.id ? "删除中…" : "删除"}
                  </Button>
                </div>
              </div>
            ))}
            {!loading && sessions.length === 0 ? (
              <div className="rounded-md border border-dashed border-border bg-stone-50 px-4 py-6 text-sm text-muted-foreground">
                还没有试用会话。先在右侧选模型和题目来源，再开始一轮对话。
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="rounded-lg border border-border shadow-none">
          <CardHeader className="border-b border-border bg-white pb-4">
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <CardTitle className="text-xl">对话测试</CardTitle>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {detail?.session.title || "尚未开始会话"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {detail?.session.llm_config_name ? (
                    <Badge variant="warning">{detail.session.llm_config_name}</Badge>
                  ) : null}
                  {detail?.session.llm_model_name ? (
                    <Badge variant="muted">{detail.session.llm_model_name}</Badge>
                  ) : null}
                  {detail?.session.status ? <Badge variant="default">{detail.session.status}</Badge> : null}
                </div>
              </div>

              <div className="grid gap-3 xl:grid-cols-[1.1fr_1.4fr_auto]">
                <div className="space-y-1">
                  <label className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
                    试用模型
                  </label>
                  <select
                    className="field rounded-md"
                    value={selectedConfigId ?? ""}
                    onChange={(event) => setSelectedConfigId(Number(event.target.value) || null)}
                  >
                    <option value="">请选择模型</option>
                    {configs.map((config) => (
                      <option key={config.id} value={config.id}>
                        {config.name} / {config.model_name}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground">
                    {selectedConfig
                      ? `${selectedConfig.provider_code} / ${
                          selectedConfig.last_tested_at
                            ? `最近检测 ${formatTime(selectedConfig.last_tested_at)}`
                            : "尚未检测"
                        }`
                      : "只显示管理员明确开放给模型试用的配置"}
                  </p>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
                    题目来源
                  </label>
                  <select
                    className="field rounded-md"
                    value={selectedSourceKey}
                    onChange={(event) => {
                      const nextValue = event.target.value;
                      setSelectedSourceKey(nextValue);
                      const nextSource = sources.find(
                        (item) => `${item.qa_item_id}:${item.answer_id}` === nextValue
                      );
                      if (nextSource && !composer.trim()) {
                        setComposer(nextSource.question_text);
                      }
                    }}
                  >
                    <option value="">不带题，直接自由对话</option>
                    {sources.map((source) => (
                      <option
                        key={`${source.qa_item_id}:${source.answer_id}`}
                        value={`${source.qa_item_id}:${source.answer_id}`}
                      >
                        {source.application_name} / {source.question_summary}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground">
                    当前先接你可见的任务 QA；后续会优先接到你自己上传的 QA。
                  </p>
                </div>

                <div className="flex items-end">
                  <Button className="w-full xl:w-auto" disabled={creating || !selectedConfigId} onClick={() => void createSession()}>
                    {creating ? "创建中…" : "开始会话"}
                  </Button>
                </div>
              </div>

              {selectedSource ? (
                <div className="border border-border bg-stone-50 px-4 py-4">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="muted">{selectedSource.application_name}</Badge>
                    <Badge variant="warning">
                      {selectedSource.technical_type_name || selectedSource.technical_type_code || "未分类"}
                    </Badge>
                    <Badge variant="default">{taskTypeLabel(selectedSource.task_type)}</Badge>
                    <Badge variant="muted">{selectedSource.task_status}</Badge>
                  </div>
                  <p className="mt-3 text-sm font-medium leading-7">{selectedSource.question_text}</p>
                  {selectedSource.context_text ? (
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">
                      {selectedSource.context_text}
                    </p>
                  ) : null}
                  <div className="mt-3 border-l-2 border-stone-300 pl-3 text-sm leading-6 text-muted-foreground">
                    <p className="font-medium text-foreground">参考答案</p>
                    <p className="mt-1">{selectedSource.answer_text}</p>
                  </div>
                </div>
              ) : null}
            </div>
          </CardHeader>

          <CardContent className="flex min-h-[720px] flex-col p-0">
            <div className="flex-1 overflow-y-auto bg-stone-50/40 px-5 py-5">
              {detail?.messages.length ? (
                <div className="space-y-4">
                  {detail.messages.map((message: TrialMessage) => (
                    <div
                      key={message.id}
                      className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[86%] border px-4 py-4 text-sm leading-7 shadow-sm ${
                          message.role === "user"
                            ? "border-stone-900 bg-stone-900 text-white"
                            : "border-border bg-white text-foreground"
                        }`}
                      >
                        <div className="mb-2 flex items-center justify-between gap-3 text-xs uppercase tracking-[0.08em] opacity-70">
                          <span>{message.role === "user" ? "User" : "Model"}</span>
                          <span>{formatTime(message.created_at)}</span>
                        </div>
                        {message.role === "assistant" ? (
                          <MarkdownContent content={message.content} />
                        ) : (
                          <p className="whitespace-pre-wrap">{message.content}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex h-full min-h-[360px] items-center justify-center border border-dashed border-border bg-white px-6 py-10 text-center text-sm text-muted-foreground">
                  选一个模型，必要时带一道 QA 题，然后直接开始对话。这里适合测回答质量、改写能力、术语稳定性和追问表现。
                </div>
              )}
            </div>

            <div className="border-t border-border bg-white px-5 py-5">
              <textarea
                className="field-textarea min-h-[150px] rounded-md"
                placeholder="输入你要测试模型的问题、追问或指令。若已选择题目来源，也可以直接围绕该 QA 做回答、分析、改写或多轮追问。"
                value={composer}
                onChange={(event) => setComposer(event.target.value)}
              />
              <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="text-sm text-muted-foreground">
                  {selectedSessionId
                    ? "当前将继续已有会话"
                    : "当前将按上方模型和题目来源创建新会话"}
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => setComposer("")}>
                    清空输入
                  </Button>
                  <Button disabled={sending || !selectedConfigId} onClick={() => void handleSend()}>
                    {sending ? "发送中…" : "发送给模型"}
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
