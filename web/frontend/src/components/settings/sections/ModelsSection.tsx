"use client";

import { useSettings } from "@/components/settings/SettingsProvider";
import { OfflineSkeleton, SectionShell, SubSection } from "@/components/settings/primitives";
import NewProfileCard from "@/components/settings/models/NewProfileCard";
import ProfileCard from "@/components/settings/models/ProfileCard";
import ProviderConnections from "@/components/settings/models/ProviderConnections";
import ModelPurposeBindings from "@/components/settings/models/ModelPurposeBindings";
import ProviderDiagnosticPanel from "@/components/settings/diagnostics/ProviderDiagnosticPanel";

export default function ModelsSection() {
  const { settings, status, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";
  const sectionDescription = zh
    ? "连接模型服务，添加模型配置，再按用途分配。多个用途可以共用一份模型配置。"
    : "Connect a provider, add model configurations, then assign them by purpose. Multiple purposes can share a configuration.";

  if (!settings) {
    return (
      <SectionShell id="models" title={zh ? "模型" : "Models"} description={sectionDescription}>
        <OfflineSkeleton />
      </SectionShell>
    );
  }

  const disabled = status !== "ready";

  return (
    <SectionShell id="models" title={zh ? "模型" : "Models"} description={sectionDescription}>
      <div className="space-y-8">
        <SubSection title={zh ? "1 · 连接模型服务" : "1 · Connect providers"}
          description={zh ? "配置服务地址和密钥，供模型配置复用。密钥保存在 .env 中，界面只显示配置状态。" : "Configure reusable endpoints and API keys. Keys stay in .env; only their presence is shown."}>
          <ProviderConnections />
        </SubSection>

        <SubSection title={zh ? "2 · 添加模型配置" : "2 · Add model configurations"}
          description={zh ? "选择模型服务，填写模型标识与参数。同一个模型可以保存不同参数的配置。" : "Select a provider, model ID, and parameters. The same model can have configurations with different parameters."}>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {Object.entries(settings.models.profiles).map(([name, profile]) => (
              <ProfileCard key={name} name={name} profile={profile} disabled={disabled} />
            ))}
            <NewProfileCard disabled={disabled} />
          </div>
        </SubSection>

        <SubSection title={zh ? "3 · 分配模型用途" : "3 · Assign model purposes"}
          description={zh ? "为研究、内容处理和技能功能选择模型。先快速分配，再按需要逐项调整。" : "Choose models for research, content processing, and skills. Start with quick assignment and adjust individual purposes as needed."}>
          <ModelPurposeBindings />
          <ProviderDiagnosticPanel />
        </SubSection>
      </div>
    </SectionShell>
  );
}
