"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiFetch, type ExpertHistoryItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatTime(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

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

function taskTypeLabel(value: ExpertHistoryItem["task_type"]) {
  if (value === "dispute_review") return "争议复核";
  if (value === "final_confirm") return "最终确认";
  return "初评";
}

export default function ExpertHistoryPage() {
  const [history, setHistory] = useState<ExpertHistoryItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [decisionFilter, setDecisionFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadHistory() {
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch<ExpertHistoryItem[]>("/api/expert/history");
        setHistory(data);
        if (data.length > 0) {
          setSelectedId((current) => current ?? data[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载历史失败");
      } finally {
        setLoading(false);
      }
    }

    void loadHistory();
  }, []);

  const filteredHistory = useMemo(() => {
    return history.filter((item) => {
      if (decisionFilter === "all") return true;
      return item.overall_decision === decisionFilter;
    });
  }, [history, decisionFilter]);

  const selectedItem =
    filteredHistory.find((item) => item.id === selectedId) ??
    history.find((item) => item.id === selectedId) ??
    filteredHistory[0] ??
    null;

  const summary = useMemo(() => {
    return history.reduce(
      (acc, item) => {
        acc.total += 1;
        if (item.overall_decision === "rewrite") acc.rewrite += 1;
        if (item.adopted_rewrite_answer_id) acc.adopted += 1;
        if (item.adopted_became_final) acc.becameFinal += 1;
        return acc;
      },
      { total: 0, rewrite: 0, adopted: 0, becameFinal: 0 }
    );
  }, [history]);

  if (loading) {
    return (
      <div className="rounded-[28px] border border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
        正在加载历史记录…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">我的历史</p>
          <h2 className="mt-2 font-serif text-4xl">回看已提交的评测、改写选择与当前聚合结果</h2>
        </div>
        <div className="flex gap-3">
          <Button asChild variant="secondary">
            <Link href="/expert/tasks">回到任务列表</Link>
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {error}
        </div>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          ["已提交评测", summary.total],
          ["待改写决策", summary.rewrite],
          ["选过候选答案", summary.adopted],
          ["最终被采纳", summary.becameFinal]
        ].map(([label, value]) => (
          <Card key={label}>
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">{label}</p>
              <p className="mt-3 text-3xl font-semibold">{value}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      <Card>
        <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <CardTitle>筛选</CardTitle>
            <p className="text-sm text-muted-foreground">
              当前 {filteredHistory.length} 条 / 全部 {history.length} 条
            </p>
          </div>
          <select
            className="field min-w-[180px]"
            value={decisionFilter}
            onChange={(event) => setDecisionFilter(event.target.value)}
          >
            <option value="all">全部结论</option>
            <option value="pass">通过</option>
            <option value="rewrite">待改写</option>
            <option value="fail">不通过</option>
          </select>
        </CardHeader>
      </Card>

      <section className="grid gap-4 xl:grid-cols-[0.96fr_1.04fr]">
        <Card>
          <CardHeader>
            <CardTitle>提交记录</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {filteredHistory.map((item) => {
              const selected = selectedItem?.id === item.id;
              return (
                <div
                  key={item.id}
                  className={`cursor-pointer rounded-[28px] border p-4 transition ${
                    selected
                      ? "border-stone-900 bg-white shadow-sm"
                      : "border-border bg-stone-50 hover:bg-white"
                  }`}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedId(item.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedId(item.id);
                    }
                  }}
                >
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <p className="text-sm text-muted-foreground">{item.application_name}</p>
                      <p className="font-medium">{item.question_summary}</p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {formatTime(item.submitted_at)} / {taskTypeLabel(item.task_type)}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant={decisionVariant(item.overall_decision)}>
                        {decisionLabel(item.overall_decision)}
                      </Badge>
                      <Badge variant="muted">{item.llm_session_count} 次 LLM</Badge>
                    </div>
                  </div>
                </div>
              );
            })}

            {filteredHistory.length === 0 ? (
              <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                当前筛选条件下没有历史记录。
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>记录详情</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!selectedItem ? (
              <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                选择左侧任意一条评测记录查看详情。
              </div>
            ) : (
              <>
                <div className="rounded-[28px] border border-border bg-stone-50 p-5">
                  <div className="flex flex-wrap items-center gap-3">
                    <Badge variant="muted">{selectedItem.application_name}</Badge>
                    <Badge variant={decisionVariant(selectedItem.overall_decision)}>
                      我的结论: {decisionLabel(selectedItem.overall_decision)}
                    </Badge>
                    <Badge variant={decisionVariant(selectedItem.aggregate_final_decision)}>
                      当前聚合: {decisionLabel(selectedItem.aggregate_final_decision)}
                    </Badge>
                  </div>
                  <p className="mt-4 text-lg leading-8">{selectedItem.question_text}</p>
                  <p className="mt-3 text-sm text-muted-foreground">
                    提交于 {formatTime(selectedItem.submitted_at)} / {taskTypeLabel(selectedItem.task_type)}
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  {[
                    ["正确性", selectedItem.correctness_rating],
                    ["完整性", selectedItem.completeness_rating],
                    ["相关性", selectedItem.relevance_rating],
                    ["清晰度", selectedItem.clarity_rating],
                    ["风险标记", selectedItem.risk_flag],
                    ["评审人数", selectedItem.review_count ?? "未聚合"]
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-[24px] border border-border bg-white p-4">
                      <p className="text-sm text-muted-foreground">{label}</p>
                      <p className="mt-2 font-medium">{value}</p>
                    </div>
                  ))}
                </div>

                <div className="rounded-[28px] border border-border bg-stone-50 p-5">
                  <p className="text-sm font-medium">快速原因标签</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {selectedItem.quick_comment_codes.length > 0 ? (
                      selectedItem.quick_comment_codes.map((code) => (
                        <Badge key={code} variant="warning">
                          {code}
                        </Badge>
                      ))
                    ) : (
                      <p className="text-sm text-muted-foreground">当时没有选择快速标签。</p>
                    )}
                  </div>
                </div>

                <div className="rounded-[28px] border border-border bg-stone-50 p-5">
                  <p className="text-sm font-medium">候选答案采用情况</p>
                  {selectedItem.adopted_rewrite_answer_text ? (
                    <>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Badge variant="success">曾选择候选答案</Badge>
                        {selectedItem.adopted_became_final ? (
                          <Badge variant="warning">最终被采纳</Badge>
                        ) : null}
                      </div>
                      <p className="mt-3 text-sm leading-7 text-muted-foreground">
                        {selectedItem.adopted_rewrite_answer_text}
                      </p>
                    </>
                  ) : (
                    <p className="mt-3 text-sm text-muted-foreground">
                      这次提交没有选择候选改写答案。
                    </p>
                  )}
                </div>

                <div className="rounded-[28px] border border-border bg-stone-50 p-5">
                  <p className="text-sm font-medium">当前最终标准答案</p>
                  {selectedItem.final_standard_answer_text ? (
                    <p className="mt-3 text-sm leading-7 text-muted-foreground">
                      {selectedItem.final_standard_answer_text}
                    </p>
                  ) : (
                    <p className="mt-3 text-sm text-muted-foreground">
                      当前还没有最终标准答案，或管理员尚未确认。
                    </p>
                  )}
                  {selectedItem.agreement_score !== null ? (
                    <p className="mt-3 text-xs text-muted-foreground">
                      当前一致性分数 {selectedItem.agreement_score}
                    </p>
                  ) : null}
                </div>

                <div className="flex justify-end">
                  <Button asChild variant="secondary">
                    <Link href={`/expert/tasks/${selectedItem.task_id}`}>重新打开该任务</Link>
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
