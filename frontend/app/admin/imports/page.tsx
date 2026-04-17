"use client";

import { useEffect, useMemo, useState } from "react";

import {
  apiFetch,
  type ImportBatch,
  type ImportFailure,
  type ImportFailureDetail
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function statText(batch: ImportBatch) {
  return `${batch.total_count} / ${batch.success_count} / ${batch.fail_count}`;
}

function formatTime(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

export default function AdminImportsPage() {
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [failureDetail, setFailureDetail] = useState<ImportFailureDetail | null>(null);
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null);
  const [selectedFailureId, setSelectedFailureId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingFailures, setLoadingFailures] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [parsingId, setParsingId] = useState<number | null>(null);

  async function loadBatches() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<ImportBatch[]>("/api/admin/imports");
      setBatches(data);
      if (selectedBatchId && !data.some((batch) => batch.id === selectedBatchId)) {
        setSelectedBatchId(null);
        setFailureDetail(null);
        setSelectedFailureId(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载批次失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadFailures(batchId: number) {
    setLoadingFailures(true);
    setError(null);
    try {
      const data = await apiFetch<ImportFailureDetail>(`/api/admin/imports/${batchId}/failures`);
      setFailureDetail(data);
      setSelectedBatchId(batchId);
      setSelectedFailureId(data.failures[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败明细失败");
    } finally {
      setLoadingFailures(false);
    }
  }

  async function handleUpload() {
    if (!file) {
      setError("请先选择一个 JSON 文件");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const query = new URLSearchParams({
        name: name || "manual-batch",
        source: source || "manual-upload"
      });
      await apiFetch(`/api/admin/imports/upload?${query.toString()}`, {
        method: "POST",
        body: formData
      });
      setName("");
      setSource("");
      setFile(null);
      await loadBatches();
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleParse(batchId: number) {
    setParsingId(batchId);
    setError(null);
    try {
      await apiFetch(`/api/admin/imports/${batchId}/parse`, { method: "POST" });
      await loadBatches();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建解析任务失败");
    } finally {
      setParsingId(null);
    }
  }

  useEffect(() => {
    void loadBatches();
  }, []);

  const selectedFailure =
    failureDetail?.failures.find((item) => item.id === selectedFailureId) ??
    failureDetail?.failures[0] ??
    null;
  const batchesWithFailures = useMemo(
    () => batches.filter((batch) => batch.fail_count > 0),
    [batches]
  );

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">数据导入</p>
        <h2 className="mt-2 font-serif text-4xl">上传 JSON 并以批次跟踪导入状态</h2>
      </div>
      <section className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle>上传新批次</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <input
              className="field"
              placeholder="批次名称"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <input
              className="field"
              placeholder="来源说明"
              value={source}
              onChange={(event) => setSource(event.target.value)}
            />
            <label className="flex cursor-pointer flex-col items-center justify-center rounded-[28px] border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
              <span>{file ? file.name : "拖拽或选择 JSON 文件"}</span>
              <input
                className="hidden"
                type="file"
                accept=".json,application/json"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>
            <Button disabled={submitting} onClick={() => void handleUpload()}>
              {submitting ? "上传中…" : "上传并创建批次"}
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <CardTitle>导入批次</CardTitle>
            <Button variant="secondary" onClick={() => void loadBatches()}>
              刷新
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {error ? (
              <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                {error}
              </div>
            ) : null}

            {!loading && batches.length === 0 ? (
              <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
                当前没有导入批次。
              </div>
            ) : null}

            {batches.map((batch) => (
              <div
                key={batch.id}
                className="rounded-3xl border border-border bg-stone-50 p-4"
              >
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="font-medium">{batch.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {batch.source || "无来源说明"} / {statText(batch)}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      创建于 {formatTime(batch.created_at)}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <Badge
                      variant={
                        batch.import_status === "parsed"
                          ? "success"
                          : batch.import_status === "uploaded"
                            ? "default"
                            : "warning"
                      }
                    >
                      {batch.import_status}
                    </Badge>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={parsingId === batch.id}
                      onClick={() => void handleParse(batch.id)}
                    >
                      {parsingId === batch.id ? "提交中…" : "创建解析任务"}
                    </Button>
                    {batch.fail_count > 0 ? (
                      <Button
                        size="sm"
                        variant={selectedBatchId === batch.id ? "default" : "secondary"}
                        onClick={() => void loadFailures(batch.id)}
                      >
                        查看失败明细
                      </Button>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
        <Card>
          <CardHeader className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle>失败样本列表</CardTitle>
              <p className="text-sm text-muted-foreground">
                有失败记录的批次 {batchesWithFailures.length} 个
              </p>
            </div>
            {selectedBatchId ? (
              <Button
                size="sm"
                variant="secondary"
                disabled={loadingFailures}
                onClick={() => void loadFailures(selectedBatchId)}
              >
                {loadingFailures ? "加载中…" : "刷新失败明细"}
              </Button>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-3">
            {!selectedBatchId ? (
              <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                从上方批次中选择“查看失败明细”。
              </div>
            ) : null}

            {selectedBatchId && failureDetail && failureDetail.failures.length === 0 ? (
              <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                该批次当前没有失败样本。
              </div>
            ) : null}

            {failureDetail?.failures.map((failure: ImportFailure) => {
              const selected = selectedFailure?.id === failure.id;
              return (
                <div
                  key={failure.id}
                  className={`cursor-pointer rounded-[28px] border p-4 transition ${
                    selected
                      ? "border-stone-900 bg-white shadow-sm"
                      : "border-border bg-stone-50 hover:bg-white"
                  }`}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedFailureId(failure.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedFailureId(failure.id);
                    }
                  }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">Row #{failure.row_no}</p>
                      <p className="text-sm text-muted-foreground">
                        {failure.external_id || "无 external_id"}
                      </p>
                    </div>
                    <Badge variant="warning">failed</Badge>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground">
                    {failure.question_preview || "无问题摘要"}
                  </p>
                </div>
              );
            })}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>失败详情</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!failureDetail ? (
              <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                选择失败批次后，这里展示错误原因和原始 payload。
              </div>
            ) : (
              <>
                <div className="rounded-[28px] border border-border bg-stone-50 p-5">
                  <p className="font-medium">{failureDetail.batch.name}</p>
                  <p className="mt-2 text-sm text-muted-foreground">
                    总计 {failureDetail.batch.total_count} / 成功 {failureDetail.batch.success_count} /
                    失败 {failureDetail.batch.fail_count}
                  </p>
                </div>

                {!selectedFailure ? (
                  <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                    当前批次没有失败样本。
                  </div>
                ) : (
                  <>
                    <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-5">
                      <p className="text-sm font-medium text-amber-900">
                        错误原因 / Row #{selectedFailure.row_no}
                      </p>
                      <p className="mt-2 text-sm leading-7 text-amber-800">
                        {selectedFailure.error_message}
                      </p>
                      <p className="mt-3 text-xs text-amber-700">
                        记录时间 {formatTime(selectedFailure.created_at)}
                      </p>
                    </div>

                    <div>
                      <p className="mb-2 text-sm font-medium">原始样本</p>
                      <pre className="overflow-x-auto rounded-3xl border border-border bg-white p-4 text-xs leading-6 text-muted-foreground">
                        {selectedFailure.raw_payload_json || "{}"}
                      </pre>
                    </div>
                  </>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
