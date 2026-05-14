"use client";

import { useEffect, useState } from "react";

import { apiFetch, type AdminSystemStatus } from "@/lib/api";
import { MetricCard } from "@/components/metric-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatTime(value: string | null) {
  if (!value) return "未记录";
  return value.replace("T", " ").slice(0, 16);
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

function StatusBadge({
  label,
  tone
}: {
  label: string;
  tone: "default" | "success" | "warning" | "danger";
}) {
  const className =
    tone === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : tone === "danger"
          ? "border-rose-200 bg-rose-50 text-rose-700"
          : "border-border bg-background text-foreground";
  return <Badge className={className}>{label}</Badge>;
}

export default function AdminSystemStatusPage() {
  const [status, setStatus] = useState<AdminSystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadStatus() {
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch<AdminSystemStatus>("/api/admin/system-status");
        setStatus(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载系统状态失败");
      } finally {
        setLoading(false);
      }
    }
    void loadStatus();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">系统状态</p>
        <h2 className="mt-2 font-serif text-4xl">把模型、队列和备份放到同一个管理员视图里</h2>
      </div>

      {error ? (
        <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {error}
        </div>
      ) : null}

      <section className="section-grid">
        <MetricCard
          label="当前环境"
          value={status?.environment.app_env ?? (loading ? "加载中" : "未知")}
          note={status?.environment.database.exists ? "数据库文件已存在" : "数据库文件未发现"}
        />
        <MetricCard
          label="生效模型"
          value={status?.llm.active_config?.name ?? (loading ? "加载中" : "未配置")}
          note={status?.llm.active_config?.model_name ?? "当前没有激活中的 LLM 配置"}
        />
        <MetricCard
          label="待处理队列"
          value={String(
            (status?.queue.summary.pending ?? 0) + (status?.queue.summary.processing ?? 0)
          )}
          note={`pending ${status?.queue.summary.pending ?? 0} / processing ${status?.queue.summary.processing ?? 0}`}
        />
        <MetricCard
          label="最近备份"
          value={
            status?.backups.latest_file
              ? formatTime(status.backups.latest_file.updated_at)
              : loading
                ? "加载中"
                : "暂无"
          }
          note={
            status?.backups.latest_file
              ? `${status.backups.latest_file.name} · ${formatBytes(status.backups.latest_file.size_bytes)}`
              : "还没有检测到备份文件"
          }
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <Card>
          <CardHeader>
            <CardTitle>LLM 配置状态</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-3xl border border-border bg-stone-50 p-4 text-sm">
                <p className="text-muted-foreground">总配置数</p>
                <p className="mt-2 text-2xl font-semibold">{status?.llm.total_configs ?? 0}</p>
              </div>
              <div className="rounded-3xl border border-border bg-stone-50 p-4 text-sm">
                <p className="text-muted-foreground">检测通过</p>
                <p className="mt-2 text-2xl font-semibold">{status?.llm.passed_count ?? 0}</p>
              </div>
              <div className="rounded-3xl border border-border bg-stone-50 p-4 text-sm">
                <p className="text-muted-foreground">缺少 Key</p>
                <p className="mt-2 text-2xl font-semibold">
                  {status?.llm.missing_api_key_count ?? 0}
                </p>
              </div>
            </div>

            <div className="rounded-[28px] border border-border bg-stone-50 p-5">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-base font-medium">
                  {status?.llm.active_config?.name ?? "当前没有启用模型"}
                </p>
                {status?.llm.active_config ? <StatusBadge label="当前生效" tone="success" /> : null}
                {status?.llm.active_config?.last_test_status === "passed" ? (
                  <StatusBadge label="检测通过" tone="success" />
                ) : null}
                {status?.llm.active_config?.last_test_status === "failed" ? (
                  <StatusBadge label="检测失败" tone="danger" />
                ) : null}
                {status?.llm.active_config && !status.llm.active_config.has_api_key ? (
                  <StatusBadge label="缺少 Key" tone="warning" />
                ) : null}
              </div>
              <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                <p>模型：{status?.llm.active_config?.model_name ?? "未配置"}</p>
                <p>Base URL：{status?.llm.active_config?.base_url ?? "未配置"}</p>
                <p>最近检测：{formatTime(status?.llm.active_config?.last_tested_at ?? null)}</p>
                {status?.llm.active_config?.last_test_latency_ms ? (
                  <p>检测耗时：{status.llm.active_config.last_test_latency_ms} ms</p>
                ) : null}
              </div>
            </div>

            <div className="space-y-3">
              {(status?.llm.configs ?? []).map((config) => (
                <div
                  key={config.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-border bg-white p-4"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{config.name}</p>
                      {config.is_active ? <StatusBadge label="生效中" tone="success" /> : null}
                      {config.last_test_status === "passed" ? (
                        <StatusBadge label="通过" tone="success" />
                      ) : null}
                      {config.last_test_status === "failed" ? (
                        <StatusBadge label="失败" tone="danger" />
                      ) : null}
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {config.model_name} · {config.base_url}
                    </p>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {formatTime(config.last_tested_at)}
                  </p>
                </div>
              ))}
              {!loading && (status?.llm.configs.length ?? 0) === 0 ? (
                <div className="rounded-3xl border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                  当前没有模型配置。
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>队列状态</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-3xl border border-border bg-stone-50 p-4">
                  <p className="text-sm text-muted-foreground">Pending</p>
                  <p className="mt-2 text-2xl font-semibold">{status?.queue.summary.pending ?? 0}</p>
                </div>
                <div className="rounded-3xl border border-border bg-stone-50 p-4">
                  <p className="text-sm text-muted-foreground">Failed</p>
                  <p className="mt-2 text-2xl font-semibold">{status?.queue.summary.failed ?? 0}</p>
                </div>
                <div className="rounded-3xl border border-border bg-stone-50 p-4">
                  <p className="text-sm text-muted-foreground">Processing</p>
                  <p className="mt-2 text-2xl font-semibold">
                    {status?.queue.summary.processing ?? 0}
                  </p>
                </div>
                <div className="rounded-3xl border border-border bg-stone-50 p-4">
                  <p className="text-sm text-muted-foreground">Done</p>
                  <p className="mt-2 text-2xl font-semibold">{status?.queue.summary.done ?? 0}</p>
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium">最近失败任务</p>
                {(status?.queue.recent_failed_jobs ?? []).map((job) => (
                  <div key={job.job_id} className="rounded-3xl border border-rose-200 bg-rose-50 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-mono text-xs text-rose-900">{job.job_id}</p>
                      <p className="text-xs text-rose-700">{job.type}</p>
                    </div>
                    <p className="mt-1 text-xs text-rose-700">{job.error ?? "无错误详情"}</p>
                  </div>
                ))}
                {!loading && (status?.queue.recent_failed_jobs.length ?? 0) === 0 ? (
                  <div className="rounded-3xl border border-dashed border-border bg-stone-50 p-4 text-sm text-muted-foreground">
                    当前没有失败任务。
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>备份与运行文件</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-[28px] border border-border bg-stone-50 p-5 text-sm text-muted-foreground">
                <p>数据库：{status?.environment.database.exists ? "已就绪" : "未发现文件"}</p>
                <p className="mt-2 break-all font-mono text-xs text-foreground">
                  {status?.environment.database.path ?? "-"}
                </p>
                <p className="mt-2">数据库大小：{formatBytes(status?.environment.database.size_bytes ?? 0)}</p>
                <p className="mt-2">运行目录文件：上传 {status?.environment.runtime.uploads_count ?? 0} / 导出 {status?.environment.runtime.exports_count ?? 0}</p>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium">最近备份文件</p>
                {(status?.backups.files ?? []).map((file) => (
                  <div
                    key={`${file.name}-${file.updated_at}`}
                    className="flex items-center justify-between gap-3 rounded-3xl border border-border bg-white px-4 py-3 text-sm"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium">{file.name}</p>
                      <p className="text-xs text-muted-foreground">{formatTime(file.updated_at)}</p>
                    </div>
                    <p className="shrink-0 text-xs text-muted-foreground">
                      {formatBytes(file.size_bytes)}
                    </p>
                  </div>
                ))}
                {!loading && (status?.backups.files.length ?? 0) === 0 ? (
                  <div className="rounded-3xl border border-dashed border-border bg-stone-50 p-4 text-sm text-muted-foreground">
                    当前没有备份文件。
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}
