"use client";

import { useState } from "react";
import { ChevronRight, Loader2 } from "lucide-react";
import { clearNetworkRoutes, getNetworkRoutes, putNetwork, testNetwork } from "@/lib/api";
import type { LearnedNetworkRoute, NetworkDiagnostic, NetworkView } from "@/lib/types";
import { useSettings } from "@/components/settings/SettingsProvider";
import { Card, Row } from "@/components/settings/primitives";
import TextField from "@/components/settings/controls/TextField";
import Toggle from "@/components/settings/controls/Toggle";

const buttonClass = "rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-ink-dim disabled:opacity-40";
const inputClass = "min-w-0 flex-1 rounded-lg border border-line bg-paper px-2.5 py-1.5 text-[12px] text-ink outline-none focus:border-accent disabled:opacity-40";

export default function NetworkSettings({ disabled = false }: { disabled?: boolean }) {
  const { settings, mutate, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";
  const network = settings?.network;
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [learned, setLearned] = useState<LearnedNetworkRoute[]>([]);
  const [host, setHost] = useState("");
  const [route, setRoute] = useState<"direct" | "proxy">("direct");
  const [url, setUrl] = useState("https://example.com");
  const [diagnostic, setDiagnostic] = useState<NetworkDiagnostic | null>(null);

  if (!network) return null;

  const save = (patch: Partial<Pick<NetworkView, "proxy_url" | "auto_route" | "routes">>) =>
    mutate({
      call: () => putNetwork(patch),
      merge: (state, view) => ({ ...state, network: view }),
      errorLabel: zh ? "网络配置保存失败" : "Couldn't save network settings",
    });

  const run = async (action: () => Promise<void>) => {
    if (busy || disabled) return;
    setBusy(true);
    setError("");
    try { await action(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  const refresh = async () => setLearned((await getNetworkRoutes()).routes);
  const routeLabel = (value: string) => value === "direct" ? (zh ? "直连" : "Direct") : (zh ? "代理" : "Proxy");
  const locked = disabled || busy;

  return (
    <Card>
      <Row label={zh ? "代理地址" : "Proxy URL"}
        hint={zh ? "模型、网页和 skill 共用。留空使用直连，无需填写网站域名。" : "Shared by models, pages and skills. Leave empty for direct access; no domain setup needed."}>
        <TextField value={network.proxy_url} disabled={locked} placeholder="http://127.0.0.1:7890"
          onCommit={(value) => save({ proxy_url: value })} />
      </Row>
      <Row label={zh ? "自动选择可用线路" : "Automatically select an available route"}
        hint={zh ? "连接失败时检查备用线路，并记住可用选择。设置变更用于新任务。" : "Checks an alternative after connection failures and remembers successful routes. Changes apply to new tasks."}>
        <Toggle checked={network.auto_route} disabled={locked}
          label={zh ? "自动选择可用线路" : "Automatically select an available route"}
          onChange={(value) => save({ auto_route: value })} />
      </Row>
      <div className="px-4 py-3">
        <button type="button" onClick={() => {
          setExpanded(!expanded);
          if (!expanded) void run(refresh);
        }} className="flex items-center gap-1 text-[12px] text-ink-faint hover:text-ink-dim">
          <ChevronRight size={13} className={expanded ? "rotate-90" : ""} />
          {zh ? "高级网络诊断" : "Advanced network diagnostics"}
        </button>
        {expanded && <div className="mt-3 space-y-4 text-[12px]">
          <p className="text-ink-faint">
            {zh ? "配置来源：" : "Configuration source: "}{network.source}
            {network.credential_set && (zh ? " · 已保存代理认证" : " · Proxy credentials saved")}
          </p>
          <div>
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="font-medium text-ink">{zh ? "自动记录" : "Learned routes"}</span>
              <div className="flex gap-2">
                <button type="button" disabled={locked} className={buttonClass} onClick={() => run(refresh)}>{zh ? "刷新" : "Refresh"}</button>
                <button type="button" disabled={locked || !learned.length} className={buttonClass}
                  onClick={() => run(async () => setLearned((await clearNetworkRoutes()).routes))}>{zh ? "清除全部" : "Clear all"}</button>
              </div>
            </div>
            {!learned.length && <p className="text-ink-faint">{zh ? "尚无自动记录，访问网站时会自动识别。" : "No learned routes yet. Hosts are discovered during requests."}</p>}
            {learned.map((item) => <div key={`${item.host}:${item.port}`} className="flex items-center gap-3 py-1 text-ink-dim">
              <span className="min-w-0 flex-1 truncate font-mono">{item.host}:{item.port}</span>
              <span>{routeLabel(item.route)}</span>
              <span className="text-ink-faint" title={zh ? "过期时间" : "Expires"}>{new Date(item.expires_at * 1000).toLocaleString()}</span>
              <button type="button" disabled={locked} className={buttonClass} aria-label={`${zh ? "清除" : "Clear"} ${item.host}`}
                onClick={() => run(async () => setLearned((await clearNetworkRoutes(item.host)).routes))}>{zh ? "清除" : "Clear"}</button>
            </div>)}
          </div>
          <div>
            <p className="mb-2 font-medium text-ink">{zh ? "手动覆盖" : "Manual overrides"}</p>
            <p className="mb-2 text-ink-faint">{zh ? "仅在需要固定线路时添加，规则覆盖该主机及其子域名。" : "Add only when a fixed route is needed. Rules include the host and its subdomains."}</p>
            {Object.entries(network.routes).map(([name, value]) => <div key={name} className="mb-2 flex items-center gap-3 text-ink-dim">
              <span className="min-w-0 flex-1 truncate font-mono">{name}</span><span>{routeLabel(value)}</span>
              <button type="button" disabled={locked} className={buttonClass} aria-label={`${zh ? "删除规则" : "Remove rule"} ${name}`}
                onClick={() => { const rules = { ...network.routes }; delete rules[name]; void save({ routes: rules }); }}>{zh ? "删除" : "Remove"}</button>
            </div>)}
            <div className="flex gap-2">
              <input value={host} onChange={(event) => setHost(event.target.value)} disabled={locked} className={inputClass}
                placeholder="example.com" aria-label={zh ? "覆盖规则主机" : "Override host"} />
              <select value={route} onChange={(event) => setRoute(event.target.value as "direct" | "proxy")} disabled={locked}
                aria-label={zh ? "覆盖线路" : "Override route"} className={inputClass}>
                <option value="direct">{routeLabel("direct")}</option><option value="proxy">{routeLabel("proxy")}</option>
              </select>
              <button type="button" disabled={locked || !host.trim()} className={buttonClass}
                onClick={() => run(async () => { if (await save({ routes: { ...network.routes, [host.trim()]: route } })) setHost(""); })}>{zh ? "添加" : "Add"}</button>
            </div>
          </div>
          <div>
            <p className="mb-2 font-medium text-ink">{zh ? "线路检查" : "Route check"}</p>
            <div className="flex gap-2">
              <input value={url} onChange={(event) => setUrl(event.target.value)} disabled={locked} className={inputClass}
                aria-label={zh ? "线路检查地址" : "Route check URL"} />
              <button type="button" disabled={locked || !url.trim()} className={buttonClass}
                onClick={() => run(async () => { setDiagnostic(await testNetwork(url.trim())); await refresh(); })}>{zh ? "检查" : "Check"}</button>
            </div>
            {diagnostic && <div className="mt-2 space-y-1" role={diagnostic.ok ? "status" : "alert"}>
              <p className={diagnostic.ok ? "text-ok" : "text-err"}>{diagnostic.ok ? (zh ? "连接成功" : "Connected") : diagnostic.error || (zh ? "连接失败" : "Connection failed")}</p>
              {diagnostic.attempts?.map((attempt, index) => <p key={index} className="text-ink-dim">
                {routeLabel(attempt.route)} · {attempt.phase} · {attempt.latency_ms ?? 0} ms {attempt.error}
              </p>)}
            </div>}
          </div>
          {busy && <Loader2 size={14} className="animate-spin text-ink-faint" />}
          {error && <p role="alert" className="text-err">{error}</p>}
        </div>}
      </div>
    </Card>
  );
}
