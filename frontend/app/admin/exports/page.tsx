"use client";

import { useEffect, useMemo, useState } from "react";

import { loadSession } from "@/lib/auth";
import {
  API_BASE_URL,
  apiFetch,
  type ApplicationItem,
  type ExportJob
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const exportTypes = [
  {
    value: "final_dataset",
    label: "最终训练集",
    description: "导出已聚合完成的 QA 与当前最终答案。"
  },
  {
    value: "review_records",
    label: "评测明细",
    description: "导出专家的结构化评分记录，适合做一致性分析。"
  },
  {
    value: "disputed_cases",
    label: "争议样本",
    description: "导出触发争议复核的 QA，方便抽样复查。"
  },
  {
    value: "sft_dataset",
    label: "SFT 训练集",
    description: "导出可直接用于监督微调的 messages 数据，推荐使用 JSONL。"
  }
] as const;

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

function statusVariant(status: ExportJob["status"]) {
  if (status === "done") return "success";
  if (status === "failed") return "warning";
  if (status === "processing") return "muted";
  return "default";
}

export default function AdminExportsPage() {
  const [exports, setExports] = useState<ExportJob[]>([]);
  const [applications, setApplications] = useState<ApplicationItem[]>([]);
  const [exportType, setExportType] =
    useState<ExportJob["export_type"]>("final_dataset");
  const [applicationId, setApplicationId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [fileFormat, setFileFormat] = useState<ExportJob["file_format"]>("json");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [runningWorker, setRunningWorker] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [exportData, applicationData] = await Promise.all([
        apiFetch<ExportJob[]>("/api/admin/exports"),
        apiFetch<ApplicationItem[]>("/api/applications")
      ]);
      setExports(exportData);
      setApplications(applicationData);
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
    if (exportType === "sft_dataset" && fileFormat !== "jsonl") {
      setFileFormat("jsonl");
    }
  }, [exportType, fileFormat]);

  async function handleCreate() {
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const created = await apiFetch<ExportJob>("/api/admin/exports", {
        method: "POST",
        body: JSON.stringify({
          type: exportType,
          application_id: applicationId ? Number(applicationId) : null,
          from: dateFrom || null,
          to: dateTo || null,
          format: fileFormat
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

      <section className="grid gap-4 xl:grid-cols-[0.88fr_1.12fr]">
        <Card className="border-none bg-[radial-gradient(circle_at_top_left,rgba(255,247,237,0.9),rgba(255,255,255,0.96)_55%,rgba(241,245,249,0.9))] shadow-sm ring-1 ring-stone-200">
          <CardHeader>
            <CardTitle>新建导出任务</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3">
              {exportTypes.map((item) => (
                <button
                  key={item.value}
                  className={`rounded-[28px] border p-4 text-left transition ${
                    exportType === item.value
                      ? "border-stone-900 bg-white shadow-sm"
                      : "border-border bg-white/70 hover:bg-white"
                  }`}
                  type="button"
                  onClick={() => setExportType(item.value)}
                >
                  <p className="font-medium">{item.label}</p>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    {item.description}
                  </p>
                </button>
              ))}
            </div>

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

            <div className="grid gap-4 sm:grid-cols-2">
              <input
                className="field"
                type="date"
                value={dateFrom}
                onChange={(event) => setDateFrom(event.target.value)}
              />
              <input
                className="field"
                type="date"
                value={dateTo}
                onChange={(event) => setDateTo(event.target.value)}
              />
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
              {exportType === "sft_dataset"
                ? " SFT 训练集会导出为 chat messages 结构，建议选择 JSONL。"
                : ""}
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
            {!loading && exports.length === 0 ? (
              <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
                还没有导出任务。
              </div>
            ) : null}

            {exports.map((item) => (
              <div
                key={item.id}
                className="rounded-[30px] border border-border bg-[linear-gradient(180deg,rgba(250,250,249,0.9),rgba(255,255,255,0.98))] p-5"
              >
                <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-3">
                      <p className="font-medium">
                        #{item.id} / {item.export_type}
                      </p>
                      <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
                      <Badge variant="muted">{item.file_format}</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {item.application_name || "全部应用"} / {formatRange(item.date_from, item.date_to)}
                    </p>
                    <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
                      <p>创建时间: {formatTime(item.created_at)}</p>
                      <p>处理完成: {formatTime(item.completed_at)}</p>
                      <p>数据量: {item.total_records} records</p>
                      <p>文件大小: {formatFileSize(item.file_size_bytes)}</p>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-3">
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
            ))}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
