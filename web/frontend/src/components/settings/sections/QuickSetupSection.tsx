"use client";

import {
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  FileText,
  Globe2,
  SearchCheck,
  Sparkles,
} from "lucide-react";

import { putEffort } from "@/lib/api";
import type { EffortLevel, ModelsView } from "@/lib/types";
import type { SectionId } from "@/components/settings/SectionNav";
import { useSettings } from "@/components/settings/SettingsProvider";
import { OfflineSkeleton, SectionShell } from "@/components/settings/primitives";

interface Props {
  onNavigate: (id: SectionId) => void;
}

const PRESETS: Array<{
  level: EffortLevel;
  zhLabel: string;
  enLabel: string;
  zhDescription: string;
  enDescription: string;
  recommended?: boolean;
}> = [
  { level: "low", zhLabel: "轻度", enLabel: "Low", zhDescription: "适合事实查证、短文档和简单列表" , enDescription: "Facts, short documents, and small lists" },
  { level: "medium", zhLabel: "中度", enLabel: "Medium", zhDescription: "适合比较、资料整理和普通问答", enDescription: "Comparisons, synthesis, and everyday research", recommended: true },
  { level: "high", zhLabel: "高度", enLabel: "High", zhDescription: "适合多步问题、较多来源和较长文档", enDescription: "Multi-step questions, more sources, and longer documents" },
  { level: "max", zhLabel: "极高", enLabel: "Max", zhDescription: "适合大型表格、困难来源和高召回任务", enDescription: "Large tables, difficult sources, and maximum recall" },
];

function roleReady(models: ModelsView, role: string): boolean {
  const profileName = models.roles[role];
  if (!profileName) return false;
  return Boolean(models.profiles[profileName]?.api_key_set);
}

function searchReady(models: ModelsView): boolean {
  const provider = models.search.providers.find((item) => item.name === models.search.resolved);
  return models.search.resolved === "ragflow" || Boolean(provider?.key_set);
}

function StatusItem({
  ready,
  label,
  detail,
  action,
  onClick,
}: {
  ready: boolean;
  label: string;
  detail: string;
  action: string;
  onClick: () => void;
}) {
  const Icon = ready ? CheckCircle2 : CircleAlert;
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-2"
    >
      <Icon className={ready ? "text-ok" : "text-warn"} size={18} />
      <span className="min-w-0 flex-1">
        <span className="block text-[13.5px] text-ink">{label}</span>
        <span className="mt-0.5 block text-[12px] leading-relaxed text-ink-faint">{detail}</span>
      </span>
      <span className="flex shrink-0 items-center gap-0.5 text-[11.5px] text-accent-ink">
        {action}<ChevronRight size={13} />
      </span>
    </button>
  );
}

export default function QuickSetupSection({ onNavigate }: Props) {
  const { settings, status, mutate, notify, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";

  if (!settings) {
    return (
      <SectionShell id="setup" title={zh ? "快速配置" : "Quick setup"}
        description={zh ? "选择使用方式，SearchOS 会检查必需配置。" : "Choose a workflow and SearchOS will check its requirements."}>
        <OfflineSkeleton />
      </SectionShell>
    );
  }

  const { models, effort } = settings;
  const answerReady = ["orchestrator", "sub_agent", "synthesis"].every((role) => roleReady(models, role));
  const localReady = roleReady(models, "sub_agent");
  const webReady = searchReady(models);
  const browserReady = models.browser_backend !== "jina" || models.jina_api_key_set;
  const disabled = status !== "ready";

  const selectPreset = async (level: EffortLevel) => {
    const result = await mutate({
      optimistic: (current) => ({
        ...current,
        effort: {
          ...current.effort,
          level,
          knobs: { ...current.effort.levels[level] },
          overrides: {},
        },
      }),
      call: () => putEffort(level),
      merge: (current, view) => ({ ...current, effort: view }),
      errorLabel: zh ? "无法保存研究档位" : "Couldn't save effort level",
    });
    const preset = PRESETS.find((item) => item.level === level);
    if (result && preset) notify(
      zh ? `已切换为“${preset.zhLabel}”` : `Effort set to ${preset.enLabel}`,
      "success",
    );
  };

  return (
    <SectionShell
      id="setup"
      title={zh ? "快速配置" : "Quick setup"}
      description={zh
        ? "先完成模型和联网检查，再选择研究档位；高级参数可保持默认值。"
        : "Check models and web access, then choose an effort level. Advanced defaults usually work well."}
    >
      <div className="grid gap-2 sm:grid-cols-3">
        <div className="surface rounded-xl p-3.5">
          <div className="flex items-center gap-2 text-[13.5px] font-medium text-ink">
            <Globe2 size={16} className="text-accent-ink" /> Web
          </div>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-faint">{zh ? "只使用网络搜索与网页内容。" : "Uses web search and web pages only."}</p>
        </div>
        <div className="surface rounded-xl p-3.5">
          <div className="flex items-center gap-2 text-[13.5px] font-medium text-ink">
            <FileText size={16} className="text-accent-ink" /> Local
          </div>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-faint">{zh ? "只阅读本次选中的本地文档。" : "Reads only the local documents selected for this run."}</p>
        </div>
        <div className="surface rounded-xl p-3.5">
          <div className="flex items-center gap-2 text-[13.5px] font-medium text-ink">
            <Sparkles size={16} className="text-accent-ink" /> Hybrid
          </div>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-faint">{zh ? "由系统编排本地阅读与联网检索。" : "Orchestrates local reading and web research."}</p>
        </div>
      </div>

      <div className="surface divide-y divide-line rounded-xl">
        <StatusItem
          ready={answerReady}
          label={zh ? "回答模型" : "Answer models"}
          detail={answerReady
            ? (zh ? "研究规划、资料阅读和最终写作模型均可用。" : "Planning, reading, and final-answer models are ready.")
            : (zh ? "至少一个核心角色缺少可用的模型密钥。" : "At least one core role is missing a usable model key.")}
          action={answerReady ? (zh ? "查看" : "View") : (zh ? "去配置" : "Configure")}
          onClick={() => onNavigate("models")}
        />
        <StatusItem
          ready={webReady}
          label={zh ? "联网搜索" : "Web search"}
          detail={webReady
            ? (zh ? `当前使用 ${models.search.resolved}，Web 与 Hybrid 可联网。` : `${models.search.resolved} is ready for Web and Hybrid.`)
            : (zh ? "当前搜索服务缺少 API Key，Web 与 Hybrid 无法正常检索。" : "The search provider is missing an API key required by Web and Hybrid.")}
          action={webReady ? (zh ? "查看" : "View") : (zh ? "去配置" : "Configure")}
          onClick={() => onNavigate("search")}
        />
        <StatusItem
          ready={browserReady}
          label={zh ? "网页读取" : "Page reader"}
          detail={browserReady
            ? (zh ? `当前使用 ${models.browser_backend}。` : `${models.browser_backend} is active.`)
            : (zh ? "Jina 未配置 API Key，可试用匿名额度，但容易受到限流。" : "Jina has no API key. Anonymous quota may be rate limited.")}
          action={browserReady ? (zh ? "查看" : "View") : (zh ? "建议配置" : "Configure")}
          onClick={() => onNavigate("search")}
        />
        <StatusItem
          ready={localReady}
          label={zh ? "本地文档问答" : "Local document Q&A"}
          detail={localReady
            ? (zh ? "Local 可检索当前知识库或限定到选中文档；Hybrid 可按任务组合本地与网络来源。" : "Local can search the current library or stay within selected documents; Hybrid can combine local and web sources.")
            : (zh ? "本地阅读角色缺少可用模型。" : "The local reading role is missing a usable model.")}
          action={localReady ? (zh ? "查看" : "View") : (zh ? "去配置" : "Configure")}
          onClick={() => onNavigate("models")}
        />
      </div>

      <div>
        <div className="mb-2 flex items-end justify-between gap-4">
          <div>
            <h3 className="text-[14px] font-medium text-ink">{zh ? "研究档位" : "Effort level"}</h3>
            <p className="mt-0.5 text-[12px] text-ink-faint">{zh ? "档位会一起调整运行时间、并发数量和工具调用预算。" : "Each level adjusts time, concurrency, and tool-call budgets together."}</p>
          </div>
          <button type="button" onClick={() => onNavigate("budget")}
            className="shrink-0 text-[11.5px] text-accent-ink hover:underline">
            {zh ? "高级设置" : "Advanced settings"}
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset.level}
              type="button"
              disabled={disabled}
              aria-pressed={effort.level === preset.level}
              onClick={() => selectPreset(preset.level)}
              className={`rounded-xl border px-3.5 py-3 text-left transition-colors disabled:opacity-40 ${
                effort.level === preset.level
                  ? "border-accent bg-clay/40"
                  : "border-line bg-surface hover:border-line-strong"
              }`}
            >
              <span className="flex items-center gap-1.5 text-[13.5px] font-medium text-ink">
                {zh ? preset.zhLabel : preset.enLabel}
                {preset.recommended && (
                  <span className="rounded bg-clay px-1.5 py-0.5 text-[9.5px] font-normal text-accent-ink">{zh ? "推荐" : "Recommended"}</span>
                )}
                {effort.level === preset.level && <SearchCheck size={14} className="ml-auto text-ok" />}
              </span>
              <span className="mt-1 block text-[11.5px] leading-relaxed text-ink-faint">{zh ? preset.zhDescription : preset.enDescription}</span>
            </button>
          ))}
        </div>
      </div>

      <p className="rounded-lg bg-surface-2 px-3 py-2.5 text-[11.5px] leading-relaxed text-ink-faint">
        {zh
          ? "Local 和 Hybrid 会把与问题相关的选中文档片段发送给当前模型，用于生成回答；未选中的文档不会加入本次问答。"
          : "Local can retrieve relevant excerpts from the current library or selected documents. Hybrid uses only explicitly selected local documents."}
      </p>
    </SectionShell>
  );
}
