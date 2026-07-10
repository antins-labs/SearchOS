"use client";

import { useState } from "react";
import { CheckCircle2, CircleAlert, Loader2, Play, Sparkles } from "lucide-react";

import { testProvider } from "@/lib/api";
import type { ProviderDiagnostic } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import Select from "@/components/settings/controls/Select";

export default function ProviderDiagnosticPanel() {
  const { settings, status } = useSettings();
  const roles = Object.keys(settings?.models.roles ?? {});
  const [role, setRole] = useState(roles.includes("orchestrator") ? "orchestrator" : roles[0] ?? "");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ProviderDiagnostic | null>(null);

  const run = async () => {
    if (!role || busy) return;
    setBusy(true);
    setResult(null);
    try {
      setResult(await testProvider(role));
    } catch (error) {
      setResult({
        ok: false,
        kind: "provider",
        role,
        latency_ms: 0,
        error: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="surface rounded-lg border border-line px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles className="text-accent-ink" size={15} />
        <div className="mr-auto">
          <div className="text-[13px] font-medium text-ink">Provider connection test</div>
          <div className="text-[11px] text-ink-faint">Minimal live request through the selected role</div>
        </div>
        <Select
          value={role}
          onChange={setRole}
          ariaLabel="Role to test"
          disabled={busy || status !== "ready"}
          options={roles.map((value) => ({ value, label: value }))}
        />
        <button
          type="button"
          onClick={run}
          disabled={!role || busy || status !== "ready"}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-ink px-3 text-[12px] font-medium text-paper transition-opacity hover:opacity-85 disabled:opacity-40"
        >
          {busy ? <Loader2 className="animate-spin" size={13} /> : <Play size={13} />}
          Test
        </button>
      </div>

      {result && (
        <div role={result.ok ? "status" : "alert"} className={`mt-3 flex items-start gap-2 border-t border-line pt-3 text-[11.5px] ${result.ok ? "text-ink-dim" : "text-err"}`}>
          {result.ok ? <CheckCircle2 className="mt-0.5 shrink-0 text-ok" size={14} /> : <CircleAlert className="mt-0.5 shrink-0" size={14} />}
          <div className="min-w-0 flex-1">
            {result.ok ? (
              <>
                <div className="font-medium text-ink">{result.provider} · {result.model} · {result.latency_ms} ms</div>
                <div className="mt-0.5 text-ink-faint">
                  Thinking {result.thinking_status?.replaceAll("_", " ")}
                  {result.usage?.total_tokens ? ` · ${result.usage.total_tokens} test tokens` : ""}
                </div>
              </>
            ) : result.error}
          </div>
        </div>
      )}
    </div>
  );
}
