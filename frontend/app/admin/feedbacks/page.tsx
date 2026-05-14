"use client";

import { useEffect, useState } from "react";

import { apiFetch, type FeedbackItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatTime(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

function categoryLabel(value: string) {
  const map: Record<string, string> = {
    general: "通用",
    bug: "问题反馈",
    feature: "功能建议",
    data: "数据问题",
    other: "其他"
  };
  return map[value] ?? value;
}

export default function AdminFeedbacksPage() {
  const [feedbacks, setFeedbacks] = useState<FeedbackItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadFeedbacks() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<FeedbackItem[]>("/api/admin/feedbacks");
      setFeedbacks(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载反馈列表失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadFeedbacks();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">用户反馈</p>
          <h2 className="mt-2 font-serif text-4xl">查看专家提交的使用反馈与建议</h2>
        </div>
        <Button variant="secondary" onClick={() => void loadFeedbacks()}>
          刷新列表
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>反馈列表</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {error ? (
            <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              {error}
            </div>
          ) : null}

          {!loading && feedbacks.length === 0 ? (
            <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
              当前没有用户反馈。
            </div>
          ) : null}

          {feedbacks.map((item) => (
            <div
              key={item.id}
              className="rounded-3xl border border-border bg-stone-50 p-4"
            >
              <div className="flex flex-wrap items-center gap-3">
                <p className="font-medium">{item.title}</p>
                <Badge variant="muted">{categoryLabel(item.category)}</Badge>
              </div>
              <p className="mt-3 text-sm leading-7 text-muted-foreground">
                {item.content}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span>{item.user_name || item.username || "未知用户"}</span>
                <span>{formatTime(item.created_at)}</span>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
