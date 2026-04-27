"use client";

import { useState } from "react";

import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const CATEGORIES = [
  { value: "general", label: "通用" },
  { value: "bug", label: "问题反馈" },
  { value: "feature", label: "功能建议" },
  { value: "data", label: "数据问题" },
  { value: "other", label: "其他" }
];

export default function ExpertFeedbackPage() {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("general");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function handleSubmit() {
    if (!title.trim() || !content.trim()) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch("/api/feedback", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(),
          content: content.trim(),
          category
        })
      });
      setNotice("反馈已提交，感谢你的意见。");
      setTitle("");
      setContent("");
      setCategory("general");
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交反馈失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">意见反馈</p>
        <h2 className="mt-2 font-serif text-4xl">提交使用反馈与改进建议</h2>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>反馈表单</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {error ? (
            <div className="rounded-[24px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              {error}
            </div>
          ) : null}
          {notice ? (
            <div className="rounded-[24px] border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
              {notice}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-3">
            {CATEGORIES.map((cat) => (
              <Button
                key={cat.value}
                size="sm"
                variant={category === cat.value ? "default" : "secondary"}
                disabled={submitting}
                onClick={() => setCategory(cat.value)}
              >
                {cat.label}
              </Button>
            ))}
          </div>

          <input
            className="field"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="反馈标题"
            disabled={submitting}
          />

          <textarea
            className="field-textarea"
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="请详细描述你的意见或问题..."
            disabled={submitting}
          />

          <div className="flex justify-end">
            <Button disabled={submitting} onClick={() => void handleSubmit()}>
              {submitting ? "提交中…" : "提交反馈"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
