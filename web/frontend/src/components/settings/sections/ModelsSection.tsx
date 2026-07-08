"use client";

import { useState } from "react";
import { ChevronRight, ExternalLink } from "lucide-react";

import { putMisc, putRoles, putSearchBackend } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";
import { Card, OfflineSkeleton, Row, SectionShell } from "@/components/settings/primitives";
import Select from "@/components/settings/controls/Select";
import KeyEditor from "@/components/settings/models/KeyEditor";
import ProviderConnection from "@/components/settings/models/ProviderConnection";

const BROWSER_BACKENDS = ["jina", "aiohttp", "crawl4ai", "search_engine"];

export default function ModelsSection() {
  const { settings, status, mutate } = useSettings();
  const [searchKeysOpen, setSearchKeysOpen] = useState(false);

  if (!settings) {
    return (
      <SectionShell id="models" title="Models"
        description="Provider connection, role bindings, and search backends. Keys are stored in .env and never shown.">
        <OfflineSkeleton />
      </SectionShell>
    );
  }

  const { models } = settings;
  const disabled = status !== "ready";
  const profileNames = Object.keys(models.profiles);

  const bindRole = (role: string, profile: string) =>
    mutate({
      optimistic: (s) => ({
        ...s,
        models: { ...s.models, roles: { ...s.models.roles, [role]: profile } },
      }),
      call: () => putRoles({ [role]: profile }),
      merge: (s, res) => ({
        ...s,
        models: { ...s.models, roles: res.roles, role_overrides: res.role_overrides },
      }),
      errorLabel: "Couldn't bind role",
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
    <SectionShell id="models" title="Models"
      description="Provider connection, role bindings, and search backends. Keys are stored in .env and never shown.">
      <ProviderConnection />

      <Card>
        {Object.entries(models.roles).map(([role, profile]) => {
          const keyMissing = models.profiles[profile] && !models.profiles[profile].api_key_set;
          return (
            <Row key={role} label={role}
              hint={keyMissing ? `${models.profiles[profile].api_key_env} not set — runs will fail` : undefined}>
              <Select
                value={profile}
                disabled={disabled}
                ariaLabel={`Model profile for ${role}`}
                options={profileNames.map((n) => ({ value: n, label: n }))}
                onChange={(v) => bindRole(role, v)}
              />
            </Row>
          );
        })}
      </Card>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {Object.entries(models.profiles).map(([name, p]) => (
          <div key={name} className="surface rounded-xl px-3.5 py-3">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-mono text-[12.5px] text-ink">{name}</span>
              <span className={`flex shrink-0 items-center gap-1.5 text-[11px] ${p.api_key_set ? "text-ok" : "text-warn"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${p.api_key_set ? "bg-ok" : "bg-warn"}`} />
                {p.api_key_set ? "Key configured" : "No API key"}
              </span>
            </div>
            <div className="mt-1.5 space-y-0.5 text-[11.5px] text-ink-faint">
              <div className="truncate">model: <span className="text-ink-dim">{p.model}</span></div>
              <div className="truncate">provider: {p.provider}</div>
              {p.api_base && <div className="truncate">base: {p.api_base}</div>}
            </div>
            {!p.api_key_set && (
              <KeyEditor envName={p.api_key_env} keySet={false} disabled={disabled} compact />
            )}
          </div>
        ))}
      </div>

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
        <Row label="Browser backend" hint="Page-fetch engine for opening URLs">
          <Select
            value={models.browser_backend}
            disabled={disabled}
            ariaLabel="Browser backend"
            options={BROWSER_BACKENDS.map((b) => ({ value: b, label: b }))}
            onChange={setBrowserBackend}
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
      </Card>
    </SectionShell>
  );
}
