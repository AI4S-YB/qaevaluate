"use client";

import { useEffect, useMemo, useState } from "react";

import {
  apiFetch,
  type ApplicationItem,
  type QueueJob,
  type QueueMonitor
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatTime(value: string | null) {
  if (!value) return "未记录";
  return value.replace("T", " ").slice(0, 16);
}

function formatDuration(durationMs: number | null) {
  if (durationMs === null || durationMs === undefined) return "未记录";
  if (durationMs < 1000) return `${durationMs} ms`;
  return `${(durationMs / 1000).toFixed(1)} s`;
}

function statusVariant(status: QueueJob["status"]) {
  if (status === "done") return "success";
  if (status === "failed") return "warning";
  if (status === "processing") return "muted";
  return "default";
}

export default function AdminTasksPage() {
  const [monitor, setMonitor] = useState<QueueMonitor | null>(null);
  const [applications, setApplications] = useState<ApplicationItem[]>([]);
  const [selectedApplication, setSelectedApplication] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dispatching, setDispatching] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [runningWorker, setRunningWorker] = useState(false);

  async function loadData() {
    setError(null);
    try {
      const [queueData, applicationData] = await Promise.all([
        apiFetch<QueueMonitor>("/api/admin/jobs"),
        apiFetch<ApplicationItem[]>("/api/applications")
      ]);
      setMonitor(queueData);
      setApplications(applicationData);
      if (!selectedApplication && applicationData.length > 0) {
        setSelectedApplication(String(applicationData[0].id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载任务监控失败");
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  const jobs = monitor?.jobs ?? [];
  const jobTypes = useMemo(
    () => Array.from(new Set(jobs.map((job) => job.type))).sort(),
    [jobs]
  );
  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      if (statusFilter !== "all" && job.status !== statusFilter) return false;
      if (typeFilter !== "all" && job.type !== typeFilter) return false;
      return true;
    });
  }, [jobs, statusFilter, typeFilter]);
  const selectedJob =
    filteredJobs.find((job) => job.job_id === selectedJobId) ??
    jobs.find((job) => job.job_id === selectedJobId) ??
    filteredJobs[0] ??
    null;
  const filteredSummary = useMemo(() => {
    return filteredJobs.reduce(
      (acc, job) => {
        acc[job.status] += 1;
        if (job.status === "failed") acc.failedRetries += job.retry_count;
        return acc;
      },
      { pending: 0, processing: 0, done: 0, failed: 0, failedRetries: 0 }
    );
  }, [filteredJobs]);

  useEffect(() => {
    if (selectedJob) {
      setSelectedJobId(selectedJob.job_id);
      return;
    }
    if (selectedJobId && filteredJobs.length === 0) {
      setSelectedJobId(null);
    }
  }, [selectedJob, selectedJobId, filteredJobs]);

  async function handleDispatch() {
    if (!selectedApplication) {
      setError("请先选择应用");
      return;
    }
    setDispatching(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch("/api/admin/tasks/dispatch", {
        method: "POST",
        body: JSON.stringify({
          application_id: Number(selectedApplication),
          limit: 100
        })
      });
      setNotice("已创建 dispatch job。");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建分发任务失败");
    } finally {
      setDispatching(false);
    }
  }

  async function handleRetry(jobId: string) {
    setRetryingJobId(jobId);
    setError(null);
    setNotice(null);
    try {
      const result = await apiFetch<{ job_id: string; retry_count: number }>(
        `/api/admin/jobs/${jobId}/retry`,
        { method: "POST" }
      );
      setNotice(`已重试 job ${result.job_id}，当前重试次数 ${result.retry_count}。`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "重试 job 失败");
    } finally {
      setRetryingJobId(null);
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
          ? `已处理一条 job：${result.job_id}`
          : "当前没有待处理的 pending job。"
      );
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "执行单次 worker 失败");
    } finally {
      setRunningWorker(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">任务分发与队列监控</p>
          <h2 className="mt-2 font-serif text-4xl">把分发动作和故障排查看到同一块屏幕里</h2>
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
            刷新监控
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

      <section className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle>创建分发任务</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <select
              className="field"
              value={selectedApplication}
              onChange={(event) => setSelectedApplication(event.target.value)}
            >
              <option value="">选择应用</option>
              {applications.map((application) => (
                <option key={application.id} value={application.id}>
                  {application.name}
                </option>
              ))}
            </select>
            <p className="text-sm leading-7 text-muted-foreground">
              点击后会写入一个 `dispatch` 类型 job，由 worker 消费并按应用给专家分配任务。
            </p>
            <Button disabled={dispatching} onClick={() => void handleDispatch()}>
              {dispatching ? "创建中…" : "批量分发"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>筛选后概况</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Pending", filteredSummary.pending],
              ["Processing", filteredSummary.processing],
              ["Done", filteredSummary.done],
              ["Failed", filteredSummary.failed]
            ].map(([label, count]) => (
              <div key={label} className="rounded-3xl border border-border bg-stone-50 p-4">
                <p className="text-sm text-muted-foreground">{label}</p>
                <p className="mt-2 text-3xl font-semibold">{count}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <CardTitle>Job 过滤器</CardTitle>
            <p className="text-sm text-muted-foreground">
              当前结果 {filteredJobs.length} / 全部 {jobs.length}
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <select
              className="field min-w-[180px]"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="all">全部状态</option>
              <option value="pending">pending</option>
              <option value="processing">processing</option>
              <option value="done">done</option>
              <option value="failed">failed</option>
            </select>
            <select
              className="field min-w-[180px]"
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value)}
            >
              <option value="all">全部类型</option>
              {jobTypes.map((jobType) => (
                <option key={jobType} value={jobType}>
                  {jobType}
                </option>
              ))}
            </select>
          </div>
        </CardHeader>
      </Card>

      <section className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <Card>
          <CardHeader>
            <CardTitle>Job 明细</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {filteredJobs.map((job) => {
              const selected = selectedJob?.job_id === job.job_id;
              return (
                <div
                  key={job.job_id}
                  className={`block w-full rounded-[28px] border p-4 text-left transition ${
                    selected
                      ? "border-stone-900 bg-white shadow-sm"
                      : "border-border bg-stone-50 hover:bg-white"
                  }`}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedJobId(job.job_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedJobId(job.job_id);
                    }
                  }}
                >
                  <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <p className="font-medium">{job.job_id}</p>
                      <p className="text-sm text-muted-foreground">
                        {job.type} / 最近更新 {formatTime(job.updated_at)}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
                      <Badge variant="muted">重试 {job.retry_count}</Badge>
                      {job.duration_ms !== null ? (
                        <Badge variant="muted">{formatDuration(job.duration_ms)}</Badge>
                      ) : null}
                    </div>
                  </div>

                  <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
                    <p>创建时间: {formatTime(job.created_at)}</p>
                    <p>开始时间: {formatTime(job.started_at)}</p>
                    <p>完成时间: {formatTime(job.completed_at)}</p>
                    <p>执行耗时: {formatDuration(job.duration_ms)}</p>
                  </div>

                  {job.status === "failed" ? (
                    <div className="mt-3 flex justify-end">
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={retryingJobId === job.job_id}
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleRetry(job.job_id);
                        }}
                      >
                        {retryingJobId === job.job_id ? "重试中…" : "重试"}
                      </Button>
                    </div>
                  ) : null}
                </div>
              );
            })}

            {filteredJobs.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                当前筛选条件下没有 job。
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>失败详情与上下文</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!selectedJob ? (
              <div className="rounded-3xl border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                选择左侧任意一条 job 查看详情。
              </div>
            ) : (
              <>
                <div className="rounded-[28px] border border-border bg-stone-50 p-5">
                  <div className="flex flex-wrap items-center gap-3">
                    <p className="font-medium">{selectedJob.job_id}</p>
                    <Badge variant={statusVariant(selectedJob.status)}>
                      {selectedJob.status}
                    </Badge>
                    <Badge variant="muted">{selectedJob.type}</Badge>
                  </div>
                  <div className="mt-4 grid gap-2 text-sm text-muted-foreground">
                    <p>创建时间: {formatTime(selectedJob.created_at)}</p>
                    <p>开始时间: {formatTime(selectedJob.started_at)}</p>
                    <p>完成时间: {formatTime(selectedJob.completed_at)}</p>
                    <p>执行耗时: {formatDuration(selectedJob.duration_ms)}</p>
                    <p>重试次数: {selectedJob.retry_count}</p>
                    <p>文件名: {selectedJob.filename}</p>
                  </div>
                </div>

                {selectedJob.error ? (
                  <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-5">
                    <p className="text-sm font-medium text-amber-900">错误信息</p>
                    <p className="mt-2 text-sm leading-7 text-amber-800">
                      {selectedJob.error}
                    </p>
                  </div>
                ) : (
                  <div className="rounded-[28px] border border-border bg-stone-50 p-5 text-sm text-muted-foreground">
                    当前 job 没有错误日志。
                  </div>
                )}

                <div>
                  <p className="mb-2 text-sm font-medium">Payload</p>
                  <pre className="overflow-x-auto rounded-3xl border border-border bg-white p-4 text-xs leading-6 text-muted-foreground">
                    {JSON.stringify(selectedJob.payload, null, 2)}
                  </pre>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
