"use client";

import type { Route } from "next";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  apiFetch,
  type AdminQaListPage,
  type QaListItem,
  type TaxonomyItem
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function parseBusinessTags(value: string | null) {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as string[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

type QaMetadata = {
  scene_code?: string;
  scene_name?: string;
  module_key?: string;
  module_name?: string;
  action_key?: string;
  action_name?: string;
  seed_group?: string;
  cot_sequence_no?: number;
};

function parseQaMetadata(value: string | null) {
  if (!value) return {} as QaMetadata;
  try {
    const parsed = JSON.parse(value) as QaMetadata;
    return parsed && typeof parsed === "object" ? parsed : ({} as QaMetadata);
  } catch {
    return {} as QaMetadata;
  }
}

function decisionVariant(value: string | null) {
  if (value === "pass") return "success";
  if (value === "rewrite") return "warning";
  if (value === "fail") return "muted";
  return "default";
}

function decisionLabel(value: string | null) {
  if (value === "pass") return "通过";
  if (value === "rewrite") return "待改写";
  if (value === "fail") return "不通过";
  if (value === "pending") return "待聚合";
  return "未生成";
}

function resolveOperationalState(item: QaListItem) {
  if (!item.final_decision || item.final_decision === "pending") {
    return {
      label: "待聚合",
      variant: "default" as const,
      description: "已有任务或评测，但聚合结论还未稳定。"
    };
  }
  if (!item.final_standard_answer_id) {
    return {
      label: "待最终确认",
      variant: "warning" as const,
      description: "聚合结果已生成，但管理员还未确认最终标准答案。"
    };
  }
  if (
    item.current_answer_id !== null &&
    item.final_standard_answer_id !== null &&
    item.current_answer_id !== item.final_standard_answer_id
  ) {
    return {
      label: "聚合与最终不一致",
      variant: "muted" as const,
      description: "管理员最终确认的答案与当前聚合指向不同。"
    };
  }
  return {
    label: "已闭环",
    variant: "success" as const,
    description: "聚合和最终标准答案已经收敛。"
  };
}

export default function AdminQasPage() {
  const [qaPage, setQaPage] = useState<AdminQaListPage | null>(null);
  const [technicalTypes, setTechnicalTypes] = useState<TaxonomyItem[]>([]);
  const [businessTags, setBusinessTags] = useState<TaxonomyItem[]>([]);
  const [filter, setFilter] = useState("");
  const [stateFilter, setStateFilter] = useState("all");
  const [technicalTypeFilter, setTechnicalTypeFilter] = useState("all");
  const [businessTagFilter, setBusinessTagFilter] = useState("all");
  const [moduleFilter, setModuleFilter] = useState("all");
  const [actionFilter, setActionFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadQas(nextPage: number, nextPageSize: number) {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("page", String(nextPage));
      params.set("page_size", String(nextPageSize));
      if (filter.trim()) params.set("keyword", filter.trim());
      if (stateFilter !== "all") params.set("operational_state", stateFilter);
      if (technicalTypeFilter !== "all") params.set("technical_type_code", technicalTypeFilter);
      if (businessTagFilter !== "all") params.set("business_tag_code", businessTagFilter);
      if (moduleFilter !== "all") params.set("module_key", moduleFilter);
      if (actionFilter !== "all") params.set("action_key", actionFilter);
      const data = await apiFetch<AdminQaListPage>(`/api/admin/qas?${params.toString()}`);
      setQaPage(data);
      if (data.page !== nextPage) {
        setPage(data.page);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 QA 失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadTaxonomy() {
    try {
      const [technicalTypeData, businessTagData] = await Promise.all([
        apiFetch<TaxonomyItem[]>("/api/admin/technical-types"),
        apiFetch<TaxonomyItem[]>("/api/admin/business-tags")
      ]);
      setTechnicalTypes(technicalTypeData.filter((item) => item.is_active));
      setBusinessTags(businessTagData.filter((item) => item.is_active));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载分类配置失败");
    }
  }

  useEffect(() => {
    void loadTaxonomy();
  }, []);

  useEffect(() => {
    void loadQas(page, pageSize);
  }, [
    actionFilter,
    businessTagFilter,
    filter,
    moduleFilter,
    page,
    pageSize,
    stateFilter,
    technicalTypeFilter
  ]);

  useEffect(() => {
    setPage(1);
  }, [actionFilter, businessTagFilter, filter, moduleFilter, stateFilter, technicalTypeFilter]);

  const qas = qaPage?.items ?? [];

  const moduleOptions = useMemo(() => {
    const map = new Map<string, string>();
    qas.forEach((item) => {
      const metadata = parseQaMetadata(item.metadata_json);
      if (metadata.module_key && metadata.module_name) {
        map.set(metadata.module_key, metadata.module_name);
      }
    });
    return Array.from(map.entries()).map(([key, label]) => ({ key, label }));
  }, [qas]);

  const actionOptions = useMemo(() => {
    const map = new Map<string, string>();
    qas.forEach((item) => {
      const metadata = parseQaMetadata(item.metadata_json);
      if (metadata.action_key && metadata.action_name) {
        map.set(metadata.action_key, metadata.action_name);
      }
    });
    return Array.from(map.entries()).map(([key, label]) => ({ key, label }));
  }, [qas]);

  const filtered = qas;
  const summary = qaPage?.summary ?? {
    pending_aggregate: 0,
    pending_final: 0,
    mismatch: 0,
    closed: 0
  };

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <div>
          <p className="text-sm text-muted-foreground">QA 数据</p>
          <h2 className="mt-2 max-w-4xl font-serif text-4xl leading-tight">
            按评审/确认阶段分流查看问题、答案和最终确认状态
          </h2>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[280px_180px_180px_220px_180px_120px]">
          <input
            className="field"
            placeholder="筛选场景、模块、动作或阶段"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
          <select
            className="field min-w-[180px]"
            value={technicalTypeFilter}
            onChange={(event) => setTechnicalTypeFilter(event.target.value)}
          >
            <option value="all">全部 QA 类型</option>
            {technicalTypes.map((item) => (
              <option key={item.id} value={item.code}>
                {item.name}
              </option>
            ))}
          </select>
          <select
            className="field"
            value={businessTagFilter}
            onChange={(event) => setBusinessTagFilter(event.target.value)}
          >
            <option value="all">全部领域场景</option>
            {businessTags.map((item) => (
              <option key={item.id} value={item.code}>
                {item.name}
              </option>
            ))}
          </select>
          <select
            className="field"
            value={moduleFilter}
            onChange={(event) => setModuleFilter(event.target.value)}
          >
            <option value="all">全部研究模块</option>
            {moduleOptions.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </select>
          <select
            className="field"
            value={actionFilter}
            onChange={(event) => setActionFilter(event.target.value)}
          >
            <option value="all">全部推理动作</option>
            {actionOptions.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </select>
          <Button variant="secondary" onClick={() => void loadQas(page, pageSize)}>
            刷新列表
          </Button>
        </div>
      </div>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          ["待聚合", summary.pending_aggregate],
          ["待最终确认", summary.pending_final],
          ["聚合与最终不一致", summary.mismatch],
          ["已闭环", summary.closed]
        ].map(([label, value]) => (
          <Card key={label}>
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">{label}</p>
              <p className="mt-3 text-3xl font-semibold">{value}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      <Card>
        <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <CardTitle>QA 列表</CardTitle>
            <p className="text-sm text-muted-foreground">
              当前页 {filtered.length} 条 / 筛选后共 {qaPage?.total ?? 0} 条
            </p>
          </div>
          <div className="flex gap-3">
            <select
              className="field min-w-[220px]"
              value={stateFilter}
              onChange={(event) => setStateFilter(event.target.value)}
            >
              <option value="all">全部阶段</option>
              <option value="待聚合">待聚合</option>
              <option value="待最终确认">待最终确认</option>
              <option value="聚合与最终不一致">聚合与最终不一致</option>
              <option value="已闭环">已闭环</option>
            </select>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {error ? (
            <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              {error}
            </div>
          ) : null}
          {!loading && filtered.length === 0 ? (
            <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
              当前没有符合条件的 QA。
            </div>
          ) : null}

          {filtered.map((item) => {
            const operational = resolveOperationalState(item);
            const metadata = parseQaMetadata(item.metadata_json);
            return (
              <div
                key={item.id}
                className="rounded-[28px] border border-border bg-stone-50 p-4"
              >
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{item.external_id || `QA-${item.id}`}</p>
                      <Badge variant="muted">{item.application_name}</Badge>
                      {item.technical_type_name ? (
                        <Badge variant="warning">{item.technical_type_name}</Badge>
                      ) : null}
                      {metadata.module_name ? (
                        <Badge variant="default">{metadata.module_name}</Badge>
                      ) : null}
                      {metadata.action_name ? (
                        <Badge variant="muted">{metadata.action_name}</Badge>
                      ) : null}
                      <Badge variant={operational.variant}>{operational.label}</Badge>
                      <Badge variant={decisionVariant(item.final_decision)}>
                        {decisionLabel(item.final_decision)}
                      </Badge>
                      {parseBusinessTags(item.business_tags_json).map((tag) => (
                        <Badge key={`${item.id}-${tag}`} variant="muted">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                    <p className="text-base">{item.question_summary}</p>
                    <p className="text-sm leading-7 text-muted-foreground">
                      {operational.description}
                    </p>
                    <div className="flex flex-wrap gap-3 text-sm text-muted-foreground">
                      <span>
                        场景: {metadata.scene_name ?? parseBusinessTags(item.business_tags_json)[0] ?? "未标注"}
                      </span>
                      {metadata.cot_sequence_no ? <span>CoT 序号: {metadata.cot_sequence_no}</span> : null}
                      <span>QA 状态: {item.status}</span>
                      <span>评审人数: {item.review_count ?? 0}</span>
                      <span>
                        一致性:
                        {item.agreement_score === null
                          ? " 未生成"
                          : ` ${item.agreement_score.toFixed(2)}`}
                      </span>
                      <span>
                        聚合答案:
                        {item.current_answer_id === null ? " 未生成" : ` #${item.current_answer_id}`}
                      </span>
                      <span>
                        最终标准:
                        {item.final_standard_answer_id === null
                          ? " 未确认"
                          : ` #${item.final_standard_answer_id}`}
                      </span>
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <Button asChild size="sm" variant="secondary">
                      <Link href={`/admin/qas/${item.id}` as Route}>详情</Link>
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}

          <div className="flex flex-col gap-3 border-t border-border pt-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <span>
                第 {qaPage?.page ?? page} / {qaPage?.total_pages ?? 1} 页
              </span>
              <span>
                当前显示{" "}
                {qaPage && qaPage.total > 0
                  ? `${(qaPage.page - 1) * qaPage.page_size + 1}-${(qaPage.page - 1) * qaPage.page_size + qas.length}`
                  : "0"}{" "}
                条
              </span>
              <label className="flex items-center gap-2">
                <span>每页</span>
                <select
                  className="field min-w-[100px]"
                  value={pageSize}
                  onChange={(event) => {
                    const nextPageSize = Number(event.target.value);
                    setPageSize(nextPageSize);
                    setPage(1);
                  }}
                >
                  {[20, 50, 100, 200].map((size) => (
                    <option key={size} value={size}>
                      {size} 条
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="flex gap-3">
              <Button
                variant="secondary"
                disabled={loading || (qaPage?.page ?? page) <= 1}
                onClick={() => setPage((current) => Math.max(current - 1, 1))}
              >
                上一页
              </Button>
              <Button
                variant="secondary"
                disabled={loading || (qaPage?.page ?? page) >= (qaPage?.total_pages ?? 1)}
                onClick={() =>
                  setPage((current) => {
                    const totalPages = qaPage?.total_pages ?? current;
                    return Math.min(current + 1, totalPages);
                  })
                }
              >
                下一页
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
