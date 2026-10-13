"use client";

import { useId, useState } from "react";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";

import { putRoles } from "@/lib/api";
import { hasModelPurposeCatalog, modelPurposeGroups, modelBindingIssue, modelConfigurationKey, planModelAllocation, type ModelBindingChange } from "@/lib/modelPurposes";
import { useSettings } from "@/components/settings/SettingsProvider";
import Select from "@/components/settings/controls/Select";

export default function ModelPurposeBindings() {
  const { settings, status, mutate, notify, refresh, uiPrefs } = useSettings();
  const language = uiPrefs.language;
  const zh = language === "zh";
  const id = useId();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [main, setMain] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [vision, setVision] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<{ key: string; changes: ModelBindingChange[] } | null>(null);

  if (!settings) return null;
  const models = settings.models;
  const hasCatalog = hasModelPurposeCatalog(models);
  const groups = modelPurposeGroups(models);
  const purposes = groups.flatMap((group) => group.purposes);
  const profileNames = Object.keys(models.profiles);
  const options = profileNames.map((name) => ({ value: name, label: name }));
  const disabled = busy || status !== "ready";
  const selectedMain = main ?? models.roles.orchestrator ?? "";
  const selectedText = text ?? models.roles.extraction ?? "";
  const selectedVision = vision ?? models.roles.local_vision ?? "";
  const configKey = modelConfigurationKey(models);
  const canAllocate = hasCatalog && [selectedMain, selectedText, selectedVision]
    .every((profile) => Boolean(models.profiles[profile]));
  const previewStale = preview !== null && preview.key !== configKey;
  const issues = purposes.filter((purpose) => modelBindingIssue(models, purpose.role, language));
  const isExpanded = (group: typeof groups[number]) => expanded[group.id]
    ?? (group.id === "research" || group.id === "existing" || group.purposes.some((purpose) => modelBindingIssue(models, purpose.role, language)));
  const allExpanded = groups.every(isExpanded);

  const bind = async (bindings: Record<string, string>) => {
    if (disabled) return;
    setBusy(true);
    const result = await mutate({
      call: () => putRoles(bindings),
      merge: (s, res) => ({ ...s, models: { ...s.models, roles: res.roles, role_overrides: res.role_overrides } }),
      errorLabel: zh ? "无法保存模型分配" : "Couldn't save model assignments",
    });
    setBusy(false);
    if (result) {
      setPreview(null);
      notify(result.warnings.length
        ? (zh ? "分配已保存，部分用途仍缺少密钥，请检查下方提示。" : "Assignments saved. Some purposes still need API keys; check the warnings below.")
        : (zh ? "模型分配已保存" : "Model assignments saved"), result.warnings.length ? "info" : "success");
    }
  };

  const showPreview = () => setPreview({
    key: configKey,
    changes: planModelAllocation(models, { main: selectedMain, text: selectedText, vision: selectedVision }),
  });

  return (
    <div className="space-y-3">
      {!hasCatalog && (
        <div role="status" className="surface space-y-2 rounded-xl px-4 py-3">
          <p className="text-[12px] text-ink-dim">{zh
            ? "后端尚未提供用途说明，下面仍可调整已有绑定。重启后端后，重新加载即可使用完整分组和快速分配。"
            : "The API has not provided purpose details yet. Existing assignments remain editable below. Restart the API, then reload to enable groups and quick assignment."}</p>
          <button type="button" onClick={refresh} disabled={disabled}
            className="rounded-lg border border-line px-3 py-1.5 text-[12px] text-ink hover:border-line-strong disabled:opacity-40">
            {zh ? "重新加载" : "Reload settings"}
          </button>
        </div>
      )}
      {hasCatalog && <details className="surface rounded-xl">
        <summary className="cursor-pointer px-4 py-3 text-[13px] font-medium text-ink">
          {zh ? "快速分配" : "Quick assignment"}
          <span className="ml-2 text-[12px] font-normal text-ink-faint">{zh ? "分别选择通用、文本和视觉模型" : "Choose general, text, and vision models"}</span>
        </summary>
        <div className="space-y-3 px-4 pb-4">
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            {([
              { key: "main", label: zh ? "通用模型" : "General model", value: selectedMain,
                hint: zh ? "规划、检索、核验与技能生成" : "Planning, search, review, and skill creation",
                change: setMain },
              { key: "text", label: zh ? "高频文本模型" : "Text processing model", value: selectedText,
                hint: zh ? "证据提取、摘要与写作" : "Extraction, summaries, and writing",
                change: setText },
              { key: "vision", label: zh ? "视觉模型" : "Vision model", value: selectedVision,
                hint: zh ? "读取图片与扫描件，需支持图片输入" : "Images and scans; image input required",
                change: setVision },
            ]).map((field) => (
              <div key={field.key} className="min-w-0 space-y-1">
                <div className="text-[12px] text-ink">{field.label}</div>
                <Select value={field.value} options={options} ariaLabel={field.label}
                  placeholder={zh ? "选择模型" : "Select a model"}
                  disabled={disabled || !profileNames.length} className="w-full"
                  onChange={(value) => { field.change(value); setPreview(null); }} />
                <p className="text-[11.5px] text-ink-faint">{field.hint}</p>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={showPreview} disabled={disabled || !canAllocate}
              className="rounded-lg border border-line px-3 py-2 text-[12px] text-ink hover:border-line-strong disabled:opacity-40">
              {zh ? "预览分配" : "Preview assignments"}
            </button>
            <p className="text-[11.5px] text-ink-faint">{zh ? "预览确认后才会保存。评测用途保持单独配置。" : "Saved only after reviewing the changes. Evaluation remains separately configured."}</p>
          </div>
          {preview && (
            <div className="space-y-3 border-t border-line pt-3" aria-live="polite">
              <p className="text-[12px] text-ink">{preview.changes.length
                ? (zh ? `将修改 ${preview.changes.length} 项用途绑定` : `${preview.changes.length} assignments will change`)
                : (zh ? "当前绑定与所选分配一致，无需修改。" : "The current assignments already match.")}</p>
              {preview.changes.length > 0 && (
                <ul className="space-y-1 text-[12px] text-ink-dim">
                  {preview.changes.map((change) => (
                    <li key={change.role} className="break-words">
                      {purposes.find((purpose) => purpose.role === change.role)?.label[language] ?? change.role}
                      <span className="ml-2 break-all text-ink-faint">{change.before || (zh ? "未绑定" : "Unassigned")} → {change.after}</span>
                      {modelBindingIssue({ ...models, roles: { ...models.roles, [change.role]: change.after } }, change.role, language) && (
                        <span className="ml-2 text-warn">{zh ? "缺少密钥" : "Missing API key"}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {previewStale && <p role="alert" className="text-[12px] text-warn">{zh ? "模型配置已变化，请重新预览后应用。" : "Model settings changed. Preview the assignments again before applying."}</p>}
              {preview.changes.length > 0 && <button type="button" disabled={disabled || previewStale}
                onClick={() => { if (preview.key === configKey) void bind(Object.fromEntries(preview.changes.map((change) => [change.role, change.after]))); }}
                className="inline-flex items-center gap-2 rounded-lg bg-ink px-3 py-2 text-[12px] text-paper disabled:opacity-40">
                {busy && <Loader2 size={13} className="animate-spin" />}{zh ? "应用分配" : "Apply assignments"}
              </button>}
            </div>
          )}
        </div>
      </details>}

      {issues.length > 0 && <p role="status" className="text-[12px] text-warn">
        {zh ? `${issues.length} 项用途的绑定或密钥需要检查；相关任务可能无法启动。` : `${issues.length} purposes need a model assignment or API key. Related tasks may not start.`}
      </p>}
      {!profileNames.length && <p className="text-[12px] text-ink-faint">{zh ? "请先在上方添加模型配置，再分配用途。" : "Add a model configuration above before assigning purposes."}</p>}
      <div className="flex items-center justify-between gap-3">
        <span className="text-[12.5px] text-ink">{zh ? `全部用途 · ${purposes.length}` : `All purposes · ${purposes.length}`}</span>
        <button type="button" onClick={() => setExpanded(Object.fromEntries(groups.map((group) => [group.id, !allExpanded])))}
          className="rounded px-2 py-1 text-[12px] text-ink-dim hover:bg-surface-2">
          {allExpanded ? (zh ? "收起全部" : "Collapse all") : (zh ? "展开全部" : "Expand all")}
        </button>
      </div>
      {groups.map((group) => {
        const open = isExpanded(group);
        const issueCount = group.purposes.filter((purpose) => modelBindingIssue(models, purpose.role, language)).length;
        return (
          <div key={group.id} className="surface rounded-xl">
            <button type="button" aria-expanded={open} aria-controls={`${id}-${group.id}`}
              onClick={() => setExpanded((previous) => ({ ...previous, [group.id]: !open }))}
              className="flex w-full items-center gap-2 rounded-xl px-4 py-3 text-left text-[13px] text-ink hover:bg-surface-2">
              {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <span className="font-medium">{group.label[language]}</span>
              <span className="text-[12px] text-ink-faint">{group.purposes.length}</span>
              {issueCount > 0 && <span className="ml-auto text-[11.5px] text-warn">{zh ? `${issueCount} 项待检查` : `${issueCount} need attention`}</span>}
            </button>
            <div id={`${id}-${group.id}`} hidden={!open} className="divide-y divide-line border-t border-line">
              {group.purposes.map((purpose) => {
                const profile = models.roles[purpose.role] ?? "";
                const issue = modelBindingIssue(models, purpose.role, language);
                return (
                  <div key={purpose.role} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                        <span className="text-[13px] text-ink">{purpose.label[language]}</span>
                        {hasCatalog && <code className="text-[11px] text-ink-faint">{purpose.role}</code>}
                      </div>
                      {purpose.description[language] && <p className="mt-1 text-[12px] text-ink-dim">{purpose.description[language]}</p>}
                      {purpose.guidance[language] && <p className="mt-1 text-[11.5px] text-ink-faint">{purpose.guidance[language]}</p>}
                      {issue && <p className="mt-1 break-all text-[12px] text-warn">{issue}</p>}
                    </div>
                    <div className="min-w-0 space-y-1 sm:w-48 sm:shrink-0">
                      <Select value={profile} disabled={disabled || !profileNames.length} className="w-full"
                        ariaLabel={zh ? `${purpose.label.zh}使用的模型` : `Model for ${purpose.label.en}`}
                        options={models.profiles[profile] ? options : [{ value: profile, label: profile || (zh ? "选择模型" : "Select a model"), disabled: true }, ...options]}
                        onChange={(value) => { void bind({ [purpose.role]: value }); }} />
                      <p className="text-[11px] text-ink-faint sm:text-right">{issue ? (zh ? "配置待完善" : "Configuration incomplete")
                        : (zh ? "已绑定" : "Assigned")}{!issue && (models.role_overrides[purpose.role] ? (zh ? " · 已自定义" : " · Custom") : (zh ? " · 默认配置" : " · Default"))}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
