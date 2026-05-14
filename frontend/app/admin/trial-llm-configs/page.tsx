"use client";

import { useEffect, useMemo, useState } from "react";

import { apiFetch, type LlmConfigItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type FormState = {
  id: number | null;
  name: string;
  base_url: string;
  api_key: string;
  model_name: string;
  system_prompt: string;
  temperature: string;
  max_tokens: string;
  top_p: string;
  is_enabled: boolean;
};

const initialForm: FormState = {
  id: null,
  name: "",
  base_url: "",
  api_key: "",
  model_name: "",
  system_prompt: "",
  temperature: "0.2",
  max_tokens: "800",
  top_p: "0.95",
  is_enabled: true
};

function formatTime(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

export default function AdminTrialLlmConfigsPage() {
  const [configs, setConfigs] = useState<LlmConfigItem[]>([]);
  const [form, setForm] = useState<FormState>(initialForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadConfigs() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<LlmConfigItem[]>("/api/admin/trial-llm-configs");
      setConfigs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载试用模型失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadConfigs();
  }, []);

  function beginCreate() {
    setForm(initialForm);
    setNotice(null);
    setError(null);
  }

  function beginEdit(config: LlmConfigItem) {
    setForm({
      id: config.id,
      name: config.name,
      base_url: config.base_url,
      api_key: "",
      model_name: config.model_name,
      system_prompt: config.system_prompt ?? "",
      temperature: String(config.temperature),
      max_tokens: String(config.max_tokens ?? 800),
      top_p: String(config.top_p ?? 0.95),
      is_enabled: config.is_enabled
    });
    setNotice(null);
    setError(null);
  }

  function beginClone(config: LlmConfigItem) {
    setForm({
      id: null,
      name: config.name,
      base_url: config.base_url,
      api_key: "",
      model_name: config.model_name,
      system_prompt: config.system_prompt ?? "",
      temperature: String(config.temperature),
      max_tokens: String(config.max_tokens ?? 800),
      top_p: String(config.top_p ?? 0.95),
      is_enabled: true
    });
    setNotice("已复制配置，修改模型名后创建即可。");
    setError(null);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const payload = {
        name: form.name.trim(),
        provider_code: "custom_openai",
        provider_type: "openai_compatible",
        base_url: form.base_url.trim(),
        api_key: form.api_key.trim(),
        model_name: form.model_name.trim(),
        system_prompt: form.system_prompt.trim() || null,
        temperature: Number(form.temperature),
        max_tokens: Number(form.max_tokens),
        top_p: Number(form.top_p),
        is_enabled: form.is_enabled,
        is_active: false
      };

      if (!payload.name || !payload.base_url || !payload.model_name) {
        throw new Error("请完整填写名称、Base URL 和模型名");
      }
      if (!form.id && !payload.api_key) {
        throw new Error("新建配置时必须填写 API Key");
      }
      if (!Number.isFinite(payload.temperature)) {
        throw new Error("temperature 必须是数字");
      }

      if (form.id) {
        const current = configs.find((item) => item.id === form.id);
        await apiFetch(`/api/admin/trial-llm-configs/${form.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            ...payload,
            api_key: payload.api_key || (current?.has_api_key ? "__KEEP_EXISTING__" : "")
          })
        });
        setNotice("试用模型已更新。");
      } else {
        const modelNames = payload.model_name.split(",").map((s: string) => s.trim()).filter(Boolean);
        if (modelNames.length === 0) {
          throw new Error("请填写模型名");
        }
        for (const modelName of modelNames) {
          await apiFetch("/api/admin/trial-llm-configs", {
            method: "POST",
            body: JSON.stringify({
              ...payload,
              name: modelNames.length > 1 ? `${payload.name} - ${modelName}` : payload.name,
              model_name: modelName
            })
          });
        }
        setNotice(modelNames.length > 1 ? `已批量创建 ${modelNames.length} 个模型配置。` : "试用模型已创建。");
      }

      await loadConfigs();
      setForm(initialForm);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存试用模型失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleTest(configId: number) {
    setTestingId(configId);
    setError(null);
    setNotice(null);
    try {
      const result = await apiFetch<{ passed: boolean; message: string; latency_ms?: number }>(
        `/api/admin/trial-llm-configs/${configId}/test`,
        { method: "POST" }
      );
      await loadConfigs();
      if (result.passed) {
        setNotice(`连接检测通过${result.latency_ms ? `，耗时 ${result.latency_ms} ms` : ""}。`);
      } else {
        setError(result.message || "连接检测失败");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "连接检测失败");
    } finally {
      setTestingId(null);
    }
  }

  async function handleToggleEnabled(config: LlmConfigItem) {
    setTogglingId(config.id);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/trial-llm-configs/${config.id}/enable`, {
        method: "POST",
        body: JSON.stringify({ is_enabled: !config.is_enabled })
      });
      await loadConfigs();
      setNotice(config.is_enabled ? "试用模型已停用。" : "试用模型已启用。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "切换启用状态失败");
    } finally {
      setTogglingId(null);
    }
  }

  async function handleDelete(configId: number) {
    if (!confirm("确定要删除该试用模型配置吗？")) return;
    setDeletingId(configId);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/trial-llm-configs/${configId}`, { method: "DELETE" });
      setNotice("试用模型已删除。");
      await loadConfigs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除试用模型失败");
    } finally {
      setDeletingId(null);
    }
  }

  const enabledCount = useMemo(() => configs.filter((item) => item.is_enabled).length, [configs]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">试用模型</p>
        <h2 className="mt-2 font-serif text-4xl">只服务专家端模型试用的独立对话配置</h2>
      </div>

      <section className="grid gap-4 xl:grid-cols-[0.96fr_1.04fr]">
        <Card>
          <CardHeader>
            <CardTitle>{form.id ? "编辑试用模型" : "新增试用模型"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {error ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                {error}
              </div>
            ) : null}
            {notice ? (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
                {notice}
              </div>
            ) : null}

            <div className="rounded-lg border border-border bg-stone-50 p-5 text-sm leading-7 text-muted-foreground">
              这里的模型只给专家端“模型试用”页面使用，不参与 QA 自动评测，也不会进入专家评测里的
              LLM 辅助对话。该页只允许配置 `自定义 OpenAI 兼容接口`。
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <input className="field" value="custom_openai" readOnly />
              <input className="field" value="openai_compatible" readOnly />
            </div>

            <input
              className="field"
              placeholder="配置名称，例如 微调模型试用入口"
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            />
            <input
              className="field"
              placeholder="Base URL"
              value={form.base_url}
              onChange={(event) =>
                setForm((current) => ({ ...current, base_url: event.target.value }))
              }
            />
            <input
              className="field"
              placeholder={form.id ? "留空表示沿用当前 API Key" : "API Key"}
              type="password"
              value={form.api_key}
              onChange={(event) =>
                setForm((current) => ({ ...current, api_key: event.target.value }))
              }
            />
            <div className="grid gap-4 md:grid-cols-2">
              <input
                className="field"
                placeholder="模型名，多个用逗号分隔"
                title="支持逗号分隔批量创建，如 qwen3-8b-v1, qwen3-8b-v2"
                value={form.model_name}
                onChange={(event) =>
                  setForm((current) => ({ ...current, model_name: event.target.value }))
                }
              />
              <input
                className="field"
                placeholder="temperature"
                value={form.temperature}
                onChange={(event) =>
                  setForm((current) => ({ ...current, temperature: event.target.value }))
                }
              />
              <input
                className="field"
                placeholder="max_tokens"
                type="number"
                value={form.max_tokens}
                onChange={(event) =>
                  setForm((current) => ({ ...current, max_tokens: event.target.value }))
                }
              />
            </div>
            <input
              className="field"
              placeholder="top_p (0-1)"
              value={form.top_p}
              onChange={(event) =>
                setForm((current) => ({ ...current, top_p: event.target.value }))
              }
            />
            <textarea
              className="field-textarea"
              placeholder="系统提示词，可为空。"
              value={form.system_prompt}
              onChange={(event) =>
                setForm((current) => ({ ...current, system_prompt: event.target.value }))
              }
            />

            <label className="flex items-center gap-3 rounded-md border border-border bg-white px-4 py-3 text-sm">
              <input
                type="checkbox"
                checked={form.is_enabled}
                onChange={(event) =>
                  setForm((current) => ({ ...current, is_enabled: event.target.checked }))
                }
              />
              <span>启用为专家端可选试用模型</span>
            </label>

            <div className="flex justify-between gap-3">
              <Button variant="secondary" onClick={() => beginCreate()}>
                新建一条
              </Button>
              <Button disabled={saving} onClick={() => void handleSave()}>
                {saving ? "保存中…" : form.id ? "保存修改" : "创建配置"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle>已有试用模型</CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">当前已启用模型数：{enabledCount}</p>
            </div>
            <Button variant="secondary" onClick={() => void loadConfigs()}>
              刷新列表
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {!loading && configs.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
                当前还没有试用模型配置。
              </div>
            ) : null}

            {configs.map((config) => (
              <div key={config.id} className="rounded-lg border border-border bg-stone-50 p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-2">
                      <Badge variant={config.is_enabled ? "default" : "muted"}>
                        {config.is_enabled ? "已启用" : "已停用"}
                      </Badge>
                      <Badge variant="warning">自定义 OpenAI 兼容</Badge>
                      <Badge variant="muted">{config.model_name}</Badge>
                    </div>
                    <p className="font-medium">{config.name}</p>
                    <p className="text-sm text-muted-foreground">{config.base_url}</p>
                    <p className="text-xs text-muted-foreground">
                      API Key: {config.api_key_masked} / T {config.temperature} / max_t {config.max_tokens ?? 800} / top_p {config.top_p ?? 0.95}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      更新时间 {formatTime(config.updated_at)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      最近检测：
                      {config.last_tested_at
                        ? ` ${formatTime(config.last_tested_at)} / ${
                            config.last_test_status === "passed" ? "通过" : "失败"
                          }${
                            config.last_test_latency_ms !== null
                              ? ` / ${config.last_test_latency_ms} ms`
                              : ""
                          }`
                        : " 尚未检测"}
                    </p>
                    {config.last_test_message ? (
                      <p className="text-xs leading-6 text-muted-foreground">
                        {config.last_test_message}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="secondary" onClick={() => beginEdit(config)}>
                      编辑
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => beginClone(config)}>
                      复制
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={testingId === config.id}
                      onClick={() => void handleTest(config.id)}
                    >
                      {testingId === config.id ? "检测中…" : "检测配置"}
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={togglingId === config.id}
                      onClick={() => void handleToggleEnabled(config)}
                    >
                      {togglingId === config.id ? "处理中…" : config.is_enabled ? "停用" : "启用"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={deletingId === config.id}
                      onClick={() => void handleDelete(config.id)}
                    >
                      {deletingId === config.id ? "删除中…" : "删除"}
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
