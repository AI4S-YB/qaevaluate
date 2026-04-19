"use client";

import { useEffect, useState } from "react";

import { apiFetch, type ExpertUser, type TaxonomyItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type ExpertEditorState = {
  businessTagIds: number[];
  allowCrossBusinessReview: boolean;
};

export default function AdminExpertsPage() {
  const [experts, setExperts] = useState<ExpertUser[]>([]);
  const [businessTags, setBusinessTags] = useState<TaxonomyItem[]>([]);
  const [drafts, setDrafts] = useState<Record<number, ExpertEditorState>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submittingId, setSubmittingId] = useState<number | null>(null);

  async function loadExperts() {
    setLoading(true);
    setError(null);
    try {
      const [expertList, businessTagList] = await Promise.all([
        apiFetch<ExpertUser[]>("/api/admin/experts"),
        apiFetch<TaxonomyItem[]>("/api/admin/business-tags")
      ]);
      setExperts(expertList);
      setBusinessTags(businessTagList.filter((item) => item.is_active));
      setDrafts(
        Object.fromEntries(
          expertList.map((expert) => [
            expert.id,
            {
              businessTagIds: expert.business_tags.map((item) => item.id),
              allowCrossBusinessReview: expert.allow_cross_business_review
            }
          ])
        )
      );
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

  async function handleSaveSettings(expertId: number) {
    const draft = drafts[expertId];
    if (!draft) return;

    setSubmittingId(expertId);
    setError(null);
    try {
      await apiFetch(`/api/admin/experts/${expertId}`, {
        method: "PATCH",
        body: JSON.stringify({
          business_tag_ids: draft.businessTagIds,
          allow_cross_business_review: draft.allowCrossBusinessReview
        })
      });
      await loadExperts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存专家配置失败");
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
          <h2 className="mt-2 font-serif text-4xl">审核专家注册并维护领域场景权限</h2>
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

          {experts.map((expert) => {
            const draft = drafts[expert.id] ?? {
              businessTagIds: [],
              allowCrossBusinessReview: false
            };

            return (
              <div
                key={expert.id}
                className="space-y-4 rounded-3xl border border-border bg-stone-50 p-4"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-3">
                      <p className="font-medium">{expert.full_name}</p>
                      <Badge variant={expert.status === "approved" ? "success" : "warning"}>
                        {expert.status}
                      </Badge>
                      <Badge variant={draft.allowCrossBusinessReview ? "warning" : "muted"}>
                        {draft.allowCrossBusinessReview ? "允许跨领域评审" : "仅限本领域评审"}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {expert.organization || "未填写单位"}
                      {expert.title ? ` / ${expert.title}` : ""}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {expert.applications.length ? (
                        expert.applications.map((application) => (
                          <Badge key={application.id} variant="muted">
                            项目: {application.name}
                          </Badge>
                        ))
                      ) : (
                        <Badge variant="muted">项目: 未绑定</Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
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

                <div className="grid gap-4 xl:grid-cols-[1fr_220px_120px] xl:items-start">
                  <div className="rounded-2xl border border-border bg-white/80 p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <p className="text-sm font-medium">领域场景配置</p>
                      <p className="text-xs text-muted-foreground">
                        专家端只读展示，不允许自行修改
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {businessTags.map((businessTag) => {
                        const selected = draft.businessTagIds.includes(businessTag.id);
                        return (
                          <Button
                            key={businessTag.id}
                            size="sm"
                            variant={selected ? "default" : "secondary"}
                            disabled={submittingId === expert.id}
                            onClick={() =>
                              setDrafts((current) => ({
                                ...current,
                                [expert.id]: {
                                  ...draft,
                                  businessTagIds: selected
                                    ? draft.businessTagIds.filter((id) => id !== businessTag.id)
                                    : [...draft.businessTagIds, businessTag.id]
                                }
                              }))
                            }
                          >
                            {businessTag.name}
                          </Button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border bg-white/80 p-4">
                    <p className="text-sm font-medium">可见范围</p>
                    <p className="mt-2 text-xs leading-6 text-muted-foreground">
                      关闭后，只能看到自己领域场景内的 QA；没有领域场景标签的通用 QA 仍可分发。
                    </p>
                    <Button
                      className="mt-4 w-full"
                      variant={draft.allowCrossBusinessReview ? "default" : "secondary"}
                      disabled={submittingId === expert.id}
                      onClick={() =>
                        setDrafts((current) => ({
                          ...current,
                          [expert.id]: {
                            ...draft,
                            allowCrossBusinessReview: !draft.allowCrossBusinessReview
                          }
                        }))
                      }
                    >
                      {draft.allowCrossBusinessReview ? "已开启跨领域评审" : "已关闭跨领域评审"}
                    </Button>
                  </div>

                  <Button
                    disabled={submittingId === expert.id}
                    onClick={() => void handleSaveSettings(expert.id)}
                  >
                    保存配置
                  </Button>
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
