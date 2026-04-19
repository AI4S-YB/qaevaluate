"use client";

import { useEffect, useState } from "react";

import { apiFetch, type LlmConfigItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type FormState = {
  id: number | null;
  name: string;
  provider_type: "openai_compatible";
  base_url: string;
  api_key: string;
  model_name: string;
  system_prompt: string;
  temperature: string;
};

const initialForm: FormState = {
  id: null,
  name: "",
  provider_type: "openai_compatible",
  base_url: "",
  api_key: "",
  model_name: "",
  system_prompt: "",
  temperature: "0.2"
};

function formatTime(value: string) {
  return value.replace("T", " ").slice(0, 16);
}

export default function AdminLlmConfigsPage() {
  const [configs, setConfigs] = useState<LlmConfigItem[]>([]);
  const [form, setForm] = useState<FormState>(initialForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [activatingId, setActivatingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadConfigs() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<LlmConfigItem[]>("/api/admin/llm-configs");
      setConfigs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载模型配置失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadConfigs();
  }, []);

  function beginCreate() {
    setForm(initialForm);
    setError(null);
  }

  function beginEdit(config: LlmConfigItem) {
    setForm({
      id: config.id,
      name: config.name,
      provider_type: config.provider_type,
      base_url: config.base_url,
      api_key: "",
      model_name: config.model_name,
      system_prompt: config.system_prompt ?? "",
      temperature: String(config.temperature)
    });
    setNotice(null);
    setError(null);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setNotice(null);

    try {
      const payload = {
        name: form.name.trim(),
        provider_type: form.provider_type,
        base_url: form.base_url.trim(),
        api_key: form.api_key.trim(),
        model_name: form.model_name.trim(),
        system_prompt: form.system_prompt.trim() || null,
        temperature: Number(form.temperature)
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
        await apiFetch(`/api/admin/llm-configs/${form.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            ...payload,
            api_key: payload.api_key || (current?.has_api_key ? "__KEEP_EXISTING__" : "")
          })
        });
        setNotice("模型配置已更新。");
      } else {
        await apiFetch("/api/admin/llm-configs", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        setNotice("模型配置已创建。");
      }

      await loadConfigs();
      setForm(initialForm);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存模型配置失败");
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
        setNotice(
          `模型连通性检测通过${result.latency_ms ? `，耗时 ${result.latency_ms} ms` : ""}。`
        );
      } else {
        setError(result.message || "模型连通性检测失败");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "模型连通性检测失败");
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
      setNotice("当前生效模型已切换。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "切换当前模型失败");
    } finally {
      setActivatingId(null);
    }
  }

  const activeConfig = configs.find((item) => item.is_active) ?? null;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">模型配置</p>
        <h2 className="mt-2 font-serif text-4xl">让专家端 LLM 辅助直接走后台统一配置的 API</h2>
      </div>

      <section className="grid gap-4 xl:grid-cols-[0.96fr_1.04fr]">
        <Card>
          <CardHeader>
            <CardTitle>{form.id ? "编辑模型配置" : "新增模型配置"}</CardTitle>
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

            <div className="rounded-[28px] border border-border bg-stone-50 p-5 text-sm leading-7 text-muted-foreground">
              当前 MVP 先支持 `OpenAI 兼容接口`。也就是只要你的模型服务支持
              `POST /chat/completions`，就可以接入专家端的事实核查、风险分析和标准答案改写。
            </div>

            <input
              className="field"
              placeholder="配置名称，例如 GPT-4.1 评测"
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            />
            <input className="field" value="openai_compatible" readOnly />
            <input
              className="field"
              placeholder="Base URL，例如 https://api.openai.com/v1"
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
                placeholder="模型名，例如 gpt-4.1"
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
            </div>
            <textarea
              className="field-textarea"
              placeholder="系统提示词，可为空。用于统一约束专家辅助模型的输出风格。"
              value={form.system_prompt}
              onChange={(event) =>
                setForm((current) => ({ ...current, system_prompt: event.target.value }))
              }
            />

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
              <CardTitle>已有配置</CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">
                当前生效模型：{activeConfig ? `${activeConfig.name} / ${activeConfig.model_name}` : "未设置"}
              </p>
            </div>
            <Button variant="secondary" onClick={() => void loadConfigs()}>
              刷新列表
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {!loading && configs.length === 0 ? (
              <div className="rounded-[28px] border border-dashed border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
                当前还没有模型配置。创建后，专家端的 LLM 辅助才会真正调用外部模型。
              </div>
            ) : null}

            {configs.map((config) => (
              <div
                key={config.id}
                className="rounded-[28px] border border-border bg-stone-50 p-4"
              >
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-2">
                      <Badge variant={config.is_active ? "success" : "muted"}>
                        {config.is_active ? "生效中" : "未生效"}
                      </Badge>
                      <Badge variant="warning">{config.provider_type}</Badge>
                      <Badge variant="muted">{config.model_name}</Badge>
                    </div>
                    <p className="font-medium">{config.name}</p>
                    <p className="text-sm text-muted-foreground">{config.base_url}</p>
                    <p className="text-xs text-muted-foreground">
                      API Key: {config.api_key_masked} / temperature {config.temperature}
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
                      disabled={config.is_active || activatingId === config.id}
                      onClick={() => void handleActivate(config.id)}
                    >
                      {config.is_active
                        ? "当前模型"
                        : activatingId === config.id
                          ? "切换中…"
                          : "设为当前模型"}
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
