"use client";

import { useEffect, useState } from "react";

import {
  apiFetch,
  type ApplicationItem,
  type MeProfile
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function ExpertProfilePage() {
  const [profile, setProfile] = useState<MeProfile | null>(null);
  const [applications, setApplications] = useState<ApplicationItem[]>([]);
  const [selectedApplications, setSelectedApplications] = useState<number[]>([]);
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
      const [me, applicationList] = await Promise.all([
        apiFetch<MeProfile>("/api/me"),
        apiFetch<ApplicationItem[]>("/api/applications")
      ]);
      setProfile(me);
      setApplications(applicationList);
      setSelectedApplications(me.applications.map((item) => item.id));
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
          bio: form.bio || null,
          application_ids: selectedApplications
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
        <h2 className="mt-2 font-serif text-4xl">维护擅长应用与个人简介</h2>
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
            <p className="mb-3 text-sm font-medium">擅长应用</p>
            <div className="flex flex-wrap gap-2">
              {applications.map((application) => {
                const selected = selectedApplications.includes(application.id);
                return (
                  <Button
                    key={application.id}
                    size="sm"
                    variant={selected ? "default" : "secondary"}
                    disabled={loading}
                    onClick={() =>
                      setSelectedApplications((current) =>
                        selected
                          ? current.filter((id) => id !== application.id)
                          : [...current, application.id]
                      )
                    }
                  >
                    {application.name}
                  </Button>
                );
              })}
            </div>
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
