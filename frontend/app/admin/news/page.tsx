"use client";

import { useEffect, useState } from "react";

import { apiFetch, type NewsItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatTime(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

export default function AdminNewsPage() {
  const [newsList, setNewsList] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [createTitle, setCreateTitle] = useState("");
  const [createContent, setCreateContent] = useState("");
  const [createPublished, setCreatePublished] = useState(false);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");

  async function loadNews() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<NewsItem[]>("/api/admin/news");
      setNewsList(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载新闻列表失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate() {
    if (!createTitle.trim() || !createContent.trim()) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch("/api/admin/news", {
        method: "POST",
        body: JSON.stringify({
          title: createTitle.trim(),
          content: createContent.trim(),
          is_published: createPublished
        })
      });
      setCreateTitle("");
      setCreateContent("");
      setCreatePublished(false);
      setNotice("新闻已创建。");
      await loadNews();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建新闻失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUpdate(newsId: number) {
    if (!editTitle.trim() || !editContent.trim()) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/news/${newsId}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: editTitle.trim(),
          content: editContent.trim()
        })
      });
      setEditingId(null);
      setNotice("新闻已更新。");
      await loadNews();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新新闻失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTogglePublish(newsId: number, currentPublished: boolean) {
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/news/${newsId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_published: !currentPublished })
      });
      await loadNews();
    } catch (err) {
      setError(err instanceof Error ? err.message : "切换发布状态失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(newsId: number) {
    if (!confirm("确定要删除这条新闻吗？")) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/news/${newsId}`, { method: "DELETE" });
      setNotice("新闻已删除。");
      await loadNews();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除新闻失败");
    } finally {
      setSubmitting(false);
    }
  }

  function startEdit(item: NewsItem) {
    setEditingId(item.id);
    setEditTitle(item.title);
    setEditContent(item.content);
  }

  useEffect(() => {
    void loadNews();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">新闻管理</p>
          <h2 className="mt-2 font-serif text-4xl">发布系统公告与新闻内容</h2>
        </div>
        <Button variant="secondary" onClick={() => void loadNews()}>
          刷新列表
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>新建新闻</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <input
            className="field"
            value={createTitle}
            onChange={(event) => setCreateTitle(event.target.value)}
            placeholder="新闻标题"
            disabled={submitting}
          />
          <textarea
            className="field-textarea"
            value={createContent}
            onChange={(event) => setCreateContent(event.target.value)}
            placeholder="新闻内容"
            disabled={submitting}
          />
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={createPublished}
                onChange={(event) => setCreatePublished(event.target.checked)}
                disabled={submitting}
              />
              立即发布
            </label>
            <Button disabled={submitting} onClick={() => void handleCreate()}>
              {submitting ? "创建中…" : "创建新闻"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>新闻列表</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
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

          {!loading && newsList.length === 0 ? (
            <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
              当前没有新闻。
            </div>
          ) : null}

          {newsList.map((item) => (
            <div
              key={item.id}
              className="space-y-3 rounded-3xl border border-border bg-stone-50 p-4"
            >
              {editingId === item.id ? (
                <div className="space-y-3">
                  <input
                    className="field"
                    value={editTitle}
                    onChange={(event) => setEditTitle(event.target.value)}
                    placeholder="标题"
                    disabled={submitting}
                  />
                  <textarea
                    className="field-textarea"
                    value={editContent}
                    onChange={(event) => setEditContent(event.target.value)}
                    placeholder="内容"
                    disabled={submitting}
                  />
                  <div className="flex gap-3">
                    <Button
                      size="sm"
                      disabled={submitting}
                      onClick={() => void handleUpdate(item.id)}
                    >
                      保存
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={submitting}
                      onClick={() => setEditingId(null)}
                    >
                      取消
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex flex-wrap items-center gap-3">
                    <p className="font-medium">{item.title}</p>
                    <Badge variant={item.is_published ? "success" : "muted"}>
                      {item.is_published ? "已发布" : "草稿"}
                    </Badge>
                  </div>
                  <p className="text-sm leading-7 text-muted-foreground">
                    {item.content}
                  </p>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                    <span>{item.created_by_name || "未知"}</span>
                    <span>{formatTime(item.created_at)}</span>
                    {item.updated_at !== item.created_at ? (
                      <span>更新于 {formatTime(item.updated_at)}</span>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={submitting}
                      onClick={() => startEdit(item)}
                    >
                      编辑
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={submitting}
                      onClick={() => void handleTogglePublish(item.id, item.is_published)}
                    >
                      {item.is_published ? "取消发布" : "发布"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={submitting}
                      onClick={() => void handleDelete(item.id)}
                    >
                      删除
                    </Button>
                  </div>
                </>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
