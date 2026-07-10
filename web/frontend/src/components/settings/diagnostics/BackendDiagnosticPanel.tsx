"use client";

import { useState } from "react";
import { CheckCircle2, CircleAlert, Globe2, Loader2, Play, Search } from "lucide-react";

import { testBrowserBackend, testSearchBackend } from "@/lib/api";
import type { BrowserDiagnostic, SearchDiagnostic } from "@/lib/types";

const inputClass = "min-w-0 flex-1 rounded-lg border border-line bg-paper px-2.5 py-1.5 text-[12px] text-ink outline-none transition-colors placeholder:text-ink-faint focus:border-accent disabled:opacity-40";

function Result({ result }: { result: SearchDiagnostic | BrowserDiagnostic }) {
  return (
    <div role={result.ok ? "status" : "alert"} className={`mt-2 flex items-start gap-2 text-[11.5px] ${result.ok ? "text-ink-dim" : "text-err"}`}>
      {result.ok ? <CheckCircle2 className="mt-0.5 shrink-0 text-ok" size={14} /> : <CircleAlert className="mt-0.5 shrink-0" size={14} />}
      <div className="min-w-0 flex-1">
        {result.ok && result.kind === "search" && (
          <>
            <div className="font-medium text-ink">{result.provider} · {result.result_count} results · {result.latency_ms} ms</div>
            <div className="mt-0.5 truncate text-ink-faint">{result.results?.map((item) => item.domain || item.title).join(" · ")}</div>
          </>
        )}
        {result.ok && result.kind === "browser" && (
          <>
            <div className="font-medium text-ink">{result.backend} · HTTP {result.status_code} · {result.latency_ms} ms</div>
            <div className="mt-0.5 truncate text-ink-faint">
              {result.title || `${result.content_chars ?? 0} content chars`} · {result.proxy.endpoint}
            </div>
          </>
        )}
        {!result.ok && result.error}
      </div>
    </div>
  );
}

export default function BackendDiagnosticPanel({ disabled = false }: { disabled?: boolean }) {
  const [searchQuery, setSearchQuery] = useState("SearchOS agentic research");
  const [browserUrl, setBrowserUrl] = useState("https://example.com");
  const [busy, setBusy] = useState<"search" | "browser" | null>(null);
  const [searchResult, setSearchResult] = useState<SearchDiagnostic | null>(null);
  const [browserResult, setBrowserResult] = useState<BrowserDiagnostic | null>(null);

  const runSearch = async () => {
    if (!searchQuery.trim() || busy) return;
    setBusy("search");
    setSearchResult(null);
    try {
      setSearchResult(await testSearchBackend(searchQuery.trim()));
    } catch (error) {
      setSearchResult({ ok: false, kind: "search", provider: "unknown", latency_ms: 0, error: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(null);
    }
  };

  const runBrowser = async () => {
    if (!browserUrl.trim() || busy) return;
    setBusy("browser");
    setBrowserResult(null);
    try {
      setBrowserResult(await testBrowserBackend(browserUrl.trim()));
    } catch (error) {
      setBrowserResult({ ok: false, kind: "browser", backend: "unknown", latency_ms: 0, proxy: { configured: false, endpoint: "Unknown" }, error: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="surface divide-y divide-line rounded-lg border border-line">
      <div className="px-4 py-3">
        <div className="mb-2 flex items-center gap-2 text-[13px] font-medium text-ink"><Search className="text-accent-ink" size={14} /> Search query test</div>
        <div className="flex gap-2">
          <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} disabled={disabled || !!busy} aria-label="Search test query" className={inputClass} />
          <button type="button" onClick={runSearch} disabled={disabled || !!busy || !searchQuery.trim()} aria-label="Run search backend test" className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-ink text-paper disabled:opacity-40">
            {busy === "search" ? <Loader2 className="animate-spin" size={13} /> : <Play size={13} />}
          </button>
        </div>
        {searchResult && <Result result={searchResult} />}
      </div>

      <div className="px-4 py-3">
        <div className="mb-2 flex items-center gap-2 text-[13px] font-medium text-ink"><Globe2 className="text-accent-ink" size={14} /> Browser fetch test</div>
        <div className="flex gap-2">
          <input value={browserUrl} onChange={(event) => setBrowserUrl(event.target.value)} disabled={disabled || !!busy} aria-label="Browser test URL" className={inputClass} spellCheck={false} />
          <button type="button" onClick={runBrowser} disabled={disabled || !!busy || !browserUrl.trim()} aria-label="Run browser backend test" className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-ink text-paper disabled:opacity-40">
            {busy === "browser" ? <Loader2 className="animate-spin" size={13} /> : <Play size={13} />}
          </button>
        </div>
        {browserResult && <Result result={browserResult} />}
      </div>
    </div>
  );
}
