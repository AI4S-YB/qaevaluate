"use client";

import { useEffect, useMemo, useState } from "react";

import {
  apiFetch,
  type AdminApplicationItem,
  type ImportBatch,
  type ImportFailure,
  type ImportFailureDetail,
  type TaxonomyItem
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

function parseBusinessTags(value: string | null) {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as string[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

const importExamples = {
  direct_qa: {
    title: "普通QA示例",
    filename: "qa-import-example-direct.json",
    content: JSON.stringify(
      [
        {
          id: "qa_001",
          question: "番茄晚疫病如何防治？",
          answer:
            "番茄晚疫病应以预防为主、综合防治为核心。首先应清除病残体并与非茄科作物轮作2至3年，以减少田间病原基数。连续阴雨条件下，要控制田间湿度，建议采用高畦栽培、合理密植和及时整枝打杈，使叶面露水尽量在上午10点前散去。发病初期可每7天左右喷施一次保护性或治疗性杀菌剂，如代森锰锌、百菌清或氟吡菌胺类药剂，并注意不同作用机制药剂轮换，以降低抗药性风险。其原理在于降低叶面持续湿润时间可抑制病菌孢子萌发，而轮换用药可减少单一药剂长期使用带来的选择压力。",
          context: "露地栽培，近期连续阴雨。"
        }
      ],
      null,
      2
    )
  },
  cot_qa: {
    title: "CoT示例",
    filename: "qa-import-example-cot.json",
    content: JSON.stringify(
      [
        {
          id: "cot_001",
          question:
            "番茄大棚夜间湿度长期高于90%，近三天出现下部叶片水渍状病斑，且预报未来一周仍有阴雨天气。请判断最优先采取的防控策略，并说明原因。",
          answer:
            "最优先的策略是先迅速降低棚内叶面持续结露时间，同时立即启动针对晚疫病的保护加治疗联合防控。推理过程如下：第一，夜间湿度长期高于90%且出现水渍状病斑，说明病害发生条件已经满足，并且很可能进入初侵染到扩展阶段；如果此时只喷药而不控湿，病原仍会在高湿条件下继续萌发传播。第二，未来一周仍有阴雨，环境风险不会自然解除，因此应优先通过清晨短时放风、增设循环风机、减少傍晚灌溉、清理下部老叶等方式，把叶面连续湿润时间尽量压到8小时以下。第三，在控湿的同时，于24小时内喷施保护性与治疗性药剂组合，并在5至7天后依据病情复喷。这样做的原理是先切断病原继续扩展所依赖的高湿环境，再用药剂压低现有侵染强度，从而同时控制病害速度和后续损失。",
          context: "设施栽培，目标是给种植技术员做现场决策参考。"
        }
      ],
      null,
      2
    )
  }
} as const;

function classifyImportError(message: string) {
  if (message.includes("technical_type not found")) {
    return {
      label: "QA 类型不存在",
      hint: "当前批次绑定的 QA 类型未在后台配置中启用。"
    };
  }
  if (message.includes("business_tag not found")) {
    return {
      label: "领域场景不存在",
      hint: "当前批次绑定的领域场景包含未定义或未启用的配置。"
    };
  }
  if (message.includes("business_tags must be an array")) {
    return {
      label: "领域场景格式错误",
      hint: "上传批次时绑定的领域场景参数格式不正确。"
    };
  }
  if (message.includes("application not found")) {
    return {
      label: "项目不存在",
      hint: "当前批次绑定的项目未在后台配置中启用。"
    };
  }
  if (message.includes("missing answer")) {
    return {
      label: "答案缺失",
      hint: "answer 为空，且 candidate_answers 中也没有可用答案。"
    };
  }
  return {
    label: "通用导入错误",
    hint: "请检查字段名、字段类型和必填项。"
  };
}

export default function AdminImportsPage() {
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [applications, setApplications] = useState<AdminApplicationItem[]>([]);
  const [technicalTypes, setTechnicalTypes] = useState<TaxonomyItem[]>([]);
  const [businessTags, setBusinessTags] = useState<TaxonomyItem[]>([]);
  const [failureDetail, setFailureDetail] = useState<ImportFailureDetail | null>(null);
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null);
  const [selectedFailureId, setSelectedFailureId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingFailures, setLoadingFailures] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [source, setSource] = useState("");
  const [applicationId, setApplicationId] = useState("");
  const [technicalTypeCode, setTechnicalTypeCode] = useState("");
  const [selectedBusinessTags, setSelectedBusinessTags] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [parsingId, setParsingId] = useState<number | null>(null);
  const [openExampleKey, setOpenExampleKey] = useState<keyof typeof importExamples | null>(null);

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

  async function loadTaxonomy() {
    try {
      const [applicationData, technicalTypeData, businessTagData] = await Promise.all([
        apiFetch<AdminApplicationItem[]>("/api/admin/applications"),
        apiFetch<TaxonomyItem[]>("/api/admin/technical-types"),
        apiFetch<TaxonomyItem[]>("/api/admin/business-tags")
      ]);
      setApplications(applicationData.filter((item) => Boolean(item.is_active)));
      setTechnicalTypes(technicalTypeData.filter((item) => item.is_active));
      setBusinessTags(businessTagData.filter((item) => item.is_active));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载分类配置失败");
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
    if (!technicalTypeCode) {
      setError("请先为本批次选择一个 QA 类型");
      return;
    }
    if (!applicationId) {
      setError("请先为本批次选择一个项目");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("name", name || "manual-batch");
      formData.append("source", source || "manual-upload");
      formData.append("application_id", applicationId);
      formData.append("technical_type_code", technicalTypeCode);
      formData.append("business_tags_json", JSON.stringify(selectedBusinessTags));
      await apiFetch("/api/admin/imports/upload", {
        method: "POST",
        body: formData
      });
      setName("");
      setSource("");
      setApplicationId("");
      setTechnicalTypeCode("");
      setSelectedBusinessTags([]);
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
    void loadTaxonomy();
  }, []);

  const selectedFailure =
    failureDetail?.failures.find((item) => item.id === selectedFailureId) ??
    failureDetail?.failures[0] ??
    null;
  const batchesWithFailures = useMemo(
    () => batches.filter((batch) => batch.fail_count > 0),
    [batches]
  );
  const selectedFailureCategory = selectedFailure
    ? classifyImportError(selectedFailure.error_message)
    : null;
  const openExample = openExampleKey ? importExamples[openExampleKey] : null;

  function handleDownloadExample(exampleKey: keyof typeof importExamples) {
    const example = importExamples[exampleKey];
    const blob = new Blob([example.content], { type: "application/json;charset=utf-8" });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = example.filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">数据导入</p>
        <h2 className="mt-2 font-serif text-4xl">上传 JSON，并在导入入口就锁定 QA 类型与领域场景</h2>
      </div>
      <section>
        <Card>
          <CardHeader>
            <CardTitle>导入字段规范</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-[28px] border border-border bg-stone-50 p-5 text-sm leading-7 text-muted-foreground">
              每条记录至少应包含 `question`、`answer`。项目、QA 类型与领域场景都在上传批次时统一指定，
              不再要求每条记录自己携带 `application`、`technical_type` 或 `business_tags`。
            </div>
            <div className="flex flex-wrap items-center gap-3 rounded-[28px] border border-border bg-white p-4">
              <span className="text-sm text-muted-foreground">导入示例：</span>
              <button
                type="button"
                className="text-sm font-medium text-emerald-700 underline decoration-emerald-200 underline-offset-4"
                onClick={() => setOpenExampleKey("direct_qa")}
              >
                普通QA示例
              </button>
              <button
                type="button"
                className="text-sm font-medium text-emerald-700 underline decoration-emerald-200 underline-offset-4"
                onClick={() => setOpenExampleKey("cot_qa")}
              >
                CoT示例
              </button>
            </div>
            <pre className="overflow-x-auto rounded-3xl border border-border bg-white p-4 text-xs leading-6 text-muted-foreground">
{`[
  {
    "id": "qa_001",
    "question": "番茄晚疫病如何防治？",
    "answer": "可通过轮作、降低湿度、及时喷施保护性杀菌剂等方式防治。",
    "context": "露地栽培，近期连续阴雨。"
  }
]`}
            </pre>
          </CardContent>
        </Card>
      </section>
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
            <select
              className="field"
              value={applicationId}
              onChange={(event) => setApplicationId(event.target.value)}
            >
              <option value="">选择本批次项目</option>
              {applications.map((item) => (
                <option key={item.id} value={String(item.id)}>
                  {item.name}
                </option>
              ))}
            </select>
            <select
              className="field"
              value={technicalTypeCode}
              onChange={(event) => setTechnicalTypeCode(event.target.value)}
            >
              <option value="">选择本批次 QA 类型</option>
              {technicalTypes.map((item) => (
                <option key={item.id} value={item.code}>
                  {item.name}
                </option>
              ))}
            </select>
            <div className="rounded-3xl border border-border bg-stone-50 p-4">
              <p className="mb-3 text-sm font-medium">为本批次选择领域场景</p>
              <div className="flex flex-wrap gap-2">
                {businessTags.map((item) => {
                  const selected = selectedBusinessTags.includes(item.code);
                  return (
                    <Button
                      key={item.id}
                      size="sm"
                      variant={selected ? "default" : "secondary"}
                      onClick={() =>
                        setSelectedBusinessTags((current) =>
                          selected
                            ? current.filter((code) => code !== item.code)
                            : [...current, item.code]
                        )
                      }
                    >
                      {item.name}
                    </Button>
                  );
                })}
              </div>
            </div>
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
                    <div className="mt-2 flex flex-wrap gap-2">
                      {batch.application_name ? (
                        <Badge variant="default">{batch.application_name}</Badge>
                      ) : null}
                      {batch.technical_type_name ? (
                        <Badge variant="warning">{batch.technical_type_name}</Badge>
                      ) : null}
                      {parseBusinessTags(batch.business_tags_json).map((tag) => (
                        <Badge key={`${batch.id}-${tag}`} variant="muted">
                          {tag}
                        </Badge>
                      ))}
                    </div>
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
                  {failureDetail.batch.application_name ? (
                    <div className="mt-3">
                      <Badge variant="default">{failureDetail.batch.application_name}</Badge>
                    </div>
                  ) : null}
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
                      {selectedFailureCategory ? (
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <Badge variant="warning">{selectedFailureCategory.label}</Badge>
                          <span className="text-xs text-amber-700">
                            {selectedFailureCategory.hint}
                          </span>
                        </div>
                      ) : null}
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

      {openExample ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/40 p-4 backdrop-blur-sm">
          <div className="flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden rounded-[32px] border border-border bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <div>
                <p className="text-sm text-muted-foreground">导入示例</p>
                <h3 className="text-xl font-semibold text-foreground">{openExample.title}</h3>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => handleDownloadExample(openExampleKey!)}
                >
                  下载示例
                </Button>
                <Button variant="secondary" size="sm" onClick={() => setOpenExampleKey(null)}>
                  关闭
                </Button>
              </div>
            </div>
            <div className="overflow-y-auto px-6 py-5">
              <pre className="overflow-x-auto rounded-3xl border border-border bg-stone-50 p-5 text-xs leading-6 text-muted-foreground">
                {openExample.content}
              </pre>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
