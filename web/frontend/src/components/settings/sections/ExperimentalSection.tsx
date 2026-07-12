"use client";

import { putAdvanced, putMisc } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";
import { Card, OfflineSkeleton, Row, SectionShell } from "@/components/settings/primitives";
import Toggle from "@/components/settings/controls/Toggle";

export default function ExperimentalSection() {
  const { settings, status, mutate } = useSettings();

  if (!settings) {
    return (
      <SectionShell id="experimental" title="Experimental"
        description="Try evolving research behaviors. These settings apply to new runs.">
        <OfflineSkeleton />
      </SectionShell>
    );
  }

  const disabled = status !== "ready";
  const { advanced, run_defaults } = settings;

  const setExploreBatch = (enabled: boolean) =>
    mutate({
      optimistic: (s) => ({
        ...s,
        run_defaults: { ...s.run_defaults, enable_explore_batch: enabled },
      }),
      call: () => putMisc({ enable_explore_batch: enabled }),
      merge: (s, view) => ({
        ...s,
        run_defaults: {
          ...s.run_defaults,
          enable_explore_batch: view.enable_explore_batch,
        },
      }),
      errorLabel: "Couldn't switch Explore mode",
    });

  const setEpisodeFolding = (enabled: boolean) =>
    mutate({
      optimistic: (s) => ({
        ...s,
        advanced: { ...s.advanced, use_layered_context: enabled },
      }),
      call: () => putAdvanced({ use_layered_context: enabled }),
      merge: (s, view) => ({ ...s, advanced: view }),
      errorLabel: "Couldn't switch episode folding",
    });

  return (
    <SectionShell id="experimental" title="Experimental"
      description="Try evolving research behaviors. These settings apply to new runs.">
      <Card>
        <Row
          label="Parallel Explore waves"
          hint="On: concurrent broad-recall waves. Off: legacy serial search/open/find."
        >
          <Toggle
            checked={run_defaults.enable_explore_batch}
            onChange={setExploreBatch}
            disabled={disabled}
            label="Enable parallel Explore waves"
          />
        </Row>
        <Row
          label="Fold completed search episodes"
          hint="Keep prior tool inputs and SOCM progress, but remove prior tool outputs from model context."
        >
          <Toggle
            checked={advanced.use_layered_context}
            onChange={setEpisodeFolding}
            disabled={disabled}
            label="Fold completed search episodes"
          />
        </Row>
      </Card>
    </SectionShell>
  );
}
