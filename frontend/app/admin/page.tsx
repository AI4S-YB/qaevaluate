"use client";

import { useEffect, useState } from "react";

import { apiFetch, type AdminDashboard, type NewsItem, type PublicStats } from "@/lib/api";
import { MetricCard } from "@/components/metric-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function progressPercent(reviewed: number, total: number) {
  if (!total) return 0;
  return Math.round((reviewed / total) * 100);
}

export default function AdminDashboardPage() {
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null);
  const [newsList, setNewsList] = useState<NewsItem[]>([]);
  const [stats, setStats] = useState<PublicStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadDashboard() {
      try {
        const [data, newsData, statsData] = await Promise.all([
          apiFetch<AdminDashboard>("/api/admin/dashboard"),
          apiFetch<NewsItem[]>("/api/news"),
          apiFetch<PublicStats>("/api/stats")
        ]);
        setDashboard(data);
        setNewsList(newsData);
        setStats(statsData);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载仪表盘失败");
      }
    }
    void loadDashboard();
  }, []);

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

      {stats ? (
        <section className="flex flex-wrap gap-3 rounded-3xl border border-border bg-stone-50 px-5 py-3 text-sm text-muted-foreground">
          <span>今日新增 QA <strong className="text-foreground">{stats.today_qa_count}</strong> 条</span>
          <span className="text-stone-300">|</span>
          <span>本周新增 QA <strong className="text-foreground">{stats.week_qa_count}</strong> 条</span>
          <span className="text-stone-300">|</span>
          <span>今日评审 <strong className="text-foreground">{stats.today_review_count}</strong> 条</span>
          <span className="text-stone-300">|</span>
          <span>本周评审 <strong className="text-foreground">{stats.week_review_count}</strong> 条</span>
          <span className="text-stone-300">|</span>
          <span>可用试用模型 <strong className="text-foreground">{stats.available_model_count}</strong> 个</span>
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <Card>
          <CardHeader>
            <CardTitle>项目进度</CardTitle>
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
                当前没有项目进度数据。
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="bg-stone-50">
          <CardHeader>
            <CardTitle>最新消息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {newsList.length ? (
              newsList.map((item) => (
                <div
                  key={item.id}
                  className="rounded-[24px] border border-border bg-white/80 p-4"
                >
                  <p className="font-medium">{item.title}</p>
                  <p className="mt-2 text-sm leading-7 text-muted-foreground">
                    {item.content}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {item.created_at.replace("T", " ").slice(0, 16)}
                  </p>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">暂无最新消息。</p>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
