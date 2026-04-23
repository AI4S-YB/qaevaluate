"use client";

import { useEffect, useMemo, useState } from "react";

import {
  apiFetch,
  type AdminApplicationBusinessTagItem,
  type AdminApplicationItem
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AdminApplicationsPage() {
  const [applications, setApplications] = useState<AdminApplicationItem[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [expandedApplicationId, setExpandedApplicationId] = useState<number | null>(null);
  const [loadingScenesId, setLoadingScenesId] = useState<number | null>(null);
  const [sceneMap, setSceneMap] = useState<Record<number, AdminApplicationBusinessTagItem[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadApplications() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<AdminApplicationItem[]>("/api/admin/applications");
      setApplications(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载项目失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate() {
    if (!name.trim()) {
      setError("项目名称不能为空");
      return;
    }
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch("/api/admin/applications", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || null,
          is_active: true
        })
      });
      setName("");
      setDescription("");
      setNotice("项目已创建。");
      await loadApplications();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建项目失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleToggle(application: AdminApplicationItem) {
    setUpdatingId(application.id);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/applications/${application.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: application.name,
          description: application.description,
          is_active: !Boolean(application.is_active)
        })
      });
      setNotice(
        !application.is_active
          ? `已启用项目 ${application.name}。`
          : `已停用项目 ${application.name}。`
      );
      await loadApplications();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新项目状态失败");
    } finally {
      setUpdatingId(null);
    }
  }

  async function toggleScenes(applicationId: number) {
    if (expandedApplicationId === applicationId) {
      setExpandedApplicationId(null);
      return;
    }
    setExpandedApplicationId(applicationId);
    if (sceneMap[applicationId]) {
      return;
    }
    setLoadingScenesId(applicationId);
    try {
      const data = await apiFetch<AdminApplicationBusinessTagItem[]>(
        `/api/admin/applications/${applicationId}/business-tags`
      );
      setSceneMap((current) => ({ ...current, [applicationId]: data }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载领域场景统计失败");
    } finally {
      setLoadingScenesId(null);
    }
  }

  useEffect(() => {
    void loadApplications();
  }, []);

  const summary = useMemo(() => {
    return applications.reduce(
      (acc, item) => {
        acc.total += 1;
        if (item.is_active) acc.active += 1;
        acc.totalQas += item.total_qas;
        acc.closedQas += item.closed_qas;
        acc.experts += item.expert_count;
        return acc;
      },
      { total: 0, active: 0, totalQas: 0, closedQas: 0, experts: 0 }
    );
  }, [applications]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">项目管理</p>
          <h2 className="mt-2 font-serif text-4xl">查看每个项目的题量、闭环进度和专家覆盖情况</h2>
        </div>
        <Button variant="secondary" onClick={() => void loadApplications()}>
          刷新列表
        </Button>
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

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          ["项目总数", summary.total],
          ["启用中", summary.active],
          ["QA 总量", summary.totalQas],
          ["已闭环 QA", summary.closedQas]
        ].map(([label, value]) => (
          <Card key={label}>
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">{label}</p>
              <p className="mt-3 text-3xl font-semibold">{value}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-[0.82fr_1.18fr]">
        <Card>
          <CardHeader>
            <CardTitle>新建项目</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <input
              className="field"
              placeholder="项目名称"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <textarea
              className="field-textarea"
              placeholder="项目描述"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
            <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-4 text-sm leading-7 text-muted-foreground">
              项目是当前平台的组织边界。专家配置、QA 统计和导出筛选都会围绕项目聚合。
            </div>
            <Button disabled={submitting} onClick={() => void handleCreate()}>
              {submitting ? "创建中…" : "新建项目"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>项目运营概览</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {!loading && applications.length === 0 ? (
              <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
                当前还没有项目。
              </div>
            ) : null}

            {applications.map((application) => (
              <div
                key={application.id}
                className="rounded-[28px] border border-border bg-stone-50 p-4"
              >
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{application.name}</p>
                      <Badge variant={application.is_active ? "success" : "muted"}>
                        {application.is_active ? "启用中" : "已停用"}
                      </Badge>
                      <Badge variant="warning">{application.expert_count} 位专家覆盖</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {application.description || "暂无描述"}
                    </p>
                    <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2 xl:grid-cols-3">
                      <p>QA 总量: {application.total_qas}</p>
                      <p>已评测量: {application.reviewed_qas}</p>
                      <p>待聚合量: {application.pending_aggregate_qas}</p>
                      <p>已闭环量: {application.closed_qas}</p>
                      <p>创建时间: {application.created_at.replace("T", " ").slice(0, 16)}</p>
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <Button
                      size="sm"
                      variant={expandedApplicationId === application.id ? "default" : "secondary"}
                      disabled={loadingScenesId === application.id}
                      onClick={() => void toggleScenes(application.id)}
                    >
                      {loadingScenesId === application.id
                        ? "加载中…"
                        : expandedApplicationId === application.id
                          ? "收起场景"
                          : "查看场景"}
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={updatingId === application.id}
                      onClick={() => void handleToggle(application)}
                    >
                      {updatingId === application.id
                        ? "处理中…"
                        : application.is_active
                          ? "停用"
                          : "启用"}
                    </Button>
                  </div>
                </div>

                {expandedApplicationId === application.id ? (
                  <div className="mt-4 border-t border-border pt-4">
                    <div className="mb-3 flex items-center justify-between">
                      <p className="text-sm font-medium">领域场景覆盖</p>
                      <p className="text-xs text-muted-foreground">
                        展示当前项目下已经有实际 QA 的场景
                      </p>
                    </div>
                    {sceneMap[application.id] && sceneMap[application.id].length > 0 ? (
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        {sceneMap[application.id].map((scene) => (
                          <div
                            key={scene.id}
                            className="rounded-[20px] border border-border bg-white p-4"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <p className="font-medium">{scene.name}</p>
                              <Badge variant="warning">{scene.expert_count} 位专家</Badge>
                            </div>
                            <div className="mt-3 space-y-1 text-sm text-muted-foreground">
                              <p>QA 总量: {scene.qa_count}</p>
                              <p>已评测量: {scene.reviewed_qas}</p>
                              <p>已闭环量: {scene.closed_qas}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-[20px] border border-dashed border-border bg-white p-6 text-sm text-muted-foreground">
                        当前项目下还没有可展示的领域场景统计。
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            ))}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
