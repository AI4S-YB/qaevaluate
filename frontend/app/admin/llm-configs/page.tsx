"use client";

import { useEffect, useMemo, useState } from "react";

import { apiFetch, type LlmConfigItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type ProviderPreset = {
  code: string;
  label: string;
  baseUrl: string;
  defaultModel: string;
  description: string;
};

const providerPresets: ProviderPreset[] = [
  {
    code: "qwen_dashscope",
    label: "阿里百炼 / Qwen",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    defaultModel: "qwen-plus",
    description: "适合 QA 自动评测、LLM 辅助分析和快速改写。"
  },
  {
    code: "zhipu_glm",
    label: "智谱 / GLM",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4/",
    defaultModel: "glm-4-plus",
    description: "官方 OpenAI 兼容接口。"
  },
  {
    code: "deepseek",
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com",
    defaultModel: "deepseek-chat",
    description: "成本较低，适合辅助评测。"
  },
  {
    code: "moonshot_kimi",
    label: "月之暗面 / Kimi",
    baseUrl: "https://api.moonshot.cn/v1",
    defaultModel: "moonshot-v1-8k",
    description: "适合长文本场景。"
  },
  {
    code: "siliconflow",
    label: "硅基流动",
    baseUrl: "https://api.siliconflow.cn/v1",
    defaultModel: "Qwen/Qwen2.5-72B-Instruct",
    description: "托管多个模型，便于快速切换。"
  },
  {
    code: "openai_proxy",
    label: "GPT 代理",
    baseUrl: "https://your-proxy.example.com/v1",
    defaultModel: "gpt-4.1",
    description: "适合通过代理接入 GPT 系列。"
  },
  {
    code: "claude_proxy",
    label: "Claude 代理",
    baseUrl: "https://your-proxy.example.com/v1",
    defaultModel: "claude-sonnet-4-20250514",
    description: "适合通过 OpenAI 兼容代理接入 Claude。"
  },
  {
    code: "gemini_openai",
    label: "Gemini OpenAI 兼容",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai/",
    defaultModel: "gemini-2.5-pro",
    description: "Google Gemini 官方 compatibility。"
  },
  {
    code: "custom_openai",
    label: "自定义 OpenAI 兼容",
    baseUrl: "",
    defaultModel: "",
    description: "适合自建网关和统一代理。"
  },
  {
    code: "ai4s_lora",
    label: "AI4S LoRA 模型",
    baseUrl: "http://182.92.166.143:38080/v1",
    defaultModel: "qwen3-8b-v1-lora",
    description: "AI4S 自建 LoRA 微调模型服务，适合农业领域 QA 评测。"
  }
];

type FormState = {
  id: number | null;
  name: string;
  provider_code: string;
  provider_type: "openai_compatible";
  base_url: string;
  api_key: string;
  model_name: string;
  system_prompt: string;
  temperature: string;
  max_tokens: string;
  top_p: string;
  is_enabled: boolean;
  is_active: boolean;
};

const initialForm: FormState = {
  id: null,
  name: "",
  provider_code: "qwen_dashscope",
  provider_type: "openai_compatible",
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  api_key: "",
  model_name: "qwen-plus",
  system_prompt: "",
  temperature: "0.2",
  max_tokens: "800",
  top_p: "0.95",
  is_enabled: true,
  is_active: false
};

function formatTime(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

function getProviderPreset(code: string) {
  return providerPresets.find((item) => item.code === code) ?? providerPresets.at(-1)!;
}

function getProviderLabel(code: string) {
  return getProviderPreset(code).label;
}

export default function AdminLlmConfigsPage() {
  const [configs, setConfigs] = useState<LlmConfigItem[]>([]);
  const [form, setForm] = useState<FormState>(initialForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [activatingId, setActivatingId] = useState<number | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadConfigs() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<LlmConfigItem[]>("/api/admin/llm-configs");
      setConfigs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载评测模型失败");
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
      provider_code: config.provider_code,
      provider_type: config.provider_type,
      base_url: config.base_url,
      api_key: "",
      model_name: config.model_name,
      system_prompt: config.system_prompt ?? "",
      temperature: String(config.temperature),
      max_tokens: String(config.max_tokens ?? 800),
      top_p: String(config.top_p ?? 0.95),
      is_enabled: config.is_enabled,
      is_active: config.is_active
    });
    setNotice(null);
    setError(null);
  }

  function handlePresetChange(nextCode: string) {
    const preset = getProviderPreset(nextCode);
    setForm((current) => ({
      ...current,
      provider_code: preset.code,
      base_url: preset.baseUrl || current.base_url,
      model_name: current.model_name || preset.defaultModel
    }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const payload = {
        name: form.name.trim(),
        provider_code: form.provider_code,
        provider_type: form.provider_type,
        base_url: form.base_url.trim(),
        api_key: form.api_key.trim(),
        model_name: form.model_name.trim(),
        system_prompt: form.system_prompt.trim() || null,
        temperature: Number(form.temperature),
        max_tokens: Number(form.max_tokens),
        top_p: Number(form.top_p),
        is_enabled: form.is_enabled || form.is_active,
        is_active: form.is_active
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
      if (!Number.isFinite(payload.max_tokens) || payload.max_tokens < 1) {
        throw new Error("max_tokens 必须是正整数");
      }
      if (!Number.isFinite(payload.top_p) || payload.top_p < 0 || payload.top_p > 1) {
        throw new Error("top_p 必须在 0-1 之间");
      }

      if (form.id) {
        const current = configs.find((item) => item.id === form.id);
        await apiFetch(`/api/admin/llm-configs/${form.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            ...payload,
            api_key: payload.api_key || (current?.has_api_key ? "__KEEP_EXISTING__" : "")
          })
        });
        setNotice("评测模型已更新。");
      } else {
        await apiFetch("/api/admin/llm-configs", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        setNotice("评测模型已创建。");
      }

      await loadConfigs();
      setForm(initialForm);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存评测模型失败");
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
        `/api/admin/llm-configs/${configId}/test`,
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

  async function handleActivate(configId: number) {
    setActivatingId(configId);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/llm-configs/${configId}/activate`, { method: "POST" });
      await loadConfigs();
      setNotice("主评测模型已切换。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "切换主模型失败");
    } finally {
      setActivatingId(null);
    }
  }

  async function handleToggleEnabled(config: LlmConfigItem) {
    setTogglingId(config.id);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/api/admin/llm-configs/${config.id}/enable`, {
        method: "POST",
        body: JSON.stringify({ is_enabled: !config.is_enabled })
      });
      await loadConfigs();
      setNotice(config.is_enabled ? "模型已停用。" : "模型已启用。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "切换启用状态失败");
    } finally {
      setTogglingId(null);
    }
  }

  const activeConfig = configs.find((item) => item.is_active) ?? null;
  const enabledCount = useMemo(() => configs.filter((item) => item.is_enabled).length, [configs]);
  const selectedPreset = getProviderPreset(form.provider_code);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">评测模型</p>
        <h2 className="mt-2 font-serif text-4xl">只服务 QA 评测链路的模型配置</h2>
      </div>

      <section className="grid gap-4 xl:grid-cols-[0.96fr_1.04fr]">
        <Card>
          <CardHeader>
            <CardTitle>{form.id ? "编辑评测模型" : "新增评测模型"}</CardTitle>
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
              这里的模型只给 QA 自动评测、专家辅助对话评测、快速改写等评测链路使用。
              专家端“模型试用”请到单独的“试用模型”页面配置。
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <select
                className="field"
                value={form.provider_code}
                onChange={(event) => handlePresetChange(event.target.value)}
              >
                {providerPresets.map((preset) => (
                  <option key={preset.code} value={preset.code}>
                    {preset.label}
                  </option>
                ))}
              </select>
              <input className="field" value="openai_compatible" readOnly />
            </div>

            <div className="rounded-lg border border-border bg-white p-4 text-sm leading-7 text-muted-foreground">
              <p className="font-medium text-foreground">{selectedPreset.label}</p>
              <p className="mt-2">{selectedPreset.description}</p>
            </div>

            <input
              className="field"
              placeholder="配置名称，例如 主评测模型"
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
            <div className="grid gap-4 md:grid-cols-3">
              <input
                className="field"
                placeholder="模型名"
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

            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex items-center gap-3 rounded-md border border-border bg-white px-4 py-3 text-sm">
                <input
                  type="checkbox"
                  checked={form.is_enabled}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      is_enabled: event.target.checked || current.is_active
                    }))
                  }
                />
                <span>启用为可选模型</span>
              </label>
              <label className="flex items-center gap-3 rounded-md border border-border bg-white px-4 py-3 text-sm">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      is_active: event.target.checked,
                      is_enabled: event.target.checked ? true : current.is_enabled
                    }))
                  }
                />
                <span>设为主模型</span>
              </label>
            </div>

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
              <CardTitle>已有评测模型</CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">
                当前主模型：
                {activeConfig ? ` ${activeConfig.name} / ${activeConfig.model_name}` : " 未设置"}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">当前已启用模型数：{enabledCount}</p>
            </div>
            <Button variant="secondary" onClick={() => void loadConfigs()}>
              刷新列表
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {!loading && configs.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
                当前还没有评测模型配置。
              </div>
            ) : null}

            {configs.map((config) => (
              <div key={config.id} className="rounded-lg border border-border bg-stone-50 p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-2">
                      {config.is_active ? <Badge variant="success">主模型</Badge> : null}
                      <Badge variant={config.is_enabled ? "default" : "muted"}>
                        {config.is_enabled ? "已启用" : "已停用"}
                      </Badge>
                      <Badge variant="warning">{getProviderLabel(config.provider_code)}</Badge>
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
                      disabled={config.is_active || activatingId === config.id}
                      onClick={() => void handleActivate(config.id)}
                    >
                      {config.is_active ? "当前主模型" : activatingId === config.id ? "切换中…" : "设为主模型"}
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
