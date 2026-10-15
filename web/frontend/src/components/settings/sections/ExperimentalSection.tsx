"use client";

import { putAdvanced, putMisc } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";
import { Card, OfflineSkeleton, Row, SectionShell } from "@/components/settings/primitives";
import NumberField from "@/components/settings/controls/NumberField";
import Toggle from "@/components/settings/controls/Toggle";

export default function ExperimentalSection() {
  const { settings, status, mutate, refresh, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";

  if (!settings) {
    return (
      <SectionShell id="experimental" title={zh ? "研究策略" : "Research behavior"}
        description={zh ? "调整新任务使用的高级研究行为。" : "Adjust advanced research behavior for new runs."}>
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
    }).then((view) => { if (view) refresh(); });

  const setCoverageStallRounds = (rounds: number) =>
    mutate({
      optimistic: (s) => ({
        ...s,
        advanced: { ...s.advanced, orch_coverage_stall_rounds: rounds },
      }),
      call: () => putAdvanced({ orch_coverage_stall_rounds: rounds }),
      merge: (s, view) => ({ ...s, advanced: view }),
      errorLabel: "Couldn't update coverage stall rounds",
    });

  return (
    <SectionShell id="experimental" title={zh ? "研究策略" : "Research behavior"}
      description={zh ? "调整新任务使用的高级研究行为。" : "Adjust advanced research behavior for new runs."}>
      <div>
        <h3 className="mb-2 text-[14px] font-medium text-ink">{zh ? "高级行为" : "Advanced behavior"}</h3>
        <Card>
          <Row
            label={zh ? "并行探索" : "Parallel exploration"}
            hint={zh ? "开启后并行执行宽召回探索；关闭后依次执行检索、打开和查找。" : "Run broad-recall exploration concurrently. When off, search, open, and find run serially."}
          >
            <Toggle
              checked={run_defaults.enable_explore_batch}
              onChange={setExploreBatch}
              disabled={disabled}
              label={zh ? "启用并行探索" : "Enable parallel exploration"}
            />
          </Row>
          <Row
            label={zh ? "折叠已完成的检索过程" : "Fold completed search episodes"}
            hint={zh ? "控制默认网页检索组合的历史折叠；自定义 Middleware 组合以装配页的选择为准。" : "Control history folding in the default web search pipeline; custom middleware selections take precedence."}
          >
            <Toggle
              checked={advanced.use_layered_context}
              onChange={setEpisodeFolding}
              disabled={disabled}
              label={zh ? "折叠已完成的检索过程" : "Fold completed search episodes"}
            />
          </Row>
          <Row
            label={zh ? "连续无进展轮数" : "No-progress rounds"}
            hint={zh ? "连续若干轮没有新阅读、有效事实、任务关联或表格变化时进入收尾。设为 0 可关闭该判断。" : "Finalize after this many rounds add no reading, facts, task bindings, or table changes. Set 0 to disable."}
          >
            <NumberField
              value={advanced.orch_coverage_stall_rounds}
              min={0}
              max={100}
              onCommit={setCoverageStallRounds}
              disabled={disabled}
            />
          </Row>
        </Card>
      </div>
    </SectionShell>
  );
}
