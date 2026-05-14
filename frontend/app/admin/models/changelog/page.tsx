"use client";

import { useEffect, useState } from "react";

import { apiFetch, type ModelChangelogItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatTime(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

function changeTypeVariant(value: string) {
  return value === "added" ? "success" : "warning";
}

function changeTypeLabel(value: string) {
  return value === "added" ? "新增" : "更新";
}

export default function AdminModelChangelogPage() {
  const [items, setItems] = useState<ModelChangelogItem[]>([]);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadChangelog() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<ModelChangelogItem[]>(
        `/api/models/changelog?days=${days}`
      );
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载模型变更记录失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadChangelog();
  }, [days]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">模型变更记录</p>
          <h2 className="mt-2 font-serif text-4xl">追踪试用模型的上下线与更新历史</h2>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 rounded-3xl border border-border bg-stone-50 px-3 py-2">
            {[1, 7, 14, 30].map((d) => (
              <Button
                key={d}
                size="sm"
                variant={days === d ? "default" : "secondary"}
                onClick={() => setDays(d)}
              >
                {d === 1 ? "今天" : `近 ${d} 天`}
              </Button>
            ))}
          </div>
          <Button variant="secondary" onClick={() => void loadChangelog()}>
            刷新
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>变更列表</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {error ? (
            <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              {error}
            </div>
          ) : null}

          {!loading && items.length === 0 ? (
            <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
              所选时间范围内没有模型变更记录。
            </div>
          ) : null}

          {items.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-4 rounded-3xl border border-border bg-stone-50 p-4"
            >
              <Badge variant={changeTypeVariant(item.change_type)}>
                {changeTypeLabel(item.change_type)}
              </Badge>
              <div className="flex-1">
                <p className="text-sm">{item.description}</p>
              </div>
              <p className="text-xs text-muted-foreground">
                {formatTime(item.created_at)}
              </p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
