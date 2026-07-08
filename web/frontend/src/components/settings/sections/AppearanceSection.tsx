"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";

import { useSettings } from "@/components/settings/SettingsProvider";
import { Card, Row, SectionShell } from "@/components/settings/primitives";
import PillGroup from "@/components/settings/controls/PillGroup";
import Toggle from "@/components/settings/controls/Toggle";

const emptySubscribe = () => () => {};

export default function AppearanceSection() {
  const { uiPrefs, setUiPrefs } = useSettings();
  const { theme, setTheme } = useTheme();
  // Hydration guard — theme is unknown until the client render.
  const mounted = useSyncExternalStore(emptySubscribe, () => true, () => false);

  return (
    <SectionShell id="appearance" title="Appearance"
      description="Local preferences — stored in this browser, works offline.">
      <Card>
        <Row label="Theme">
          {mounted ? (
            <PillGroup
              value={theme === "dark" ? "dark" : "light"}
              options={[{ value: "light", label: "Light" }, { value: "dark", label: "Dark" }]}
              onChange={setTheme}
            />
          ) : (
            <div className="h-7 w-28 animate-pulse rounded-lg bg-surface-2" />
          )}
        </Row>
        <Row label="Detailed cards" hint="Show verbose orchestration detail by default">
          <Toggle checked={uiPrefs.verboseCards}
            onChange={(v) => setUiPrefs({ verboseCards: v })} />
        </Row>
      </Card>
    </SectionShell>
  );
}
