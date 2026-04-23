"use client";

import { useMemo } from "react";
import { useEffect, useState } from "react";

import { apiFetch, type ExpertTaskListItem, type MeProfile } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function ExpertProfilePage() {
  const [profile, setProfile] = useState<MeProfile | null>(null);
  const [tasks, setTasks] = useState<ExpertTaskListItem[]>([]);
  const [form, setForm] = useState({
    organization: "",
    title: "",
    bio: ""
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [me, taskList] = await Promise.all([
        apiFetch<MeProfile>("/api/me"),
        apiFetch<ExpertTaskListItem[]>("/api/expert/tasks")
      ]);
      setProfile(me);
      setTasks(taskList);
      setForm({
        organization: me.organization ?? "",
        title: me.title ?? "",
        bio: me.bio ?? ""
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载个人资料失败");
    } finally {
      setLoading(false);
    }
  }

  const projectSummaries = useMemo(() => {
    if (!profile) return [];

    const taskStats = new Map<
      string,
      { total: number; pending: number; inProgress: number; submitted: number }
    >();

    for (const task of tasks) {
      const current = taskStats.get(task.application_name) ?? {
        total: 0,
        pending: 0,
        inProgress: 0,
        submitted: 0
      };
      current.total += 1;
      if (task.status === "pending") current.pending += 1;
      if (task.status === "in_progress") current.inProgress += 1;
      if (task.status === "submitted") current.submitted += 1;
      taskStats.set(task.application_name, current);
    }

    return profile.applications.map((application) => ({
      id: application.id,
      name: application.name,
      stats: taskStats.get(application.name) ?? {
        total: 0,
        pending: 0,
        inProgress: 0,
        submitted: 0
      }
    }));
  }, [profile, tasks]);

  useEffect(() => {
    void loadData();
  }, []);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch("/api/me", {
        method: "PATCH",
        body: JSON.stringify({
          organization: form.organization || null,
          title: form.title || null,
          bio: form.bio || null
        })
      });
      setNotice("资料已更新。");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存资料失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">我的资料</p>
        <h2 className="mt-2 font-serif text-4xl">查看项目范围、领域场景与个人简介</h2>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>专家信息</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          {error ? (
            <div className="rounded-[24px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 md:col-span-2">
              {error}
            </div>
          ) : null}
          {notice ? (
            <div className="rounded-[24px] border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800 md:col-span-2">
              {notice}
            </div>
          ) : null}
          <input className="field" value={profile?.username ?? ""} readOnly />
          <input className="field" value={profile?.full_name ?? ""} readOnly />
          <input
            className="field"
            value={form.organization}
            onChange={(event) =>
              setForm((current) => ({ ...current, organization: event.target.value }))
            }
            placeholder="单位"
            disabled={loading}
          />
          <input
            className="field"
            value={form.title}
            onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
            placeholder="职称或角色"
            disabled={loading}
          />
          <div className="rounded-3xl border border-border bg-stone-50 p-4 md:col-span-2">
            <div className="mb-3 flex items-center justify-between gap-3">
              <p className="text-sm font-medium">当前项目与任务分布</p>
              <p className="text-xs text-muted-foreground">
                共 {projectSummaries.length} 个项目 / {tasks.length} 条任务
              </p>
            </div>
            <div className="space-y-3">
              {projectSummaries.length ? (
                projectSummaries.map((project) => (
                  <div
                    key={project.id}
                    className="flex flex-col gap-2 rounded-2xl border border-border/80 bg-white/80 px-4 py-3 lg:flex-row lg:items-center lg:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{project.name}</p>
                      <p className="text-xs text-muted-foreground">
                        已分配 {project.stats.total} 条任务
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="muted">待处理 {project.stats.pending}</Badge>
                      <Badge variant="default">处理中 {project.stats.inProgress}</Badge>
                      <Badge variant="success">已提交 {project.stats.submitted}</Badge>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">当前还没有分配项目。</p>
              )}
            </div>
          </div>
          <div className="rounded-3xl border border-border bg-stone-50 p-4 md:col-span-2">
            <div className="mb-3 flex items-center justify-between gap-3">
              <p className="text-sm font-medium">领域场景</p>
              <Badge variant={profile?.allow_cross_business_review ? "warning" : "muted"}>
                {profile?.allow_cross_business_review ? "允许跨领域评审" : "仅限本领域评审"}
              </Badge>
            </div>
            <div className="flex flex-wrap gap-2">
              {profile?.business_tags.length ? (
                profile.business_tags.map((businessTag) => (
                  <Badge key={businessTag.id} variant="muted" className="px-3 py-1">
                    {businessTag.name}
                  </Badge>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">当前尚未配置领域场景，由管理员维护。</p>
              )}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              领域场景与跨领域评审权限由管理员在专家管理中统一配置，专家端仅展示当前设置。
            </p>
          </div>
          <textarea
            className="field-textarea md:col-span-2"
            value={form.bio}
            onChange={(event) => setForm((current) => ({ ...current, bio: event.target.value }))}
            placeholder="个人说明"
            disabled={loading}
          />
          <div className="md:col-span-2 flex justify-end">
            <Button disabled={loading || saving} onClick={() => void handleSave()}>
              {saving ? "保存中…" : "保存资料"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
