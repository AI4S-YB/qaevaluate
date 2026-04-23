"use client";

import type { Route } from "next";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiFetch, type QaListItem, type TaxonomyItem } from "@/lib/api";
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
  const [qas, setQas] = useState<QaListItem[]>([]);
  const [technicalTypes, setTechnicalTypes] = useState<TaxonomyItem[]>([]);
  const [businessTags, setBusinessTags] = useState<TaxonomyItem[]>([]);
  const [filter, setFilter] = useState("");
  const [stateFilter, setStateFilter] = useState("all");
  const [technicalTypeFilter, setTechnicalTypeFilter] = useState("all");
  const [businessTagFilter, setBusinessTagFilter] = useState("all");
  const [moduleFilter, setModuleFilter] = useState("all");
  const [actionFilter, setActionFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadQas() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<QaListItem[]>("/api/admin/qas");
      setQas(data);
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
    void loadQas();
    void loadTaxonomy();
  }, []);

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

  const filtered = useMemo(() => {
    const keyword = filter.trim().toLowerCase();
    return qas.filter((item) => {
      const operational = resolveOperationalState(item);
      const metadata = parseQaMetadata(item.metadata_json);
      const matchedKeyword =
        !keyword ||
        item.application_name.toLowerCase().includes(keyword) ||
        (item.technical_type_name ?? "").toLowerCase().includes(keyword) ||
        (item.technical_type_code ?? "").toLowerCase().includes(keyword) ||
        item.question_summary.toLowerCase().includes(keyword) ||
        item.status.toLowerCase().includes(keyword) ||
        (item.final_decision ?? "").toLowerCase().includes(keyword) ||
        parseBusinessTags(item.business_tags_json).some((tag) =>
          tag.toLowerCase().includes(keyword)
        ) ||
        (metadata.scene_name ?? "").toLowerCase().includes(keyword) ||
        (metadata.module_name ?? "").toLowerCase().includes(keyword) ||
        (metadata.action_name ?? "").toLowerCase().includes(keyword) ||
        operational.label.toLowerCase().includes(keyword);
      if (!matchedKeyword) return false;
      if (stateFilter !== "all" && operational.label !== stateFilter) return false;
      if (technicalTypeFilter !== "all" && item.technical_type_code !== technicalTypeFilter) {
        return false;
      }
      if (
        businessTagFilter !== "all" &&
        !parseBusinessTags(item.business_tags_json).includes(businessTagFilter)
      ) {
        return false;
      }
      if (moduleFilter !== "all" && metadata.module_key !== moduleFilter) {
        return false;
      }
      if (actionFilter !== "all" && metadata.action_key !== actionFilter) {
        return false;
      }
      return true;
    });
  }, [actionFilter, businessTagFilter, filter, moduleFilter, qas, stateFilter, technicalTypeFilter]);

  const summary = useMemo(() => {
    return qas.reduce(
      (acc, item) => {
        const state = resolveOperationalState(item).label;
        if (state === "待聚合") acc.pendingAggregate += 1;
        if (state === "待最终确认") acc.pendingFinal += 1;
        if (state === "聚合与最终不一致") acc.mismatch += 1;
        if (state === "已闭环") acc.closed += 1;
        return acc;
      },
      { pendingAggregate: 0, pendingFinal: 0, mismatch: 0, closed: 0 }
    );
  }, [qas]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">QA 数据</p>
          <h2 className="mt-2 font-serif text-4xl">按聚合阶段分流查看问题、答案和最终确认状态</h2>
        </div>
        <div className="grid gap-3 xl:grid-cols-[280px_180px_180px_220px_180px_120px]">
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
          <Button variant="secondary" onClick={() => void loadQas()}>
            刷新列表
          </Button>
        </div>
      </div>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          ["待聚合", summary.pendingAggregate],
          ["待最终确认", summary.pendingFinal],
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
              当前 {filtered.length} 条 / 全部 {qas.length} 条
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
        </CardContent>
      </Card>
    </div>
  );
}
