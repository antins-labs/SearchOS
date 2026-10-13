import type { ModelPurposeGroup, ModelsView } from "./types";

export function hasModelPurposeCatalog(models: ModelsView): boolean {
  return Array.isArray(models.purpose_groups) && models.purpose_groups.length > 0;
}

/** Keep existing assignments editable while an older API is still running. */
export function modelPurposeGroups(models: ModelsView): ModelPurposeGroup[] {
  if (hasModelPurposeCatalog(models)) return models.purpose_groups!;
  return [{
    id: "existing",
    label: { zh: "已有用途", en: "Existing purposes" },
    purposes: Object.keys(models.roles).filter((role) => role !== "skill_runtime").map((role) => ({
      role,
      label: { zh: role, en: role },
      description: { zh: "", en: "" },
      guidance: { zh: "", en: "" },
      allocation: null,
    })),
  }];
}

export interface ModelAllocation {
  main: string;
  text: string;
  vision: string;
}

export interface ModelBindingChange {
  role: string;
  before: string;
  after: string;
}

export function planModelAllocation(models: ModelsView, selection: ModelAllocation): ModelBindingChange[] {
  if ([selection.main, selection.text, selection.vision].some((profile) => !models.profiles[profile])) return [];
  return modelPurposeGroups(models).flatMap((group) => group.purposes).flatMap((purpose) => {
    const after = purpose.allocation === "main" ? selection.main
      : purpose.allocation === "text" ? selection.text
        : purpose.allocation === "vision" ? selection.vision : "";
    const before = models.roles[purpose.role] ?? "";
    return after && models.profiles[after] && after !== before
      ? [{ role: purpose.role, before, after }]
      : [];
  });
}

/** A preview is valid only for the bindings and model configurations it displayed. */
export function modelConfigurationKey(models: ModelsView): string {
  return JSON.stringify([models.roles, models.profiles, models.purpose_groups]);
}

export function modelBindingIssue(models: ModelsView, role: string, language: "zh" | "en"): string | null {
  const profileName = models.roles[role];
  if (!profileName) return language === "zh" ? "尚未绑定模型" : "No model assigned";
  const profile = models.profiles[profileName];
  if (!profile) return language === "zh" ? `模型配置 ${profileName} 不存在` : `Model configuration ${profileName} is missing`;
  if (!profile.api_key_set) return language === "zh" ? `缺少密钥：${profile.api_key_env}` : `Missing key: ${profile.api_key_env}`;
  return null;
}
