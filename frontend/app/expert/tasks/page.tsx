"use client";

import type { Route } from "next";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiFetch, type ExpertTaskListItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function taskTypeLabel(taskType: ExpertTaskListItem["task_type"]) {
  return taskType === "dispute_review" ? "争议复核" : "初评";
}

function taskStatusLabel(status: ExpertTaskListItem["status"]) {
  if (status === "in_progress") return "处理中";
  if (status === "submitted") return "已提交";
  if (status === "expired") return "已过期";
  if (status === "cancelled") return "已取消";
  return "待处理";
}

function formatDate(value: string | null) {
  if (!value) return "未设置";
  return value.replace("T", " ").slice(0, 16);
}

export default function ExpertTasksPage() {
  const [tasks, setTasks] = useState<ExpertTaskListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  async function loadTasks() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<ExpertTaskListItem[]>("/api/expert/tasks");
      setTasks(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载任务失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadTasks();
  }, []);

  const filteredTasks = useMemo(() => {
    const keyword = filter.trim().toLowerCase();
    if (!keyword) return tasks;
    return tasks.filter((task) => {
      return (
        task.application_name.toLowerCase().includes(keyword) ||
        task.question_summary.toLowerCase().includes(keyword) ||
        taskStatusLabel(task.status).toLowerCase().includes(keyword)
      );
    });
  }, [filter, tasks]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">任务列表</p>
          <h2 className="mt-2 font-serif text-4xl">按应用和优先级处理待评 QA</h2>
        </div>
        <div className="flex gap-3">
          <input
            className="field max-w-[260px]"
            placeholder="筛选应用、问题或状态"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
          <Button variant="secondary" onClick={() => void loadTasks()}>
            刷新列表
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <CardTitle>当前任务</CardTitle>
          <p className="text-sm text-muted-foreground">
            {loading ? "正在加载…" : `共 ${filteredTasks.length} 条任务`}
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          {error ? (
            <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              {error}
            </div>
          ) : null}

          {!loading && filteredTasks.length === 0 ? (
            <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
              暂无可显示任务。可先在管理端触发分发，或运行 seed 数据生成初始任务。
            </div>
          ) : null}

          {filteredTasks.map((task) => (
            <div
              key={task.id}
              className="grid gap-4 rounded-[28px] border border-border bg-stone-50 p-4 lg:grid-cols-[160px_1fr_120px_120px_150px]"
            >
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                  Task #{task.id}
                </p>
                <p className="mt-1 text-sm">{task.application_name}</p>
              </div>
              <p className="font-medium">{task.question_summary}</p>
              <Badge variant={task.task_type === "dispute_review" ? "warning" : "muted"}>
                {taskTypeLabel(task.task_type)}
              </Badge>
              <Badge variant={task.status === "submitted" ? "success" : "default"}>
                {taskStatusLabel(task.status)}
              </Badge>
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm text-muted-foreground">
                  {formatDate(task.expires_at ?? task.assigned_at)}
                </span>
                <Button asChild size="sm">
                  <Link href={`/expert/tasks/${task.id}` as Route}>打开</Link>
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
