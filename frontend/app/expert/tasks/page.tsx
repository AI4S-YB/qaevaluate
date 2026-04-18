"use client";

import type { Route } from "next";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiFetch, type ExpertTaskListItem, type TaxonomyItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function parseBusinessTags(value: string | null) {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as string[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

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
  return value.replace("T", " ").slice(5, 16);
}

function compactTags(tagsJson: string | null) {
  const tags = parseBusinessTags(tagsJson);
  return {
    visible: tags.slice(0, 2),
    remaining: Math.max(tags.length - 2, 0)
  };
}

export default function ExpertTasksPage() {
  const [tasks, setTasks] = useState<ExpertTaskListItem[]>([]);
  const [technicalTypes, setTechnicalTypes] = useState<TaxonomyItem[]>([]);
  const [businessTags, setBusinessTags] = useState<TaxonomyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("pending_active");
  const [technicalTypeFilter, setTechnicalTypeFilter] = useState("all");
  const [businessTagFilter, setBusinessTagFilter] = useState("all");

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

  async function loadTaxonomy() {
    try {
      const [technicalTypeData, businessTagData] = await Promise.all([
        apiFetch<TaxonomyItem[]>("/api/admin/technical-types"),
        apiFetch<TaxonomyItem[]>("/api/admin/business-tags")
      ]);
      setTechnicalTypes(technicalTypeData.filter((item) => item.is_active));
      setBusinessTags(businessTagData.filter((item) => item.is_active));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载分类配置失败");
    }
  }

  useEffect(() => {
    void loadTasks();
    void loadTaxonomy();
  }, []);

  const filteredTasks = useMemo(() => {
    const keyword = filter.trim().toLowerCase();
    return [...tasks]
      .filter((task) => {
      const matchedKeyword =
        !keyword ||
        task.application_name.toLowerCase().includes(keyword) ||
        (task.technical_type_name ?? "").toLowerCase().includes(keyword) ||
        task.question_summary.toLowerCase().includes(keyword) ||
        parseBusinessTags(task.business_tags_json).some((tag) =>
          tag.toLowerCase().includes(keyword)
        ) ||
        taskStatusLabel(task.status).toLowerCase().includes(keyword);
      if (!matchedKeyword) return false;
      if (
        statusFilter === "pending_active" &&
        !["pending", "in_progress"].includes(task.status)
      ) {
        return false;
      }
      if (
        statusFilter !== "all" &&
        statusFilter !== "pending_active" &&
        task.status !== statusFilter
      ) {
        return false;
      }
      if (technicalTypeFilter !== "all" && task.technical_type_code !== technicalTypeFilter) {
        return false;
      }
      if (
        businessTagFilter !== "all" &&
        !parseBusinessTags(task.business_tags_json).includes(businessTagFilter)
      ) {
        return false;
      }
      return true;
      })
      .sort((left, right) => {
        const priority = (task: ExpertTaskListItem) => {
          let score = 0;
          if (task.task_type === "dispute_review") score -= 20;
          if (task.status === "in_progress") score -= 10;
          if (task.status === "pending") score -= 5;
          return score;
        };
        return priority(left) - priority(right) || right.id - left.id;
      });
  }, [businessTagFilter, filter, statusFilter, tasks, technicalTypeFilter]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4">
        <div>
          <p className="text-sm text-muted-foreground">任务列表</p>
          <h2 className="mt-2 font-serif text-4xl">先选业务类型和技术类型，再批量处理任务</h2>
        </div>
        <div className="grid gap-3 lg:grid-cols-[1fr_180px_180px_160px_120px]">
          <input
            className="field"
            placeholder="搜索问题、应用或状态"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
          <select
            className="field"
            value={technicalTypeFilter}
            onChange={(event) => setTechnicalTypeFilter(event.target.value)}
          >
            <option value="all">全部技术类型</option>
            {technicalTypes.map((item) => (
              <option key={item.id} value={item.code}>
                {item.name}
              </option>
            ))}
          </select>
          <select
            className="field"
            value={businessTagFilter}
            onChange={(event) => setBusinessTagFilter(event.target.value)}
          >
            <option value="all">全部业务类型</option>
            {businessTags.map((item) => (
              <option key={item.id} value={item.code}>
                {item.name}
              </option>
            ))}
          </select>
          <select
            className="field"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="pending_active">待处理 + 处理中</option>
            <option value="all">全部状态</option>
            <option value="pending">待处理</option>
            <option value="in_progress">处理中</option>
            <option value="submitted">已提交</option>
            <option value="expired">已过期</option>
            <option value="cancelled">已取消</option>
          </select>
          <Button variant="secondary" onClick={() => void loadTasks()}>
            刷新列表
          </Button>
        </div>
        <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
          <span>当前 {filteredTasks.length} 条任务</span>
          <span>·</span>
          <span>业务类型: {businessTagFilter === "all" ? "全部" : businessTagFilter}</span>
          <span>·</span>
          <span>技术类型: {technicalTypeFilter === "all" ? "全部" : technicalTypeFilter}</span>
          <span>·</span>
          <span>
            状态:
            {statusFilter === "pending_active"
              ? " 待处理 + 处理中"
              : statusFilter === "all"
                ? " 全部"
                : ` ${taskStatusLabel(statusFilter as ExpertTaskListItem["status"])}`}
          </span>
          <span>·</span>
          <span>排序: 争议复核优先，其次处理中</span>
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

          {filteredTasks.length > 0 ? (
            <div className="hidden grid-cols-[110px_140px_minmax(0,1fr)_90px_110px_80px] gap-3 border-b border-border px-3 pb-2 text-[11px] font-medium tracking-[0.16em] text-muted-foreground lg:grid">
              <span>ID</span>
              <span>分类</span>
              <span>问题</span>
              <span>任务</span>
              <span>状态</span>
              <span>操作</span>
            </div>
          ) : null}

          {filteredTasks.map((task) => (
            <div
              key={task.id}
              className="grid gap-3 rounded-[18px] border border-border bg-stone-50 px-3 py-2.5 lg:grid-cols-[110px_140px_minmax(0,1fr)_90px_110px_80px] lg:items-center"
            >
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                  Task #{task.id}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatDate(task.expires_at ?? task.assigned_at)}
                </p>
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm">{task.application_name}</p>
                {task.technical_type_name ? (
                  <p className="truncate text-xs text-muted-foreground">
                    {task.technical_type_name}
                  </p>
                ) : null}
              </div>
              <div className="min-w-0 space-y-1.5">
                <p className="truncate text-sm font-medium">{task.question_summary}</p>
                <div className="flex flex-wrap gap-2">
                  {compactTags(task.business_tags_json).visible.map((tag) => (
                    <Badge
                      key={`${task.id}-${tag}`}
                      variant="muted"
                      className="px-2 py-0.5 text-[11px]"
                    >
                      {tag}
                    </Badge>
                  ))}
                  {compactTags(task.business_tags_json).remaining > 0 ? (
                    <Badge variant="muted" className="px-2 py-0.5 text-[11px]">
                      +{compactTags(task.business_tags_json).remaining}
                    </Badge>
                  ) : null}
                </div>
              </div>
              <div className="flex justify-start lg:justify-center">
                <Badge
                  variant={task.task_type === "dispute_review" ? "warning" : "muted"}
                  className="px-2 py-0.5 text-[11px]"
                >
                  {taskTypeLabel(task.task_type)}
                </Badge>
              </div>
              <div className="space-y-1">
                <Badge
                  variant={task.status === "submitted" ? "success" : "default"}
                  className="px-2 py-0.5 text-[11px]"
                >
                  {taskStatusLabel(task.status)}
                </Badge>
              </div>
              <div className="flex items-center justify-end">
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
