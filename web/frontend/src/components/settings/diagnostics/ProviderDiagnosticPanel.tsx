"use client";

import { useState } from "react";
import { CheckCircle2, CircleAlert, Loader2, Play, Sparkles } from "lucide-react";

import { testProvider } from "@/lib/api";
import type { ModelsView, ProviderDiagnostic } from "@/lib/types";
import { modelPurposeGroups } from "@/lib/modelPurposes";
import { useSettings } from "@/components/settings/SettingsProvider";
import Select from "@/components/ui/Select";

export default function ProviderDiagnosticPanel() {
  const { settings, status, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";
  const purposes = settings ? modelPurposeGroups(settings.models).flatMap((group) => group.purposes) : [];
  const [selectedRole, setRole] = useState("orchestrator");
  const role = purposes.some((purpose) => purpose.role === selectedRole) ? selectedRole : purposes[0]?.role ?? "";
  const [busy, setBusy] = useState(false);
  const [completed, setCompleted] = useState<{ key: string; models: ModelsView | undefined; result: ProviderDiagnostic } | null>(null);
  const profileName = settings?.models.roles[role] ?? "";
  const profile = settings?.models.profiles[profileName];
  const configurationKey = JSON.stringify([role, profileName, profile]);
  const result = completed?.key === configurationKey && completed.models === settings?.models ? completed.result : null;

  const run = async () => {
    if (!role || busy) return;
    setBusy(true);
    setCompleted(null);
    try {
      setCompleted({ key: configurationKey, models: settings?.models, result: await testProvider(role) });
    } catch (error) {
      setCompleted({ key: configurationKey, models: settings?.models, result: {
        ok: false,
        kind: "provider",
        role,
        latency_ms: 0,
        error: error instanceof Error ? error.message : String(error),
      } });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="surface rounded-lg border border-line px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles className="text-accent-ink" size={15} />
        <div className="mr-auto">
          <div className="text-[13px] font-medium text-ink">{zh ? "模型连接测试" : "Provider connection test"}</div>
          <div className="text-[12px] text-ink-faint">{zh ? "发送一次真实文本请求；图片与工具调用能力需另行验证。" : "Send a live text request. Image input and tool calling need separate verification."}</div>
        </div>
        <Select
          value={role}
          onChange={setRole}
          ariaLabel={zh ? "测试用途" : "Role to test"}
          disabled={busy || status !== "ready"}
          className="w-full sm:w-56"
          options={purposes.map((purpose) => ({ value: purpose.role, label: purpose.label[uiPrefs.language] }))}
        />
        <button
          type="button"
          onClick={run}
          disabled={!role || !profile?.api_key_set || busy || status !== "ready"}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-ink px-3 text-[12px] font-medium text-paper transition-opacity hover:opacity-85 disabled:opacity-40"
        >
          {busy ? <Loader2 className="animate-spin" size={13} /> : <Play size={13} />}
          {zh ? "测试" : "Test"}
        </button>
      </div>

      <p className="mt-2 break-words text-[11.5px] text-ink-faint">
        {profile ? `${profileName} · ${profile.model}` : (zh ? "请先为该用途绑定有效的模型配置。" : "Assign a valid model configuration to this purpose first.")}
        {profile && !profile.api_key_set && <span className="ml-2 text-warn">{zh ? `缺少密钥：${profile.api_key_env}` : `Missing key: ${profile.api_key_env}`}</span>}
      </p>

      {result && (
        <div role={result.ok ? "status" : "alert"} className={`mt-3 flex items-start gap-2 border-t border-line pt-3 text-[11.5px] ${result.ok ? "text-ink-dim" : "text-err"}`}>
          {result.ok ? <CheckCircle2 className="mt-0.5 shrink-0 text-ok" size={14} /> : <CircleAlert className="mt-0.5 shrink-0" size={14} />}
          <div className="min-w-0 flex-1">
            {result.ok ? (
              <>
                <div className="font-medium text-ink">{zh ? "文本连接通过" : "Text connection passed"} · {result.provider} · {result.model} · {result.latency_ms} ms</div>
                <div className="mt-0.5 text-ink-faint">
                  {zh ? "推理状态" : "Thinking"} {result.thinking_status?.replaceAll("_", " ")}
                  {result.usage?.total_tokens ? ` · ${result.usage.total_tokens} ${zh ? "个测试 Token" : "test tokens"}` : ""}
                </div>
              </>
            ) : result.error}
          </div>
        </div>
      )}
    </div>
  );
}
