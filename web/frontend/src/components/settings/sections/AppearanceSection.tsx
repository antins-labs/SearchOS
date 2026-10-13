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
  const zh = uiPrefs.language === "zh";
  const { theme, setTheme } = useTheme();
  // Hydration guard — theme is unknown until the client render.
  const mounted = useSyncExternalStore(emptySubscribe, () => true, () => false);

  return (
    <SectionShell id="appearance" title={zh ? "外观" : "Appearance"}
      description={zh ? "偏好保存在当前浏览器中，离线时也可使用。" : "Local preferences are stored in this browser and work offline."}>
      <Card>
        <Row label={zh ? "界面语言" : "Interface language"}>
          <PillGroup
            ariaLabel="Interface language"
            value={uiPrefs.language}
            options={[{ value: "zh", label: "中文" }, { value: "en", label: "English" }]}
            onChange={(language) => setUiPrefs({ language: language as "zh" | "en" })}
          />
        </Row>
        <Row label={zh ? "主题" : "Theme"}>
          {mounted ? (
            <PillGroup
              ariaLabel={zh ? "主题" : "Theme"}
              value={theme === "dark" ? "dark" : "light"}
              options={zh
                ? [{ value: "light", label: "浅色" }, { value: "dark", label: "深色" }]
                : [{ value: "light", label: "Light" }, { value: "dark", label: "Dark" }]}
              onChange={setTheme}
            />
          ) : (
            <div className="h-7 w-28 animate-pulse rounded-lg bg-surface-2" />
          )}
        </Row>
        <Row label={zh ? "详细运行卡片" : "Detailed cards"}
          hint={zh ? "默认显示完整的编排过程" : "Show verbose orchestration detail by default"}>
          <Toggle checked={uiPrefs.verboseCards} label={zh ? "详细运行卡片" : "Detailed cards"}
            onChange={(v) => setUiPrefs({ verboseCards: v })} />
        </Row>
      </Card>
    </SectionShell>
  );
}
