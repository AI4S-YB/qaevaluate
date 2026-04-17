"use client";

import { useEffect, useState } from "react";

import { apiFetch, type AdminAnalyticsSummary } from "@/lib/api";
import { MetricCard } from "@/components/metric-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AdminAnalyticsPage() {
  const [summary, setSummary] = useState<AdminAnalyticsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadSummary() {
      try {
        const data = await apiFetch<AdminAnalyticsSummary>("/api/admin/analytics/summary");
        setSummary(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载统计失败");
      }
    }
    void loadSummary();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">统计分析</p>
        <h2 className="mt-2 font-serif text-4xl">让任务量、通过率和争议率一眼可见</h2>
      </div>

      {error ? (
        <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {error}
        </div>
      ) : null}

      <section className="section-grid">
        <MetricCard
          label="通过率"
          value={`${summary?.metrics.pass_rate ?? 0}%`}
          note="基于 qa_aggregates.final_decision=pass"
        />
        <MetricCard
          label="待改写率"
          value={`${summary?.metrics.rewrite_rate ?? 0}%`}
          note="已形成最终结论样本中的 rewrite 占比"
        />
        <MetricCard
          label="争议率"
          value={`${summary?.metrics.dispute_rate ?? 0}%`}
          note="触发 dispute_review 的 QA 占总 QA 的比例"
        />
        <MetricCard
          label="LLM 采用率"
          value={`${summary?.metrics.llm_adoption_rate ?? 0}%`}
          note="evaluation_record 中采用改写答案的比例"
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <Card>
          <CardHeader>
            <CardTitle>应用维度分析</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {summary?.application_breakdown.map((application) => (
              <div
                key={application.id}
                className="rounded-3xl border border-border bg-stone-50 p-4 text-sm text-muted-foreground"
              >
                <div className="mb-2 flex items-center justify-between">
                  <p className="font-medium text-foreground">{application.name}</p>
                  <span>{application.total_qas} 条</span>
                </div>
                <p>
                  pass {application.pass_count} / rewrite {application.rewrite_count} / fail{" "}
                  {application.fail_count}
                </p>
                <p>
                  平均一致性：
                  {application.avg_agreement === null
                    ? " 未生成"
                    : ` ${application.avg_agreement.toFixed(2)}`}
                </p>
              </div>
            ))}
            {!summary || summary.application_breakdown.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                当前还没有应用分析数据。
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>专家活跃度</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {summary?.top_experts.map((expert) => (
              <div
                key={expert.id}
                className="flex items-center justify-between rounded-3xl border border-border bg-stone-50 p-4"
              >
                <p className="font-medium">{expert.full_name}</p>
                <p className="text-sm text-muted-foreground">
                  完成 {expert.completed_reviews} 条
                </p>
              </div>
            ))}
            {!summary || summary.top_experts.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                当前还没有专家活跃数据。
              </div>
            ) : null}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
