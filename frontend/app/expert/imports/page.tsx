"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  apiFetch,
  type ExpertImportBatch,
  type ExpertImportBatchDetail,
  type ExpertImportPushPayload,
  type ExpertTaxonomy,
  type MeProfile,
  type TaxonomyItem
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatTime(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

function parseTagCodes(value: string | null) {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as string[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function importStatusLabel(value: ExpertImportBatch["import_status"]) {
  if (value === "parsed") return "已解析";
  if (value === "failed") return "失败";
  return "已上传";
}

function reviewStatusLabel(
  value: ExpertImportBatch["self_review_status"] | ExpertImportBatch["peer_review_status"]
) {
  if (value === "queued") return "已排队";
  if (value === "pending") return "待处理";
  if (value === "in_progress") return "进行中";
  if (value === "submitted") return "已提交";
  if (value === "completed") return "已完成";
  return "未开始";
}

function reviewStatusVariant(
  value: ExpertImportBatch["self_review_status"] | ExpertImportBatch["peer_review_status"]
) {
  if (value === "submitted" || value === "completed") return "success";
  if (value === "in_progress") return "warning";
  if (value === "pending" || value === "queued") return "default";
  return "muted";
}

function compactText(value: string | null | undefined, fallback = "—") {
  if (!value) return fallback;
  const normalized = value.trim();
  return normalized || fallback;
}

const examplePayload = JSON.stringify(
  [
    {
      id: "qa-demo-001",
      question: "番茄晚疫病如何做综合防控？",
      answer:
        "建议轮作、降低棚内湿度、及时清理病残体，并在发病初期轮换喷施保护性与治疗性药剂。",
      context: "设施栽培，连续阴雨后湿度较高。",
      difficulty: "medium",
      source: "desktop-sync",
      model: "ft-agri-demo-v1",
      metadata: {
        group: "示例批次",
        note: "可直接替换成桌面端生成的 rows 数组"
      }
    }
  ],
  null,
  2
);

const VIRTUAL_REMOTE_BATCH_SOURCE = "remote-server";

export default function ExpertImportsPage() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [profile, setProfile] = useState<MeProfile | null>(null);
  const [taxonomy, setTaxonomy] = useState<ExpertTaxonomy | null>(null);
  const [batches, setBatches] = useState<ExpertImportBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ExpertImportBatchDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [peerSubmitting, setPeerSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [name, setName] = useState("expert-batch");
  const [source, setSource] = useState("qa-xiaozhao");
  const [sourceBatchName, setSourceBatchName] = useState("");
  const [externalBatchId, setExternalBatchId] = useState("");
  const [applicationId, setApplicationId] = useState("");
  const [technicalTypeCode, setTechnicalTypeCode] = useState("");
  const [selectedBusinessTags, setSelectedBusinessTags] = useState<string[]>([]);
  const [createSelfReview, setCreateSelfReview] = useState(true);
  const [jsonText, setJsonText] = useState(examplePayload);

  async function loadBaseData() {
    setLoading(true);
    setError(null);
    try {
      const [me, taxonomyData, batchData] = await Promise.all([
        apiFetch<MeProfile>("/api/me"),
        apiFetch<ExpertTaxonomy>("/api/expert/taxonomy"),
        apiFetch<ExpertImportBatch[]>("/api/expert/imports")
      ]);
      setProfile(me);
      setTaxonomy(taxonomyData);
      setBatches(batchData);
      setSelectedBatchId((current) => current ?? batchData[0]?.id ?? null);
      if (!applicationId && me.applications[0]) {
        setApplicationId(String(me.applications[0].id));
      }
      if (!technicalTypeCode && taxonomyData.technical_types[0]) {
        setTechnicalTypeCode(taxonomyData.technical_types[0].code);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载上传页面失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(batchId: number) {
    setLoadingDetail(true);
    setError(null);
    try {
      const data = await apiFetch<ExpertImportBatchDetail>(`/api/expert/imports/${batchId}`);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载批次详情失败");
    } finally {
      setLoadingDetail(false);
    }
  }

  async function refreshBatches(targetBatchId?: number | null) {
    const data = await apiFetch<ExpertImportBatch[]>("/api/expert/imports");
    setBatches(data);
    const nextId = targetBatchId ?? selectedBatchId ?? data[0]?.id ?? null;
    setSelectedBatchId(nextId);
    if (nextId) {
      await loadDetail(nextId);
    } else {
      setDetail(null);
    }
  }

  useEffect(() => {
    void loadBaseData();
  }, []);

  useEffect(() => {
    if (!selectedBatchId) {
      setDetail(null);
      return;
    }
    void loadDetail(selectedBatchId);
  }, [selectedBatchId]);

  const allowedApplications = useMemo(() => {
    if (!profile) return [];
    return profile.applications;
  }, [profile]);

  const allowedBusinessTags = useMemo(() => {
    if (!profile || !taxonomy) return [];
    if (profile.allow_cross_business_review) {
      return taxonomy.business_tags;
    }
    const allowedIds = new Set(profile.business_tags.map((item) => item.id));
    return taxonomy.business_tags.filter((item) => allowedIds.has(item.id));
  }, [profile, taxonomy]);

  const selectedBatch = useMemo(
    () => batches.find((item) => item.id === selectedBatchId) ?? null,
    [batches, selectedBatchId]
  );

  const parsedRowsPreview = useMemo(() => {
    try {
      const parsed = JSON.parse(jsonText) as unknown;
      return Array.isArray(parsed) ? parsed.length : 0;
    } catch {
      return 0;
    }
  }, [jsonText]);

  const canSubmitPeerReview =
    selectedBatch?.source !== VIRTUAL_REMOTE_BATCH_SOURCE &&
    selectedBatch?.import_status === "parsed" &&
    ["none", "submitted"].includes(selectedBatch.self_review_status) &&
    selectedBatch.success_count > 0 &&
    selectedBatch.peer_review_status !== "completed";

  async function handleReadFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setJsonText(text);
    if (!name || name === "expert-batch") {
      setName(file.name.replace(/\.[^.]+$/, ""));
    }
  }

  async function handleSubmit() {
    if (!applicationId) {
      setError("请先选择项目");
      return;
    }
    if (!technicalTypeCode) {
      setError("请先选择 QA 类型");
      return;
    }

    let rows: ExpertImportPushPayload["rows"] = [];
    try {
      const parsed = JSON.parse(jsonText) as unknown;
      if (!Array.isArray(parsed) || parsed.length === 0) {
        throw new Error("rows 必须是非空数组");
      }
      rows = parsed as ExpertImportPushPayload["rows"];
    } catch (err) {
      setError(err instanceof Error ? err.message : "JSON 解析失败");
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await apiFetch<{
        batch_id: number;
        existing_batch: boolean;
        parse_queued: boolean;
      }>("/api/expert/imports/push", {
        method: "POST",
        body: JSON.stringify({
          name,
          source,
          source_batch_name: sourceBatchName || undefined,
          external_batch_id: externalBatchId || undefined,
          application_id: Number(applicationId),
          technical_type_code: technicalTypeCode,
          business_tag_codes: selectedBusinessTags,
          rows,
          auto_parse: true,
          create_self_review: createSelfReview
        } satisfies ExpertImportPushPayload)
      });
      setSuccess(
        result.existing_batch
          ? `已命中已有批次 #${result.batch_id}`
          : `批次 #${result.batch_id} 已创建，并已进入解析队列`
      );
      await refreshBatches(result.batch_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交批次失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmitPeerReview() {
    if (!selectedBatch) return;
    setPeerSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await apiFetch<{
        created_count: number;
        blocked_count: number;
      }>(`/api/expert/imports/${selectedBatch.id}/submit-for-peer-review`, {
        method: "POST"
      });
      setSuccess(
        `已提交互评：新增 ${result.created_count} 个同行评审任务，未覆盖 ${result.blocked_count} 条`
      );
      await refreshBatches(selectedBatch.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交互评失败");
    } finally {
      setPeerSubmitting(false);
    }
  }

  const batchItems = detail?.items ?? [];
  const batchFailures = detail?.failures ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">我的上传</p>
          <h2 className="mt-2 font-serif text-4xl">上传 QA 批次，先自评，再提交同行复核</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="muted">桌面端可直接调用 `/api/expert/imports/push`</Badge>
          <Badge variant="warning">网页端支持手工粘贴 JSON 兜底</Badge>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {error}
        </div>
      ) : null}
      {success ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {success}
        </div>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[0.88fr_1.12fr]">
        <Card className="rounded-xl border border-border bg-white shadow-none">
          <CardHeader>
            <CardTitle>上传新批次</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <input
                className="field"
                placeholder="批次名称"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
              <input
                className="field"
                placeholder="来源标识"
                value={source}
                onChange={(event) => setSource(event.target.value)}
              />
              <input
                className="field"
                placeholder="来源批次名"
                value={sourceBatchName}
                onChange={(event) => setSourceBatchName(event.target.value)}
              />
              <input
                className="field"
                placeholder="外部批次 ID（做幂等）"
                value={externalBatchId}
                onChange={(event) => setExternalBatchId(event.target.value)}
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <select
                className="field"
                value={applicationId}
                onChange={(event) => setApplicationId(event.target.value)}
              >
                <option value="">选择项目</option>
                {allowedApplications.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
              <select
                className="field"
                value={technicalTypeCode}
                onChange={(event) => setTechnicalTypeCode(event.target.value)}
              >
                <option value="">选择 QA 类型</option>
                {taxonomy?.technical_types.map((item) => (
                  <option key={item.id} value={item.code}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <p className="text-sm font-medium">领域场景</p>
              <div className="flex flex-wrap gap-2">
                {allowedBusinessTags.length ? (
                  allowedBusinessTags.map((item: TaxonomyItem) => {
                    const selected = selectedBusinessTags.includes(item.code);
                    return (
                      <button
                        key={item.id}
                        type="button"
                        className={`rounded-md border px-3 py-1.5 text-sm transition ${
                          selected
                            ? "border-stone-900 bg-stone-900 text-white"
                            : "border-border bg-stone-50 text-foreground hover:bg-stone-100"
                        }`}
                        onClick={() =>
                          setSelectedBusinessTags((current) =>
                            selected
                              ? current.filter((code) => code !== item.code)
                              : [...current, item.code]
                          )
                        }
                      >
                        {item.name}
                      </button>
                    );
                  })
                ) : (
                  <div className="rounded-lg border border-dashed border-border bg-stone-50 px-3 py-4 text-sm text-muted-foreground">
                    当前账号还没有配置领域场景；如果你具备跨领域权限，可以留空后继续上传。
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-lg border border-border bg-stone-50 px-4 py-3">
              <label className="flex items-center gap-3 text-sm">
                <input
                  type="checkbox"
                  checked={createSelfReview}
                  onChange={(event) => setCreateSelfReview(event.target.checked)}
                />
                上传后自动为我创建自评任务
              </label>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button variant="secondary" onClick={() => fileInputRef.current?.click()}>
                读取本地 JSON
              </Button>
              <Button variant="secondary" onClick={() => setJsonText(examplePayload)}>
                填入示例
              </Button>
              <span className="text-sm text-muted-foreground">当前识别 {parsedRowsPreview} 条记录</span>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/json"
                className="hidden"
                onChange={(event) => void handleReadFile(event)}
              />
            </div>

            <textarea
              className="field min-h-[280px] font-mono text-xs leading-6"
              value={jsonText}
              onChange={(event) => setJsonText(event.target.value)}
            />

            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-muted-foreground">
                推荐每次上传一个来源批次；若提供 `external_batch_id`，重复推送会直接命中已有批次。
              </p>
              <Button onClick={() => void handleSubmit()} disabled={submitting || loading}>
                {submitting ? "正在提交…" : "上传并解析"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-xl border border-border bg-white shadow-none">
          <CardHeader className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle>我的批次</CardTitle>
              <p className="text-sm text-muted-foreground">
                {loading ? "正在加载…" : `共 ${batches.length} 个上传批次`}
              </p>
            </div>
            <Button variant="secondary" onClick={() => void loadBaseData()}>
              刷新
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {loading ? (
              <div className="rounded-lg border border-dashed border-border bg-stone-50 px-4 py-8 text-center text-sm text-muted-foreground">
                正在加载批次…
              </div>
            ) : null}

            {!loading && batches.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border bg-stone-50 px-4 py-8 text-center text-sm text-muted-foreground">
                还没有上传记录。可先从桌面端同步一批 QA，或在左侧手工粘贴 JSON 上传。
              </div>
            ) : null}

            {batches.map((batch) => {
              const selected = batch.id === selectedBatchId;
              return (
                <button
                  key={batch.id}
                  type="button"
                  className={`w-full rounded-lg border px-4 py-3 text-left transition ${
                    selected
                      ? "border-stone-900 bg-white shadow-sm"
                      : "border-border bg-stone-50 hover:bg-white"
                  }`}
                  onClick={() => setSelectedBatchId(batch.id)}
                >
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="space-y-2">
                      <div className="flex flex-wrap gap-2">
                        <Badge variant="muted">#{batch.id}</Badge>
                        <Badge variant="default">{importStatusLabel(batch.import_status)}</Badge>
                        <Badge variant={reviewStatusVariant(batch.self_review_status)}>
                          自评 {reviewStatusLabel(batch.self_review_status)}
                        </Badge>
                        <Badge variant={reviewStatusVariant(batch.peer_review_status)}>
                          互评 {reviewStatusLabel(batch.peer_review_status)}
                        </Badge>
                      </div>
                      <p className="font-medium">{batch.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {batch.application_name ?? "未绑定项目"} /{" "}
                        {batch.technical_type_name ?? batch.technical_type_code ?? "未绑定类型"}
                      </p>
                    </div>
                    <div className="space-y-1 text-right text-sm text-muted-foreground">
                      <p>{formatTime(batch.created_at)}</p>
                      <p>
                        成功 {batch.success_count} / 失败 {batch.fail_count}
                      </p>
                      <p>
                        自评 {batch.self_review_submitted}/{batch.self_review_total} · 互评{" "}
                        {batch.peer_review_submitted}/{batch.peer_review_total}
                      </p>
                    </div>
                  </div>
                </button>
              );
            })}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <Card className="rounded-xl border border-border bg-white shadow-none">
          <CardHeader className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle>批次详情</CardTitle>
              <p className="text-sm text-muted-foreground">
                {selectedBatch ? `批次 #${selectedBatch.id}` : "选择右上方任意批次查看详情"}
              </p>
            </div>
            <Button
              onClick={() => void handleSubmitPeerReview()}
              disabled={!canSubmitPeerReview || peerSubmitting}
            >
              {peerSubmitting ? "正在提交…" : "提交同行复核"}
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {!selectedBatch ? (
              <div className="rounded-lg border border-dashed border-border bg-stone-50 px-4 py-8 text-center text-sm text-muted-foreground">
                还没有选中批次。
              </div>
            ) : loadingDetail ? (
              <div className="rounded-lg border border-dashed border-border bg-stone-50 px-4 py-8 text-center text-sm text-muted-foreground">
                正在加载批次详情…
              </div>
            ) : (
              <>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-border bg-stone-50 px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
                      来源
                    </p>
                    <p className="mt-2 text-sm">{compactText(selectedBatch.source)}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      外部批次: {compactText(selectedBatch.external_batch_id)}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border bg-stone-50 px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
                      解析结果
                    </p>
                    <p className="mt-2 text-sm">
                      总计 {selectedBatch.total_count} / 成功 {selectedBatch.success_count} / 失败{" "}
                      {selectedBatch.fail_count}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      自评 {reviewStatusLabel(selectedBatch.self_review_status)} · 互评{" "}
                      {reviewStatusLabel(selectedBatch.peer_review_status)}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {parseTagCodes(selectedBatch.business_tags_json).map((tag) => (
                    <Badge key={tag} variant="warning">
                      {tag}
                    </Badge>
                  ))}
                </div>

                <div className="rounded-lg border border-border bg-stone-50 px-4 py-3 text-sm text-muted-foreground">
                  {selectedBatch.source === VIRTUAL_REMOTE_BATCH_SOURCE
                    ? "这是平台返回的“远程服务器虚拟批次”，用于承载所有未归入真实批次的 QA，当前仅支持浏览，不支持从这里直接提交同行复核。"
                    : "互评按钮会在“自评已提交”，或当前批次关闭自评时可用。平台会尽量把每条题补齐到 2 个 `initial_review` 任务；如果当前领域没有足够同行，会在结果里提示未覆盖条数。"}
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="font-medium">已导入 QA</p>
                    <p className="text-sm text-muted-foreground">{batchItems.length} 条</p>
                  </div>
                  <div className="space-y-2">
                    {batchItems.slice(0, 12).map((item) => (
                      <div
                        key={item.id}
                        className="rounded-lg border border-border bg-white px-4 py-3"
                      >
                        <div className="flex flex-wrap gap-2">
                          <Badge variant="muted">QA #{item.id}</Badge>
                          <Badge variant="default">{item.status}</Badge>
                          <Badge variant="warning">
                            自评 {compactText(item.self_review_task_status, "未生成")}
                          </Badge>
                          <Badge variant="muted">
                            互评 {item.peer_review_submitted}/{item.peer_review_total}
                          </Badge>
                        </div>
                        <p className="mt-3 font-medium">{item.question_summary}</p>
                        <p className="mt-2 text-sm text-muted-foreground line-clamp-2">
                          {compactText(item.current_answer_text)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="rounded-xl border border-border bg-white shadow-none">
          <CardHeader>
            <CardTitle>失败记录</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {batchFailures.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border bg-stone-50 px-4 py-8 text-center text-sm text-muted-foreground">
                当前批次没有解析失败记录。
              </div>
            ) : (
              batchFailures.map((item) => (
                <div key={item.id} className="rounded-lg border border-border bg-stone-50 px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="muted">行 {item.row_no}</Badge>
                    {item.external_id ? <Badge variant="warning">{item.external_id}</Badge> : null}
                  </div>
                  <p className="mt-3 font-medium">{compactText(item.question_preview)}</p>
                  <p className="mt-2 text-sm text-amber-700">{item.error_message}</p>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
