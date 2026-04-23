"use client";

import type { Route } from "next";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  apiFetch,
  type ExpertHistoryItem,
  type ExpertTaskListItem,
  type MeProfile
} from "@/lib/api";
import { MetricCard } from "@/components/metric-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function decisionLabel(value: string) {
  if (value === "pass") return "通过";
  if (value === "rewrite") return "待改写";
  if (value === "fail") return "不通过";
  return value;
}

function decisionVariant(value: string) {
  if (value === "pass") return "success";
  if (value === "rewrite") return "warning";
  if (value === "fail") return "muted";
  return "default";
}

function taskTypeLabel(taskType: ExpertTaskListItem["task_type"]) {
  if (taskType === "dispute_review") return "争议复核";
  if (taskType === "final_confirm") return "最终确认";
  return "初评";
}

function formatTime(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

function parseBusinessTags(value: string | null) {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as string[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default function ExpertDashboardPage() {
  const [profile, setProfile] = useState<MeProfile | null>(null);
  const [tasks, setTasks] = useState<ExpertTaskListItem[]>([]);
  const [history, setHistory] = useState<ExpertHistoryItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      setError(null);
      try {
        const [me, taskList, historyList] = await Promise.all([
          apiFetch<MeProfile>("/api/me"),
          apiFetch<ExpertTaskListItem[]>("/api/expert/tasks"),
          apiFetch<ExpertHistoryItem[]>("/api/expert/history")
        ]);
        setProfile(me);
        setTasks(taskList);
        setHistory(historyList);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载工作台失败");
      }
    }
    void loadData();
  }, []);

  const pendingTasks = useMemo(
    () => tasks.filter((task) => task.status === "pending"),
    [tasks]
  );
  const activeTasks = useMemo(
    () => tasks.filter((task) => task.status === "in_progress"),
    [tasks]
  );
  const disputeTasks = useMemo(
    () => tasks.filter((task) => task.task_type === "dispute_review"),
    [tasks]
  );
  const rewriteHistory = useMemo(
    () => history.filter((item) => item.overall_decision === "rewrite"),
    [history]
  );
  const adoptedFinalHistory = useMemo(
    () => history.filter((item) => item.adopted_became_final),
    [history]
  );
  const priorityTasks = useMemo(() => {
    return [...tasks].sort((left, right) => {
      const leftScore =
        (left.status === "in_progress" ? 0 : 1) + (left.task_type === "dispute_review" ? -1 : 0);
      const rightScore =
        (right.status === "in_progress" ? 0 : 1) +
        (right.task_type === "dispute_review" ? -1 : 0);
      return leftScore - rightScore || right.id - left.id;
    });
  }, [tasks]);

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">专家工作台</p>
          <h2 className="mt-2 font-serif text-4xl">
            {profile ? `${profile.full_name} 的评测首页` : "今日评测焦点"}
          </h2>
          {profile ? (
            <div className="mt-4 space-y-3">
              <div className="flex flex-wrap gap-2">
                {profile.applications.length ? (
                  profile.applications.map((item) => (
                    <Badge key={item.id} variant="muted">
                      项目: {item.name}
                    </Badge>
                  ))
                ) : (
                  <Badge variant="muted">项目: 未配置</Badge>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {profile.business_tags.length ? (
                  profile.business_tags.map((item) => (
                    <Badge key={item.id} variant="warning">
                      领域场景: {item.name}
                    </Badge>
                  ))
                ) : (
                  <Badge variant="warning">领域场景: 未配置</Badge>
                )}
                <Badge variant="default">当前任务: {tasks.length}</Badge>
                {profile.organization ? <Badge variant="muted">{profile.organization}</Badge> : null}
              </div>
            </div>
          ) : null}
        </div>
        <div className="flex gap-3">
          <Button asChild>
            <Link href="/expert/tasks">开始评测</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link href="/expert/imports">上传 QA</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link href="/expert/model-trial">模型试用</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link href="/expert/history">查看历史</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link href="/expert/profile">维护资料</Link>
          </Button>
        </div>
      </section>

      {error ? (
        <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {error}
        </div>
      ) : null}

      <section className="section-grid">
        <MetricCard label="待处理任务" value={String(pendingTasks.length)} note="等待你开始评测" />
        <MetricCard label="处理中任务" value={String(activeTasks.length)} note="建议优先完成提交" />
        <MetricCard label="待改写历史" value={String(rewriteHistory.length)} note="你曾判定需改写的题目" />
        <MetricCard label="被最终采纳" value={String(adoptedFinalHistory.length)} note="你选中的候选答案已成最终标准" />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <Card className="border-none bg-[linear-gradient(135deg,rgba(255,250,245,0.96),rgba(255,255,255,0.96)_55%,rgba(241,245,249,0.92))] ring-1 ring-stone-200">
          <CardHeader>
            <CardTitle>今日优先处理</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {priorityTasks.slice(0, 4).map((task) => (
              <div
                key={task.id}
                className="flex flex-col gap-3 rounded-[28px] border border-border bg-white/85 p-4 lg:flex-row lg:items-center lg:justify-between"
              >
                <div className="space-y-1">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="muted">{task.application_name}</Badge>
                    {task.technical_type_name ? (
                      <Badge variant="warning">{task.technical_type_name}</Badge>
                    ) : null}
                    <Badge variant={task.task_type === "dispute_review" ? "warning" : "default"}>
                      {taskTypeLabel(task.task_type)}
                    </Badge>
                    <Badge variant={task.status === "in_progress" ? "success" : "muted"}>
                      {task.status}
                    </Badge>
                    {parseBusinessTags(task.business_tags_json).map((tag) => (
                      <Badge key={`${task.id}-${tag}`} variant="muted">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                  <p className="font-medium">{task.question_summary}</p>
                </div>
                <Button asChild size="sm" variant="secondary">
                  <Link href={`/expert/tasks/${task.id}` as Route}>
                    {task.status === "in_progress" ? "继续评测" : "打开任务"}
                  </Link>
                </Button>
              </div>
            ))}
            {tasks.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                当前还没有分配到你的任务。
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="bg-stone-50">
          <CardHeader>
            <CardTitle>工作提示</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-7 text-muted-foreground">
            <p>优先处理 `in_progress` 任务，避免同一题长时间停在草稿状态。</p>
            <p>争议复核题优先级高于普通初评，建议先完成这类任务。</p>
            <p>若结论为待改写，尽量确认一条候选答案，便于后续聚合收敛。</p>
            <p>被最终采纳的记录可以回看你的判断习惯，逐步稳定标准。</p>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <Card>
          <CardHeader className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <CardTitle>最近提交</CardTitle>
            <Button asChild size="sm" variant="secondary">
              <Link href="/expert/history">查看全部历史</Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {history.slice(0, 4).map((item) => (
              <div
                key={item.id}
                className="rounded-[28px] border border-border bg-stone-50 p-4"
              >
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="muted">{item.application_name}</Badge>
                      <Badge variant={decisionVariant(item.overall_decision)}>
                        {decisionLabel(item.overall_decision)}
                      </Badge>
                      {item.adopted_became_final ? (
                        <Badge variant="success">最终被采纳</Badge>
                      ) : null}
                    </div>
                    <p className="mt-3 font-medium">{item.question_summary}</p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {formatTime(item.submitted_at)} / {item.llm_session_count} 次 LLM 辅助
                    </p>
                  </div>
                  <Button asChild size="sm" variant="secondary">
                    <Link href={`/expert/tasks/${item.task_id}` as Route}>查看任务</Link>
                  </Button>
                </div>
              </div>
            ))}
            {history.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                当前还没有已提交的历史记录。
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>被采纳的改写记录</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {adoptedFinalHistory.slice(0, 3).map((item) => (
              <div
                key={item.id}
                className="rounded-[28px] border border-border bg-stone-50 p-4"
              >
                <div className="mb-3 flex flex-wrap gap-2">
                  <Badge variant="success">最终被采纳</Badge>
                  <Badge variant="muted">{item.application_name}</Badge>
                </div>
                <p className="font-medium">{item.question_summary}</p>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">
                  {item.adopted_rewrite_answer_text || "该记录未返回候选答案文本。"}
                </p>
              </div>
            ))}
            {adoptedFinalHistory.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                目前还没有你选中的候选答案进入最终标准答案。
              </div>
            ) : null}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[0.88fr_1.12fr]">
        <Card>
          <CardHeader>
            <CardTitle>争议与改写提醒</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-[24px] border border-border bg-stone-50 p-4">
              <p className="text-sm text-muted-foreground">争议复核任务</p>
              <p className="mt-2 text-3xl font-semibold">{disputeTasks.length}</p>
            </div>
            <div className="rounded-[24px] border border-border bg-stone-50 p-4">
              <p className="text-sm text-muted-foreground">待改写历史</p>
              <p className="mt-2 text-3xl font-semibold">{rewriteHistory.length}</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>最近需要关注的题</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {[...disputeTasks, ...activeTasks].slice(0, 4).map((task) => (
              <div
                key={`focus-${task.id}`}
                className="flex items-center justify-between rounded-[24px] border border-border bg-stone-50 p-4"
              >
                <div>
                  <p className="text-sm text-muted-foreground">{task.application_name}</p>
                  <p className="font-medium">{task.question_summary}</p>
                </div>
                <Button asChild size="sm" variant="secondary">
                  <Link href={`/expert/tasks/${task.id}` as Route}>处理</Link>
                </Button>
              </div>
            ))}
            {disputeTasks.length === 0 && activeTasks.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                当前没有需要特别优先关注的题目。
              </div>
            ) : null}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
