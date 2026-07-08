"use client";

import { putMisc, putRoles, putSearchBackend } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";
import { Card, OfflineSkeleton, Row, SectionShell } from "@/components/settings/primitives";
import Select from "@/components/settings/controls/Select";

const BROWSER_BACKENDS = ["jina", "aiohttp", "crawl4ai", "search_engine"];

export default function ModelsSection() {
  const { settings, status, mutate } = useSettings();

  if (!settings) {
    return (
      <SectionShell id="models" title="Models"
        description="Role bindings, provider profiles, and the search backend.">
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
      description="Role bindings, provider profiles, and the search backend. API keys stay in .env.">
      {models.active_provider_preset && (
        <p className="text-[12.5px] text-ink-faint">
          Provider preset: <span className="font-mono text-ink-dim">{models.active_provider_preset}</span>
        </p>
      )}

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
      </Card>
    </SectionShell>
  );
}
