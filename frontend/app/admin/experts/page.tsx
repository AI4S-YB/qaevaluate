"use client";

import { useEffect, useState } from "react";

import { apiFetch, type ExpertUser } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AdminExpertsPage() {
  const [experts, setExperts] = useState<ExpertUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submittingId, setSubmittingId] = useState<number | null>(null);

  async function loadExperts() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<ExpertUser[]>("/api/admin/experts");
      setExperts(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载专家失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleAction(expertId: number, action: "approve" | "reject" | "disable") {
    setSubmittingId(expertId);
    try {
      await apiFetch(`/api/admin/experts/${expertId}/${action}`, {
        method: "POST",
        body: JSON.stringify({ note: "" })
      });
      await loadExperts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新状态失败");
    } finally {
      setSubmittingId(null);
    }
  }

  useEffect(() => {
    void loadExperts();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">专家审核</p>
          <h2 className="mt-2 font-serif text-4xl">审核专家注册并维护可用专家池</h2>
        </div>
        <Button variant="secondary" onClick={() => void loadExperts()}>
          刷新列表
        </Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>专家列表</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {error ? (
            <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              {error}
            </div>
          ) : null}

          {!loading && experts.length === 0 ? (
            <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
              当前没有专家数据。
            </div>
          ) : null}

          {experts.map((expert) => (
            <div
              key={expert.id}
              className="flex flex-col gap-4 rounded-3xl border border-border bg-stone-50 p-4 lg:flex-row lg:items-center lg:justify-between"
            >
              <div className="space-y-1">
                <p className="font-medium">{expert.full_name}</p>
                <p className="text-sm text-muted-foreground">
                  {expert.organization || "未填写单位"}
                  {expert.title ? ` / ${expert.title}` : ""}
                </p>
                <p className="text-sm text-muted-foreground">
                  擅长应用：{expert.applications || "未绑定应用"}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Badge variant={expert.status === "approved" ? "success" : "warning"}>
                  {expert.status}
                </Badge>
                <Button
                  size="sm"
                  disabled={submittingId === expert.id}
                  onClick={() => void handleAction(expert.id, "approve")}
                >
                  通过
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={submittingId === expert.id}
                  onClick={() => void handleAction(expert.id, "reject")}
                >
                  拒绝
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={submittingId === expert.id}
                  onClick={() => void handleAction(expert.id, "disable")}
                >
                  停用
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
