"use client";

import { useEffect, useState } from "react";

import { apiFetch, type ApplicationItem } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function RegisterPage() {
  const [applications, setApplications] = useState<ApplicationItem[]>([]);
  const [selectedApplications, setSelectedApplications] = useState<number[]>([]);
  const [form, setForm] = useState({
    username: "",
    password: "",
    full_name: "",
    organization: "",
    title: "",
    bio: ""
  });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function loadApplications() {
      try {
        const data = await apiFetch<ApplicationItem[]>("/api/applications");
        setApplications(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载项目失败");
      }
    }
    void loadApplications();
  }, []);

  async function handleRegister() {
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          application_ids: selectedApplications
        })
      });
      setNotice("注册申请已提交，等待管理员审核。");
      setForm({
        username: "",
        password: "",
        full_name: "",
        organization: "",
        title: "",
        bio: ""
      });
      setSelectedApplications([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交注册失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-background bg-mesh px-4 py-6 lg:px-6">
      <div className="mx-auto max-w-3xl">
        <Card>
          <CardHeader>
            <p className="text-sm text-muted-foreground">专家注册</p>
            <CardTitle className="text-3xl">提交申请后由管理员审核</CardTitle>
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
            <input
              className="field"
              placeholder="用户名"
              value={form.username}
              onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))}
            />
            <input
              className="field"
              placeholder="密码"
              type="password"
              value={form.password}
              onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
            />
            <input
              className="field"
              placeholder="姓名"
              value={form.full_name}
              onChange={(event) => setForm((current) => ({ ...current, full_name: event.target.value }))}
            />
            <input
              className="field"
              placeholder="单位"
              value={form.organization}
              onChange={(event) =>
                setForm((current) => ({ ...current, organization: event.target.value }))
              }
            />
            <input
              className="field"
              placeholder="职称或角色"
              value={form.title}
              onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
            />
            <div className="rounded-3xl border border-border bg-stone-50 p-4 md:col-span-2">
              <p className="mb-3 text-sm font-medium">参与项目</p>
              <div className="flex flex-wrap gap-2">
                {applications.map((application) => {
                  const selected = selectedApplications.includes(application.id);
                  return (
                    <Button
                      key={application.id}
                      size="sm"
                      variant={selected ? "default" : "secondary"}
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
              placeholder="个人说明"
              value={form.bio}
              onChange={(event) => setForm((current) => ({ ...current, bio: event.target.value }))}
            />
            <div className="md:col-span-2 flex justify-end">
              <Button disabled={submitting} onClick={() => void handleRegister()}>
                {submitting ? "提交中…" : "提交注册申请"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
