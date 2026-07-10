"use client";

import { putRoles } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";
import { Card, OfflineSkeleton, Row, SectionShell, SubSection } from "@/components/settings/primitives";
import Select from "@/components/settings/controls/Select";
import NewProfileCard from "@/components/settings/models/NewProfileCard";
import ProfileCard from "@/components/settings/models/ProfileCard";
import ProviderConnections from "@/components/settings/models/ProviderConnections";
import ProviderDiagnosticPanel from "@/components/settings/diagnostics/ProviderDiagnosticPanel";

const SECTION_DESC =
  "Providers, model cards, and role bindings. API keys are stored in .env and never shown.";

export default function ModelsSection() {
  const { settings, status, mutate } = useSettings();

  if (!settings) {
    return (
      <SectionShell id="models" title="Models" description={SECTION_DESC}>
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

  return (
    <SectionShell id="models" title="Models" description={SECTION_DESC}>
      <div className="space-y-8">
        <SubSection title="Providers"
          description="Define your provider connections — an endpoint plus one or more API keys. Vendor presets pre-fill a new connection; model cards below point at these by name and inherit protocol / endpoint / key.">
          <ProviderConnections />
          <ProviderDiagnosticPanel />
        </SubSection>

        <SubSection title="Models"
          description="Each model card points at a provider connection above and sets a model id + sampling (temperature, thinking). Roles pick from these.">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {Object.entries(models.profiles).map(([name, p]) => (
              <ProfileCard key={name} name={name} profile={p} disabled={disabled} />
            ))}
            <NewProfileCard disabled={disabled} />
          </div>
        </SubSection>

        <SubSection title="Roles" description="Bind each agent role to a model.">
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
        </SubSection>
      </div>
    </SectionShell>
  );
}
