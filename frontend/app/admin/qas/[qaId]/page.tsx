"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { apiFetch, type QaDetail } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function decisionLabel(value: string | null) {
  if (value === "pass") return "通过";
  if (value === "rewrite") return "待改写";
  if (value === "fail") return "不通过";
  if (value === "pending") return "待聚合";
  return "未生成";
}

function decisionVariant(value: string | null) {
  if (value === "pass") return "success";
  if (value === "rewrite") return "warning";
  if (value === "fail") return "muted";
  return "default";
}

function formatRecordList(value: string | null) {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as string[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function formatTagList(value: string | null | undefined) {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as string[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

type QaMetadata = {
  scene_code?: string;
  scene_name?: string;
  module_key?: string;
  module_name?: string;
  action_key?: string;
  action_name?: string;
  seed_group?: string;
  cot_sequence_no?: number;
};

function parseQaMetadata(value: string | null | undefined) {
  if (!value) return {} as QaMetadata;
  try {
    const parsed = JSON.parse(value) as QaMetadata;
    return parsed && typeof parsed === "object" ? parsed : ({} as QaMetadata);
  } catch {
    return {} as QaMetadata;
  }
}

export default function AdminQaDetailPage() {
  const params = useParams<{ qaId: string }>();
  const qaId = params.qaId;
  const [detail, setDetail] = useState<QaDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [savingAnswerId, setSavingAnswerId] = useState<number | null>(null);
  const [rerunningAggregate, setRerunningAggregate] = useState(false);

  async function loadDetail(showLoading = true) {
    if (showLoading) setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<QaDetail>(`/api/admin/qas/${qaId}`);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 QA 详情失败");
    } finally {
      if (showLoading) setLoading(false);
    }
  }

  useEffect(() => {
    if (qaId) {
      void loadDetail();
    }
  }, [qaId]);

  async function handleConfirmFinalAnswer(answerId: number) {
    setSavingAnswerId(answerId);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/qas/${qaId}/final-answer`, {
        method: "POST",
        body: JSON.stringify({ answer_id: answerId })
      });
      setNotice("最终标准答案已确认。");
      await loadDetail(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "确认最终标准答案失败");
    } finally {
      setSavingAnswerId(null);
    }
  }

  async function handleRerunAggregate() {
    setRerunningAggregate(true);
    setError(null);
    setNotice(null);
    try {
      const result = await apiFetch<{ job_id: string; answer_id: number }>(
        `/api/admin/qas/${qaId}/aggregate/run`,
        { method: "POST" }
      );
      setNotice(`已创建聚合任务 ${result.job_id}，基于 answer #${result.answer_id} 重新计算。`);
      await loadDetail(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "重跑聚合失败");
    } finally {
      setRerunningAggregate(false);
    }
  }

  const aggregateAnswerId = detail?.aggregate?.current_answer_id ?? null;
  const finalStandardAnswerId = detail?.aggregate?.final_standard_answer_id ?? null;
  const agreementScore = detail?.aggregate?.agreement_score ?? null;
  const aggregateAnswer = useMemo(
    () => detail?.answers.find((answer) => answer.id === aggregateAnswerId) ?? null,
    [detail, aggregateAnswerId]
  );
  const finalAnswer = useMemo(
    () => detail?.answers.find((answer) => answer.id === finalStandardAnswerId) ?? null,
    [detail, finalStandardAnswerId]
  );
  const businessTags = useMemo(
    () => formatTagList(detail?.qa_item.business_tags_json),
    [detail?.qa_item.business_tags_json]
  );
  const metadata = useMemo(
    () => parseQaMetadata(detail?.qa_item.metadata_json),
    [detail?.qa_item.metadata_json]
  );

  if (loading) {
    return (
      <div className="rounded-[28px] border border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
        正在加载 QA 详情…
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        {error ?? "QA 不存在"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            QA 详情 / {detail.qa_item.external_id || `QA-${detail.qa_item.id}`}
          </p>
          <h2 className="mt-2 font-serif text-4xl">单题视角查看当前聚合指向与最终确认</h2>
        </div>
        <div className="flex gap-3">
          <Button
            variant="secondary"
            disabled={rerunningAggregate}
            onClick={() => void handleRerunAggregate()}
          >
            {rerunningAggregate ? "提交中…" : "重跑聚合"}
          </Button>
          <Button variant="secondary" onClick={() => void loadDetail(false)}>
            刷新详情
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

      <section className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <Card>
          <CardHeader>
            <CardTitle>问题与状态</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-7 text-muted-foreground">
            <p>项目：{detail.qa_item.application_name}</p>
            <p>QA 类型：{detail.qa_item.technical_type_name || "未定义"}</p>
            <p>领域场景：{metadata.scene_name ?? businessTags[0] ?? "未标注"}</p>
            {metadata.module_name ? <p>研究模块：{metadata.module_name}</p> : null}
            {metadata.action_name ? <p>推理动作：{metadata.action_name}</p> : null}
            {metadata.cot_sequence_no ? <p>CoT 序号：{metadata.cot_sequence_no}</p> : null}
            <p>问题：{detail.qa_item.question_text}</p>
            <p>来源：{detail.qa_item.source || "未记录"}</p>
            <div className="flex flex-wrap gap-2">
              <Badge variant="muted">{detail.qa_item.status}</Badge>
              {detail.qa_item.technical_type_name ? (
                <Badge variant="warning">{detail.qa_item.technical_type_name}</Badge>
              ) : null}
              {metadata.module_name ? <Badge variant="default">{metadata.module_name}</Badge> : null}
              {metadata.action_name ? <Badge variant="muted">{metadata.action_name}</Badge> : null}
              <Badge variant={decisionVariant(detail.aggregate?.final_decision ?? "pending")}>
                {decisionLabel(detail.aggregate?.final_decision ?? "pending")}
              </Badge>
              <Badge variant="muted">
                评审人数 {detail.aggregate?.review_count ?? 0}
              </Badge>
              {businessTags.map((tag) => (
                <Badge key={tag} variant="muted">
                  {tag}
                </Badge>
              ))}
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <p>
                一致性：
                {agreementScore === null ? "未生成" : agreementScore.toFixed(2)}
              </p>
              <p>
                当前聚合答案：
                {aggregateAnswer ? `#${aggregateAnswer.id}` : "未生成"}
              </p>
              <p>
                最终标准答案：
                {finalAnswer ? `#${finalAnswer.id}` : "未确认"}
              </p>
              <p>
                是否同一答案：
                {aggregateAnswer && finalAnswer
                  ? aggregateAnswer.id === finalAnswer.id
                    ? "是"
                    : "否"
                  : "未确定"}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>CoT 链路与聚合说明</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-7 text-muted-foreground">
            <div className="rounded-[28px] border border-border bg-stone-50 p-4">
              <p className="font-medium text-foreground">研究链路定位</p>
              <p className="mt-2">
                {metadata.module_name || metadata.action_name
                  ? `这道题当前位于“${metadata.module_name ?? "未标注模块"} / ${metadata.action_name ?? "未标注动作"}”节点，用于把单题评测挂到同一场景的研究链路中。`
                  : "当前题目没有标注 CoT 链路元数据。"}
              </p>
            </div>
            <div className="rounded-[28px] border border-border bg-stone-50 p-4">
              <p className="font-medium text-foreground">当前聚合指向</p>
              <p className="mt-2">
                {aggregateAnswer
                  ? "这是当前聚合策略认为最应该继续使用或进入下一步确认的答案。"
                  : "当前还没有可用的聚合答案。"}
              </p>
            </div>
            <div className="rounded-[28px] border border-border bg-stone-50 p-4">
              <p className="font-medium text-foreground">最终标准答案</p>
              <p className="mt-2">
                最终标准答案必须由管理员确认；它可以和当前聚合答案一致，也可以被管理员改判为另一条候选答案。
              </p>
            </div>
            <div className="rounded-[28px] border border-border bg-stone-50 p-4">
              <p className="font-medium text-foreground">重跑聚合的用途</p>
              <p className="mt-2">
                当新评测记录已经提交、但聚合结果还没刷新时，可以手动重跑一次聚合任务。
              </p>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>专家评测摘要</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-7 text-muted-foreground">
            {detail.records.length === 0 ? <p>当前还没有评测记录。</p> : null}
            {detail.records.map((record) => {
              const tags = formatRecordList(record.quick_comment_codes);
              return (
                <div key={record.id} className="rounded-3xl border border-border bg-stone-50 p-4">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge variant="muted">专家 #{record.expert_user_id}</Badge>
                    <Badge variant={decisionVariant(record.overall_decision)}>
                      {decisionLabel(record.overall_decision)}
                    </Badge>
                  </div>
                  <p>
                    正确性 {record.correctness_rating}，完整性 {record.completeness_rating}，相关性{" "}
                    {record.relevance_rating}，清晰度 {record.clarity_rating}
                  </p>
                  <p>风险：{record.risk_flag}</p>
                  {detail.qa_item.technical_type_code === "cot_qa" ? (
                    <p>
                      推理链完整性 {record.reasoning_completeness || "未填"}，推理链自洽性{" "}
                      {record.reasoning_consistency || "未填"}，结论与推理一致性{" "}
                      {record.reasoning_support || "未填"}
                    </p>
                  ) : null}
                  {tags.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {tags.map((tag) => (
                        <Badge key={`${record.id}-${tag}`} variant="warning">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>答案版本与聚合定位</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {detail.answers.map((answer) => {
              const isAggregate = aggregateAnswerId === answer.id;
              const isFinal = finalStandardAnswerId === answer.id;
              return (
                <div
                  key={answer.id}
                  className="flex flex-col gap-3 rounded-3xl border border-border bg-stone-50 p-4 lg:flex-row lg:items-center lg:justify-between"
                >
                  <div className="max-w-4xl">
                    <div className="mb-2 flex flex-wrap gap-2">
                      <Badge variant={isFinal ? "success" : "muted"}>
                        {answer.answer_type}
                      </Badge>
                      <Badge variant="warning">v{answer.version_no}</Badge>
                      {isAggregate ? <Badge variant="default">当前聚合选中</Badge> : null}
                      {isFinal ? <Badge variant="success">最终标准答案</Badge> : null}
                    </div>
                    <p className="text-sm leading-7 text-muted-foreground">{answer.answer_text}</p>
                  </div>
                  <Button
                    size="sm"
                    variant={isFinal ? "default" : "secondary"}
                    disabled={savingAnswerId === answer.id}
                    onClick={() => void handleConfirmFinalAnswer(answer.id)}
                  >
                    {savingAnswerId === answer.id
                      ? "提交中…"
                      : isFinal
                        ? "当前最终标准答案"
                        : "设为最终标准答案"}
                  </Button>
                </div>
              );
            })}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
