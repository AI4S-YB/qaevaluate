"use client";

import { useEffect, useMemo, useState } from "react";

import { apiFetch, type AdminDashboard } from "@/lib/api";
import { MetricCard } from "@/components/metric-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function progressPercent(reviewed: number, total: number) {
  if (!total) return 0;
  return Math.round((reviewed / total) * 100);
}

export default function AdminDashboardPage() {
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadDashboard() {
      try {
        const data = await apiFetch<AdminDashboard>("/api/admin/dashboard");
        setDashboard(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载仪表盘失败");
      }
    }
    void loadDashboard();
  }, []);

  const topApplication = useMemo(() => {
    if (!dashboard) return null;
    return [...dashboard.application_progress].sort((left, right) => {
      const leftRate = progressPercent(left.reviewed_qas, left.total_qas);
      const rightRate = progressPercent(right.reviewed_qas, right.total_qas);
      return rightRate - leftRate;
    })[0];
  }, [dashboard]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">管理仪表盘</p>
        <h2 className="mt-2 font-serif text-4xl">把评测流程压缩成清晰的运营视图</h2>
      </div>

      {error ? (
        <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {error}
        </div>
      ) : null}

      <section className="section-grid">
        <MetricCard
          label="待审核专家"
          value={String(dashboard?.metrics.pending_experts ?? 0)}
          note="等待管理员处理的新注册申请"
        />
        <MetricCard
          label="待分发 QA"
          value={String(dashboard?.metrics.pending_qas ?? 0)}
          note="当前处于 active 状态的待分发问题"
        />
        <MetricCard
          label="进行中任务"
          value={String(dashboard?.metrics.ongoing_tasks ?? 0)}
          note="pending 与 in_progress 任务总数"
        />
        <MetricCard
          label="争议样本"
          value={String(dashboard?.metrics.disputed_qas ?? 0)}
          note="已触发 dispute_review 的问题数"
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <Card>
          <CardHeader>
            <CardTitle>应用进度</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {dashboard?.application_progress.map((application) => (
              <div
                key={application.id}
                className="rounded-3xl border border-border bg-stone-50 p-4"
              >
                <div className="mb-2 flex items-center justify-between">
                  <p className="font-medium">{application.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {application.reviewed_qas}/{application.total_qas}
                  </p>
                </div>
                <div className="h-2 rounded-full bg-stone-200">
                  <div
                    className="h-2 rounded-full bg-primary"
                    style={{
                      width: `${progressPercent(
                        application.reviewed_qas,
                        application.total_qas
                      )}%`
                    }}
                  />
                </div>
              </div>
            ))}
            {!dashboard || dashboard.application_progress.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
                当前没有应用进度数据。
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="bg-stone-50">
          <CardHeader>
            <CardTitle>当前判断</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-7 text-muted-foreground">
            <p>
              当前总 QA 数为 {dashboard?.metrics.total_qas ?? 0}，其中已完成评测{" "}
              {dashboard?.metrics.reviewed_qas ?? 0} 条。
            </p>
            <p>
              已导入批次 {dashboard?.metrics.imported_batches ?? 0} 个，平台仍应优先处理
              active 状态样本。
            </p>
            <p>
              {topApplication
                ? `${topApplication.name} 当前完成率最高，可优先沉淀标准答案库。`
                : "待有更多实际数据后再生成运营建议。"}
            </p>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
