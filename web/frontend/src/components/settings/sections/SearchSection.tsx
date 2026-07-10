"use client";

import { useState } from "react";
import { ChevronRight, ExternalLink } from "lucide-react";

import { putAdvanced, putMisc, putSearchBackend } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";
import { Card, OfflineSkeleton, Row, SectionShell } from "@/components/settings/primitives";
import Select from "@/components/settings/controls/Select";
import TextField from "@/components/settings/controls/TextField";
import KeyEditor from "@/components/settings/models/KeyEditor";
import BackendDiagnosticPanel from "@/components/settings/diagnostics/BackendDiagnosticPanel";

const BROWSER_BACKENDS = ["jina", "aiohttp", "crawl4ai", "search_engine"];

export default function SearchSection() {
  const { settings, status, mutate } = useSettings();
  const [searchKeysOpen, setSearchKeysOpen] = useState(false);

  if (!settings) {
    return (
      <SectionShell id="search" title="Search & browse"
        description="Choose the search provider and page-fetch engine. Provider keys are stored in .env and never shown.">
        <OfflineSkeleton />
      </SectionShell>
    );
  }

  const { models, advanced } = settings;
  const disabled = status !== "ready";

  const setAdvanced = (patch: { https_proxy?: string; browser_disk_cache_dir?: string }) =>
    mutate({
      optimistic: (s) => ({ ...s, advanced: { ...s.advanced, ...patch } }),
      call: () => putAdvanced(patch),
      merge: (s, view) => ({ ...s, advanced: view }),
      errorLabel: "Couldn't save setting",
    });

  const setSearchBackend = (provider: string) =>
    mutate({
      call: () => putSearchBackend(provider === "auto" ? null : provider),
      merge: (s, search) => ({ ...s, models: { ...s.models, search } }),
      errorLabel: "Couldn't switch search backend",
    });

  const setBrowserBackend = (backend: string) =>
    mutate({
      optimistic: (s) => ({ ...s, models: { ...s.models, browser_backend: backend } }),
      call: () => putMisc({ browser_backend: backend }),
      errorLabel: "Couldn't switch browser backend",
    });

  return (
    <SectionShell id="search" title="Search & browse"
      description="Choose the search provider and page-fetch engine. Provider keys are stored in .env and never shown.">
      <Card>
        <Row label="Search backend"
          hint={models.search.configured ? undefined : `Auto-resolved to ${models.search.resolved}`}>
          <Select
            value={models.search.configured ?? "auto"}
            disabled={disabled}
            ariaLabel="Search backend"
            options={[
              { value: "auto", label: `Auto (${models.search.resolved})` },
              ...models.search.providers.map((pr) => ({
                value: pr.name,
                label: pr.key_set || pr.name === "ragflow" ? pr.name : `${pr.name} (no key)`,
                disabled: !pr.key_set && pr.name !== "ragflow",
              })),
            ]}
            onChange={setSearchBackend}
          />
        </Row>
        <div className="px-4 py-2.5">
          <button
            type="button"
            onClick={() => setSearchKeysOpen((v) => !v)}
            className="flex items-center gap-1 text-[12.5px] text-ink-faint transition-colors hover:text-ink-dim"
          >
            <ChevronRight size={13}
              className={`transition-transform duration-200 ${searchKeysOpen ? "rotate-90" : ""}`} />
            Search provider keys
          </button>
          {searchKeysOpen && (
            <div className="rise-in mt-2 space-y-2">
              {models.search.providers.map((pr) => (
                <div key={pr.name} className="flex items-center justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${pr.key_set ? "bg-ok" : "bg-line-strong"}`} />
                    <span className="truncate text-[12.5px] text-ink-dim">{pr.name}</span>
                    <span className="truncate font-mono text-[11px] text-ink-faint">{pr.api_key_env}</span>
                    {pr.doc_url && (
                      <a href={pr.doc_url} target="_blank" rel="noreferrer"
                        aria-label={`Docs for ${pr.name}`}
                        className="shrink-0 text-ink-faint transition-colors hover:text-ink-dim">
                        <ExternalLink size={11} />
                      </a>
                    )}
                  </span>
                  <KeyEditor envName={pr.api_key_env} keySet={pr.key_set} disabled={disabled} />
                </div>
              ))}
            </div>
          )}
        </div>
        <Row label="Browser backend" hint="Page-fetch engine for opening URLs">
          <Select
            value={models.browser_backend}
            disabled={disabled}
            ariaLabel="Browser backend"
            options={BROWSER_BACKENDS.map((b) => ({ value: b, label: b }))}
            onChange={setBrowserBackend}
          />
        </Row>
        {models.browser_backend === "jina" && (
          <Row label="Jina API key"
            hint={models.jina_api_key_set ? undefined : "No key → unauthenticated quota, easy to hit 429"}>
            <KeyEditor envName="JINA_API_KEY" keySet={models.jina_api_key_set} disabled={disabled} />
          </Row>
        )}
        <Row label="Custom proxy" hint="Proxy for outbound fetches, e.g. VPN/clash address (http://host:port). Empty = no proxy.">
          <TextField
            value={advanced.https_proxy}
            onCommit={(v) => setAdvanced({ https_proxy: v })}
            disabled={disabled}
            placeholder="http://127.0.0.1:7890"
          />
        </Row>
        <Row label="Browser cache dir" hint="Per-URL disk cache for fetched pages. Empty = default (~/.cache/searchos).">
          <TextField
            value={advanced.browser_disk_cache_dir}
            onCommit={(v) => setAdvanced({ browser_disk_cache_dir: v })}
            disabled={disabled}
            placeholder="~/.cache/searchos/page_cache"
          />
        </Row>
      </Card>
      <div>
        <h3 className="mb-2 text-[14px] font-medium text-ink">Connection tests</h3>
        <BackendDiagnosticPanel disabled={disabled} />
      </div>
    </SectionShell>
  );
}
