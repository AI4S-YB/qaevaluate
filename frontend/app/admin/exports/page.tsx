"use client";

import { useEffect, useMemo, useState } from "react";

import { loadSession } from "@/lib/auth";
import {
  API_BASE_URL,
  apiFetch,
  type ApplicationItem,
  type ExportJob,
  type ExportStats,
  type TaxonomyItem
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function toDateInputValue(value: Date) {
  return value.toISOString().slice(0, 10);
}

function startOfWeek(value: Date) {
  const next = new Date(value);
  const day = next.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  next.setDate(next.getDate() + diff);
  next.setHours(0, 0, 0, 0);
  return next;
}

function endOfWeek(value: Date) {
  const next = startOfWeek(value);
  next.setDate(next.getDate() + 6);
  return next;
}

function addDays(value: string, days: number) {
  const next = new Date(`${value}T00:00:00`);
  next.setDate(next.getDate() + days);
  return next.toISOString().slice(0, 10);
}

function weekdayLabel(value: string) {
  const day = new Date(`${value}T00:00:00`).getDay();
  return ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][day];
}

function formatTime(value: string | null) {
  if (!value) return "未开始";
  return value.replace("T", " ").slice(0, 16);
}

function formatRange(start: string | null, end: string | null) {
  if (!start && !end) return "全量";
  if (start && end) return `${start} -> ${end}`;
  return `${start || end}`;
}

function formatFileSize(bytes: number) {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function exportTypeLabel(value: ExportJob["export_type"]) {
  if (value === "sft_dataset") return "一键导出 QA";
  if (value === "final_dataset") return "最终训练集";
  if (value === "review_records") return "评测明细";
  return "争议样本";
}

function statusVariant(status: ExportJob["status"]) {
  if (status === "done") return "success";
  if (status === "failed") return "warning";
  if (status === "processing") return "muted";
  return "default";
}

export default function AdminExportsPage() {
  const [exports, setExports] = useState<ExportJob[]>([]);
  const [applications, setApplications] = useState<ApplicationItem[]>([]);
  const [technicalTypes, setTechnicalTypes] = useState<TaxonomyItem[]>([]);
  const [stats, setStats] = useState<ExportStats | null>(null);
  const [applicationId, setApplicationId] = useState("");
  const [technicalTypeCodes, setTechnicalTypeCodes] = useState<string[]>([]);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [fileFormat, setFileFormat] = useState<ExportJob["file_format"]>("json");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [runningWorker, setRunningWorker] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [statsExpanded, setStatsExpanded] = useState(false);
  const [selectedWeekStart, setSelectedWeekStart] = useState<string | null>(null);
  const [quickRange, setQuickRange] = useState<
    "this_week" | "last_week" | "last_7_days" | "last_30_days" | "all" | "custom"
  >("all");
  const [technicalTypesInitialized, setTechnicalTypesInitialized] = useState(false);

  const summary = useMemo(() => {
    return exports.reduce(
      (acc, item) => {
        acc[item.status] += 1;
        acc.total += 1;
        acc.records += item.total_records;
        return acc;
      },
      { pending: 0, processing: 0, done: 0, failed: 0, total: 0, records: 0 }
    );
  }, [exports]);

  const technicalTypeMap = useMemo(
    () => new Map(technicalTypes.map((item) => [item.code, item.name])),
    [technicalTypes]
  );
  const latestSuccessfulRecordCount = useMemo(
    () => exports.find((item) => item.status === "done" && item.total_records > 0)?.total_records ?? null,
    [exports]
  );

  const recentWeeklyStats = stats?.weekly.slice(0, 8) ?? [];
  const visibleWeeklyStats = statsExpanded ? recentWeeklyStats : recentWeeklyStats.slice(0, 1);
  const activeWeek =
    recentWeeklyStats.find((item) => item.period_start === selectedWeekStart) ?? recentWeeklyStats[0] ?? null;
  const activeWeekDailyStats = useMemo(() => {
    if (!activeWeek?.period_start || !activeWeek.period_end) return [];
    const dailyMap = new Map(
      (stats?.daily ?? [])
        .filter((item) => item.period)
        .map((item) => [item.period as string, item])
    );
    return Array.from({ length: 7 }, (_, index) => {
      const period = addDays(activeWeek.period_start!, index);
      const point = dailyMap.get(period);
      return {
        period,
        import_count: point?.import_count ?? 0,
        review_count: point?.review_count ?? 0
      };
    });
  }, [activeWeek, stats?.daily]);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [exportData, applicationData, technicalTypeData, statsData] = await Promise.all([
        apiFetch<ExportJob[]>("/api/admin/exports"),
        apiFetch<ApplicationItem[]>("/api/applications"),
        apiFetch<TaxonomyItem[]>("/api/admin/technical-types"),
        apiFetch<ExportStats>("/api/admin/exports/stats")
      ]);
      setExports(exportData);
      setApplications(applicationData);
      setTechnicalTypes(technicalTypeData.filter((item) => item.is_active));
      setStats(statsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载导出任务失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  useEffect(() => {
    if (fileFormat !== "jsonl") {
      setFileFormat("jsonl");
    }
  }, [fileFormat]);

  useEffect(() => {
    if (!technicalTypes.length || technicalTypesInitialized) return;
    const defaultCodes = technicalTypes
      .filter((item) => item.code !== "direct_qa")
      .map((item) => item.code);
    setTechnicalTypeCodes(defaultCodes);
    setTechnicalTypesInitialized(true);
  }, [technicalTypes, technicalTypesInitialized]);

  useEffect(() => {
    if (!recentWeeklyStats.length) {
      setSelectedWeekStart(null);
      return;
    }
    if (
      !selectedWeekStart ||
      !recentWeeklyStats.some((item) => item.period_start === selectedWeekStart)
    ) {
      setSelectedWeekStart(recentWeeklyStats[0].period_start ?? null);
    }
  }, [recentWeeklyStats, selectedWeekStart]);

  async function handleCreate() {
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const created = await apiFetch<ExportJob>("/api/admin/exports", {
        method: "POST",
        body: JSON.stringify({
          type: "sft_dataset",
          application_id: applicationId ? Number(applicationId) : null,
          from: dateFrom || null,
          to: dateTo || null,
          format: fileFormat,
          technical_type_codes: technicalTypeCodes
        })
      });
      setNotice(`已创建导出任务 #${created.id}，等待 worker 处理。`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建导出任务失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRunOneJob() {
    setRunningWorker(true);
    setError(null);
    setNotice(null);
    try {
      const result = await apiFetch<{ processed: boolean; job_id: string | null }>(
        "/api/admin/jobs/run-once",
        { method: "POST" }
      );
      setNotice(
        result.processed
          ? `worker 已处理一条 job：${result.job_id}`
          : "当前没有 pending job。"
      );
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "执行 worker 失败");
    } finally {
      setRunningWorker(false);
    }
  }

  async function handleRetry(jobId: string) {
    setRetryingJobId(jobId);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/jobs/${jobId}/retry`, { method: "POST" });
      setNotice(`已将失败导出 ${jobId} 重新放回 pending。`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "重试导出失败");
    } finally {
      setRetryingJobId(null);
    }
  }

  async function handleDownload(item: ExportJob) {
    setDownloadingId(item.id);
    setError(null);
    try {
      const session = loadSession();
      if (!session?.token) {
        throw new Error("当前缺少登录态，无法下载");
      }
      const response = await fetch(`${API_BASE_URL}/api/admin/exports/${item.id}/download`, {
        headers: {
          Authorization: `Bearer ${session.token}`
        }
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = item.file_name || `export-${item.id}.${item.file_format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "下载导出文件失败");
    } finally {
      setDownloadingId(null);
    }
  }

  async function handleDelete(item: ExportJob) {
    if (
      !window.confirm(
        `确认删除导出任务 #${item.id} 吗？${item.file_name ? "\n对应导出文件也会一起删除。" : ""}`
      )
    ) {
      return;
    }

    setDeletingId(item.id);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/exports/${item.id}`, { method: "DELETE" });
      setNotice(`已删除导出任务 #${item.id}。`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除导出任务失败");
    } finally {
      setDeletingId(null);
    }
  }

  function toggleTechnicalType(code: string) {
    setTechnicalTypeCodes((current) =>
      current.includes(code) ? current.filter((item) => item !== code) : [...current, code]
    );
  }

  function applyQuickRange(range: "this_week" | "last_week" | "last_7_days" | "last_30_days" | "all") {
    setQuickRange(range);
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    if (range === "all") {
      setDateFrom("");
      setDateTo("");
      return;
    }

    if (range === "this_week") {
      setDateFrom(toDateInputValue(startOfWeek(today)));
      setDateTo(toDateInputValue(endOfWeek(today)));
      return;
    }

    if (range === "last_week") {
      const lastWeekEnd = new Date(startOfWeek(today));
      lastWeekEnd.setDate(lastWeekEnd.getDate() - 1);
      const lastWeekStart = startOfWeek(lastWeekEnd);
      setDateFrom(toDateInputValue(lastWeekStart));
      setDateTo(toDateInputValue(endOfWeek(lastWeekEnd)));
      return;
    }

    const start = new Date(today);
    start.setDate(start.getDate() - (range === "last_7_days" ? 6 : 29));
    setDateFrom(toDateInputValue(start));
    setDateTo(toDateInputValue(today));
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">结果导出</p>
          <h2 className="mt-2 max-w-4xl font-serif text-4xl leading-tight">
            把已评测的 QA 直接沉淀成训练集、评测明细和争议样本包
          </h2>
        </div>
        <div className="flex gap-3">
          <Button
            variant="secondary"
            disabled={runningWorker}
            onClick={() => void handleRunOneJob()}
          >
            {runningWorker ? "处理中…" : "处理一条 Pending Job"}
          </Button>
          <Button variant="secondary" onClick={() => void loadData()}>
            刷新历史
          </Button>
        </div>
      </div>

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

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {[
          ["总任务", summary.total],
          ["Pending", summary.pending],
          ["Processing", summary.processing],
          ["Done", summary.done],
          ["累计记录", summary.records]
        ].map(([label, value]) => (
          <Card
            key={label}
            className="overflow-hidden border-none bg-[linear-gradient(135deg,rgba(255,255,255,0.96),rgba(244,244,240,0.95))] shadow-sm ring-1 ring-stone-200"
          >
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">{label}</p>
              <p className="mt-3 text-3xl font-semibold tracking-tight">{value}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      <section>
        <Card className="border-none bg-white shadow-sm ring-1 ring-stone-200">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>每周 / 每日导入与评测</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                左侧选择周次，右侧查看该周每日导入与评测明细。
              </p>
            </div>
            <Button variant="secondary" onClick={() => setStatsExpanded((current) => !current)}>
              {statsExpanded ? "收起" : "展开更多"}
            </Button>
          </CardHeader>
          <CardContent className="grid items-stretch gap-4 xl:grid-cols-[0.92fr_1.08fr]">
            <div className="rounded-[24px] border border-border bg-stone-50 p-4">
              <div className="space-y-3">
                {visibleWeeklyStats.map((item) => {
                  const selected = item.period_start === activeWeek?.period_start;
                  return (
                    <button
                      key={item.period ?? `${item.period_start}-${item.period_end}`}
                      type="button"
                      className={`w-full rounded-[20px] border px-4 py-4 text-left transition ${
                        selected
                          ? "border-stone-900 bg-stone-900 text-white"
                          : "border-border bg-white hover:bg-stone-100"
                      }`}
                      onClick={() => setSelectedWeekStart(item.period_start ?? null)}
                    >
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <p className="font-medium">{item.period ?? "最近一周"}</p>
                          <p
                            className={`mt-1 text-sm ${
                              selected ? "text-stone-200" : "text-muted-foreground"
                            }`}
                          >
                            {item.period_start} ~ {item.period_end}
                          </p>
                        </div>
                        <div className={`text-sm ${selected ? "text-stone-200" : "text-muted-foreground"}`}>
                          <p>导入 {item.import_count}</p>
                          <p>评测 {item.review_count}</p>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="rounded-[24px] border border-border bg-stone-50 p-4">
              {activeWeekDailyStats.length === 0 ? (
                <div className="rounded-[20px] border border-dashed border-border bg-white p-6 text-sm text-muted-foreground">
                  该周暂无每日统计数据。
                </div>
              ) : (
                <div className="grid auto-rows-fr gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
                  {activeWeekDailyStats.map((item) => (
                    <div
                      key={item.period}
                      className="flex min-h-[88px] flex-col items-center justify-center rounded-[18px] border border-border bg-white px-2 py-4 text-center text-sm"
                    >
                      <p className="font-medium">{weekdayLabel(item.period)}</p>
                      <p className="mt-3 font-semibold text-foreground">
                        {item.import_count}/{item.review_count}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[0.88fr_1.12fr]">
        <Card className="border-none bg-[radial-gradient(circle_at_top_left,rgba(255,247,237,0.9),rgba(255,255,255,0.96)_55%,rgba(241,245,249,0.9))] shadow-sm ring-1 ring-stone-200">
          <CardHeader>
            <CardTitle>新建导出任务</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <select
              className="field"
              value={applicationId}
              onChange={(event) => setApplicationId(event.target.value)}
            >
              <option value="">全部应用</option>
              {applications.map((application) => (
                <option key={application.id} value={application.id}>
                  {application.name}
                </option>
              ))}
            </select>

            <div className="rounded-[28px] border border-stone-200 bg-white/80 p-4">
              <p className="text-sm font-medium">QA 类型筛选</p>
              <p className="mt-1 text-sm text-muted-foreground">
                可多选；不选表示全部 QA 类型。
              </p>
              <div className="mt-3 flex flex-wrap gap-3">
                {technicalTypes.map((item) => {
                  const selected = technicalTypeCodes.includes(item.code);
                  return (
                    <button
                      key={item.code}
                      type="button"
                      className={`rounded-full border px-3 py-1 text-sm transition ${
                        selected
                          ? "border-stone-900 bg-stone-900 text-white"
                          : "border-stone-300 bg-white text-foreground"
                      }`}
                      onClick={() => toggleTechnicalType(item.code)}
                    >
                      {item.name}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <input
                className="field"
                type="date"
                value={dateFrom}
                onChange={(event) => {
                  setDateFrom(event.target.value);
                  setQuickRange("custom");
                }}
              />
              <input
                className="field"
                type="date"
                value={dateTo}
                onChange={(event) => {
                  setDateTo(event.target.value);
                  setQuickRange("custom");
                }}
              />
            </div>

            <div className="flex flex-wrap gap-3">
              {[
                ["this_week", "本周"],
                ["last_week", "上周"],
                ["last_7_days", "最近7天"],
                ["last_30_days", "最近30天"],
                ["all", "全量"]
              ].map(([value, label]) => (
                <Button
                  key={value}
                  size="sm"
                  type="button"
                  variant={quickRange === value ? "default" : "secondary"}
                  onClick={() =>
                    applyQuickRange(
                      value as "this_week" | "last_week" | "last_7_days" | "last_30_days" | "all"
                    )
                  }
                >
                  {label}
                </Button>
              ))}
            </div>

            <select
              className="field"
              value={fileFormat}
              onChange={(event) =>
                setFileFormat(event.target.value as ExportJob["file_format"])
              }
            >
              <option value="json">JSON</option>
              <option value="jsonl">JSONL</option>
            </select>

            <div className="rounded-[28px] border border-dashed border-stone-300 bg-white/80 p-4 text-sm leading-7 text-muted-foreground">
              当前导出会把 job 写入文件队列，文件产物落在 `data/exports/`。
              {" "}导出 QA 会输出 chat messages 结构，默认覆盖已评测和未评测样本，建议选择 JSONL。
            </div>

            <Button disabled={submitting} onClick={() => void handleCreate()}>
              {submitting ? "创建中…" : "创建导出任务"}
            </Button>
          </CardContent>
        </Card>

        <Card className="border-none bg-white shadow-sm ring-1 ring-stone-200">
          <CardHeader>
            <CardTitle>导出历史</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {latestSuccessfulRecordCount ? (
              <div className="rounded-[24px] border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-muted-foreground">
                当前最新成功导出基线：{latestSuccessfulRecordCount} 条。明显偏小的历史任务会标记为旧结果。
              </div>
            ) : null}
            {!loading && exports.length === 0 ? (
              <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
                还没有导出任务。
              </div>
            ) : null}

            {exports.map((item) => {
              const isLegacySmallResult =
                item.status === "done" &&
                latestSuccessfulRecordCount !== null &&
                latestSuccessfulRecordCount > 0 &&
                item.total_records > 0 &&
                item.total_records < latestSuccessfulRecordCount;

              return (
                <div
                  key={item.id}
                  className="rounded-[30px] border border-border bg-[linear-gradient(180deg,rgba(250,250,249,0.9),rgba(255,255,255,0.98))] p-5"
                >
                  <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-3">
                        <p className="font-medium">
                          #{item.id} / {exportTypeLabel(item.export_type)}
                        </p>
                        <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
                        <Badge variant="muted">{item.file_format}</Badge>
                        {isLegacySmallResult ? <Badge variant="warning">旧结果，记录数偏小</Badge> : null}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {item.application_name || "全部应用"} / {formatRange(item.date_from, item.date_to)}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {item.technical_type_codes.length === 0 ? (
                          <Badge variant="muted">全部 QA 类型</Badge>
                        ) : (
                          item.technical_type_codes.map((code) => (
                            <Badge key={`${item.id}-${code}`} variant="muted">
                              {technicalTypeMap.get(code) ?? code}
                            </Badge>
                          ))
                        )}
                      </div>
                      <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
                        <p>创建时间: {formatTime(item.created_at)}</p>
                        <p>处理完成: {formatTime(item.completed_at)}</p>
                        <p>数据量: {item.total_records} 条</p>
                        <p>文件大小: {formatFileSize(item.file_size_bytes)}</p>
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-3">
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={deletingId === item.id || item.status === "processing"}
                        onClick={() => void handleDelete(item)}
                      >
                        {deletingId === item.id ? "删除中…" : "删除"}
                      </Button>
                      {item.status === "failed" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={retryingJobId === item.job_id}
                          onClick={() => void handleRetry(item.job_id)}
                        >
                          {retryingJobId === item.job_id ? "重试中…" : "重试"}
                        </Button>
                      ) : null}
                      {item.status === "done" ? (
                        <Button
                          size="sm"
                          disabled={downloadingId === item.id}
                          onClick={() => void handleDownload(item)}
                        >
                          {downloadingId === item.id ? "下载中…" : "下载文件"}
                        </Button>
                      ) : null}
                    </div>
                  </div>

                  {item.file_name ? (
                    <div className="mt-4 rounded-[24px] border border-stone-200 bg-white p-4 text-xs leading-6 text-muted-foreground">
                      {item.file_name}
                    </div>
                  ) : null}
                  {item.error_message ? (
                    <div className="mt-4 rounded-[24px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                      {item.error_message}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
