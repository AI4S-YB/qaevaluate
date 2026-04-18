"use client";

import { useEffect, useMemo, useState } from "react";

import { apiFetch, type TaxonomyItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type TaxonomyKind = "technical-types" | "business-tags";

function sectionTitle(kind: TaxonomyKind) {
  return kind === "technical-types" ? "技术类型" : "业务标签";
}

function emptyForm() {
  return { code: "", name: "", description: "", sort_order: "100" };
}

function TaxonomyPanel({
  kind,
  items,
  loading,
  updatingId,
  onRefresh,
  onCreate,
  onToggle
}: {
  kind: TaxonomyKind;
  items: TaxonomyItem[];
  loading: boolean;
  updatingId: number | null;
  onRefresh: () => Promise<void>;
  onCreate: (kind: TaxonomyKind, form: ReturnType<typeof emptyForm>) => Promise<void>;
  onToggle: (kind: TaxonomyKind, item: TaxonomyItem) => Promise<void>;
}) {
  const [form, setForm] = useState(emptyForm());

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <CardTitle>{sectionTitle(kind)}</CardTitle>
        <Button variant="secondary" size="sm" onClick={() => void onRefresh()}>
          刷新
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 rounded-[28px] border border-dashed border-border bg-stone-50 p-4">
          <input
            className="field"
            placeholder="编码，例如 cot_qa / pest_control"
            value={form.code}
            onChange={(event) => setForm((current) => ({ ...current, code: event.target.value }))}
          />
          <input
            className="field"
            placeholder="显示名称"
            value={form.name}
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
          />
          <textarea
            className="field-textarea"
            placeholder="描述"
            value={form.description}
            onChange={(event) =>
              setForm((current) => ({ ...current, description: event.target.value }))
            }
          />
          <input
            className="field"
            placeholder="排序，默认 100"
            value={form.sort_order}
            onChange={(event) =>
              setForm((current) => ({ ...current, sort_order: event.target.value }))
            }
          />
          <Button
            onClick={async () => {
              await onCreate(kind, form);
              setForm(emptyForm());
            }}
          >
            新建{sectionTitle(kind)}
          </Button>
        </div>

        {!loading && items.length === 0 ? (
          <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-8 text-center text-sm text-muted-foreground">
            当前没有{sectionTitle(kind)}。
          </div>
        ) : null}

        {items.map((item) => (
          <div key={item.id} className="rounded-[28px] border border-border bg-stone-50 p-4">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">{item.name}</p>
                  <Badge variant={item.is_active ? "success" : "muted"}>
                    {item.is_active ? "启用中" : "已停用"}
                  </Badge>
                  <Badge variant="warning">{item.code}</Badge>
                </div>
                <p className="text-sm text-muted-foreground">
                  {item.description || "暂无描述"}
                </p>
                <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                  <p>排序: {item.sort_order}</p>
                  <p>创建时间: {item.created_at.replace("T", " ").slice(0, 16)}</p>
                </div>
              </div>
              <Button
                size="sm"
                variant="secondary"
                disabled={updatingId === item.id}
                onClick={() => void onToggle(kind, item)}
              >
                {updatingId === item.id
                  ? "处理中…"
                  : item.is_active
                    ? "停用"
                    : "启用"}
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function AdminTaxonomyPage() {
  const [technicalTypes, setTechnicalTypes] = useState<TaxonomyItem[]>([]);
  const [businessTags, setBusinessTags] = useState<TaxonomyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadTaxonomy() {
    setLoading(true);
    setError(null);
    try {
      const [technicalTypeData, businessTagData] = await Promise.all([
        apiFetch<TaxonomyItem[]>("/api/admin/technical-types"),
        apiFetch<TaxonomyItem[]>("/api/admin/business-tags")
      ]);
      setTechnicalTypes(technicalTypeData);
      setBusinessTags(businessTagData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载分类配置失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadTaxonomy();
  }, []);

  async function handleCreate(kind: TaxonomyKind, form: ReturnType<typeof emptyForm>) {
    if (!form.code.trim() || !form.name.trim()) {
      setError("编码和名称不能为空");
      return;
    }
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/${kind}`, {
        method: "POST",
        body: JSON.stringify({
          code: form.code.trim(),
          name: form.name.trim(),
          description: form.description.trim() || null,
          sort_order: Number(form.sort_order) || 100
        })
      });
      setNotice(`${sectionTitle(kind)}已创建。`);
      await loadTaxonomy();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建分类失败");
    }
  }

  async function handleToggle(kind: TaxonomyKind, item: TaxonomyItem) {
    setUpdatingId(item.id);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/${kind}/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          is_active: !item.is_active
        })
      });
      setNotice(`${sectionTitle(kind)} ${item.name} 已${item.is_active ? "停用" : "启用"}。`);
      await loadTaxonomy();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新分类失败");
    } finally {
      setUpdatingId(null);
    }
  }

  const summary = useMemo(
    () => ({
      technicalTotal: technicalTypes.length,
      technicalActive: technicalTypes.filter((item) => item.is_active).length,
      tagTotal: businessTags.length,
      tagActive: businessTags.filter((item) => item.is_active).length
    }),
    [businessTags, technicalTypes]
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">分类配置</p>
          <h2 className="mt-2 font-serif text-4xl">把技术类型和业务标签变成可维护的后台配置</h2>
        </div>
        <Button variant="secondary" onClick={() => void loadTaxonomy()}>
          刷新全部
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
          ["技术类型总数", summary.technicalTotal],
          ["启用技术类型", summary.technicalActive],
          ["业务标签总数", summary.tagTotal],
          ["启用业务标签", summary.tagActive]
        ].map(([label, value]) => (
          <Card key={label}>
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">{label}</p>
              <p className="mt-3 text-3xl font-semibold">{value}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <TaxonomyPanel
          kind="technical-types"
          items={technicalTypes}
          loading={loading}
          updatingId={updatingId}
          onRefresh={loadTaxonomy}
          onCreate={handleCreate}
          onToggle={handleToggle}
        />
        <TaxonomyPanel
          kind="business-tags"
          items={businessTags}
          loading={loading}
          updatingId={updatingId}
          onRefresh={loadTaxonomy}
          onCreate={handleCreate}
          onToggle={handleToggle}
        />
      </section>
    </div>
  );
}
