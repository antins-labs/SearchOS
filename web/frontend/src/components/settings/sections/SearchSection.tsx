"use client";

import { useState } from "react";
import { ChevronRight, ExternalLink, Loader2 } from "lucide-react";

import { detectWebImageCapability, putAdvanced, putMisc, putSearchBackend } from "@/lib/api";
import { useSettings } from "@/components/settings/SettingsProvider";
import { Card, OfflineSkeleton, Row, SectionShell } from "@/components/settings/primitives";
import Select from "@/components/settings/controls/Select";
import TextField from "@/components/settings/controls/TextField";
import KeyEditor from "@/components/settings/models/KeyEditor";
import BackendDiagnosticPanel from "@/components/settings/diagnostics/BackendDiagnosticPanel";
import Toggle from "@/components/settings/controls/Toggle";

const BROWSER_BACKENDS = ["jina", "aiohttp", "crawl4ai", "search_engine"];

export default function SearchSection() {
  const { settings, status, mutate, uiPrefs } = useSettings();
  const zh = uiPrefs.language === "zh";
  const [searchKeysOpen, setSearchKeysOpen] = useState(false);
  const [detectingImage, setDetectingImage] = useState(false);

  if (!settings) {
    return (
      <SectionShell id="search" title={zh ? "联网与读取" : "Search & browse"}
        description={zh ? "配置联网检索与网页读取服务。密钥保存在 .env 中，界面不会显示原文。" : "Configure web search and page reading. Provider keys are stored in .env and never shown."}>
        <OfflineSkeleton />
      </SectionShell>
    );
  }

  const { models, advanced, run_defaults: runDefaults } = settings;
  const disabled = status !== "ready";

  const setAdvanced = (patch: {
    https_proxy?: string;
    browser_disk_cache_dir?: string;
  }) =>
    mutate({
      optimistic: (s) => ({ ...s, advanced: { ...s.advanced, ...patch } }),
      call: () => putAdvanced(patch),
      merge: (s, view) => ({ ...s, advanced: view }),
      errorLabel: "Couldn't save setting",
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

  const setImageReading = (patch: Parameters<typeof putMisc>[0]) =>
    mutate({
      optimistic: (s) => ({ ...s, run_defaults: { ...s.run_defaults, ...patch } }),
      call: () => putMisc(patch),
      merge: (s, view) => ({ ...s, run_defaults: view }),
      errorLabel: "Couldn't save image-reading setting",
    });

  const detectImageInput = async () => {
    if (detectingImage) return;
    setDetectingImage(true);
    try {
      await mutate({
        call: detectWebImageCapability,
        merge: (s, view) => ({ ...s, run_defaults: view }),
        errorLabel: "Couldn't detect image input",
      });
    } finally {
      setDetectingImage(false);
    }
  };

  const capability = runDefaults.web_image_capability;
  const capabilityLabel = capability.status === "supported"
    ? (zh ? "支持原生图片输入" : "Native image input supported")
    : capability.status === "unsupported"
      ? (zh ? "不支持；自动模式将使用视觉模型" : "Unsupported; auto uses the vision model")
      : (zh ? "尚未检测" : "Not detected");

  return (
    <SectionShell id="search" title={zh ? "联网与读取" : "Search & browse"}
      description={zh ? "配置联网检索与网页读取服务。密钥保存在 .env 中，界面不会显示原文。" : "Configure web search and page reading. Provider keys are stored in .env and never shown."}>
      <Card>
        <Row label={zh ? "检索服务" : "Search provider"}
          hint={models.search.configured ? undefined : (zh ? `自动选择为 ${models.search.resolved}` : `Automatically resolved to ${models.search.resolved}`)}>
          <Select
            value={models.search.configured ?? "auto"}
            disabled={disabled}
            ariaLabel={zh ? "检索服务" : "Search provider"}
            options={[
              { value: "auto", label: `${zh ? "自动" : "Auto"} (${models.search.resolved})` },
              ...models.search.providers.map((pr) => ({
                value: pr.name,
                label: pr.key_set || pr.name === "ragflow" ? pr.name : `${pr.name} (${zh ? "未配置密钥" : "no key"})`,
                disabled: !pr.key_set && pr.name !== "ragflow",
              })),
            ]}
            onChange={setSearchBackend}
          />
        </Row>
        <div className="px-4 py-2.5">
          <button
            type="button"
            onClick={() => setSearchKeysOpen((v) => !v)}
            className="flex items-center gap-1 text-[12.5px] text-ink-faint transition-colors hover:text-ink-dim"
          >
            <ChevronRight size={13}
              className={`transition-transform duration-200 ${searchKeysOpen ? "rotate-90" : ""}`} />
            {zh ? "检索服务密钥" : "Search provider keys"}
          </button>
          {searchKeysOpen && (
            <div className="rise-in mt-2 space-y-2">
              {models.search.providers.map((pr) => (
                <div key={pr.name} className="flex items-center justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${pr.key_set ? "bg-ok" : "bg-line-strong"}`} />
                    <span className="truncate text-[12.5px] text-ink-dim">{pr.name}</span>
                    <span className="truncate font-mono text-[11px] text-ink-faint">{pr.api_key_env}</span>
                    {pr.doc_url && (
                      <a href={pr.doc_url} target="_blank" rel="noreferrer"
                        aria-label={zh ? `${pr.name} 文档` : `Docs for ${pr.name}`}
                        className="shrink-0 text-ink-faint transition-colors hover:text-ink-dim">
                        <ExternalLink size={11} />
                      </a>
                    )}
                  </span>
                  <KeyEditor envName={pr.api_key_env} keySet={pr.key_set} disabled={disabled} />
                </div>
              ))}
            </div>
          )}
        </div>
        <Row label={zh ? "网页读取服务" : "Page reader"} hint={zh ? "用于打开链接并读取网页正文" : "Fetches and reads content from URLs"}>
          <Select
            value={models.browser_backend}
            disabled={disabled}
            ariaLabel={zh ? "网页读取服务" : "Page reader"}
            options={BROWSER_BACKENDS.map((b) => ({ value: b, label: b }))}
            onChange={setBrowserBackend}
          />
        </Row>
        {models.browser_backend === "jina" && (
          <Row label={zh ? "Jina 密钥" : "Jina API key"}
            hint={models.jina_api_key_set ? undefined : (zh ? "未配置密钥时使用匿名额度，容易受到限流" : "Without a key, anonymous quota may be rate limited")}>
            <KeyEditor envName="JINA_API_KEY" keySet={models.jina_api_key_set} disabled={disabled} />
          </Row>
        )}
        <Row label={zh ? "启用图片阅读" : "Enable image reading"}
          hint={zh ? "为 Web Search Agent 注册 view；关闭时保持原文本工具与提示词。" : "Registers view for Web Search Agent; off preserves the text-only tools and prompt."}>
          <Toggle checked={runDefaults.enable_web_image_read} disabled={disabled}
            label={zh ? "启用图片阅读" : "Enable image reading"}
            onChange={(enabled) => setImageReading({ enable_web_image_read: enabled })} />
        </Row>
        {runDefaults.enable_web_image_read && (
          <>
            <Row label={zh ? "图片读取方式" : "Image reading mode"}
              hint={zh ? `Search Agent：${runDefaults.web_image_agent_model}；视觉模型：${runDefaults.web_image_vision_model}` : `Search Agent: ${runDefaults.web_image_agent_model}; vision model: ${runDefaults.web_image_vision_model}`}>
              <Select value={runDefaults.web_image_read_mode} disabled={disabled}
                ariaLabel={zh ? "图片读取方式" : "Image reading mode"}
                options={[
                  { value: "auto", label: zh ? "自动选择" : "Auto" },
                  { value: "native", label: zh ? "主模型直接读图" : "Native" },
                  { value: "vision", label: zh ? "使用视觉模型" : "Vision model" },
                ]}
                onChange={(mode) => setImageReading({ web_image_read_mode: mode as "auto" | "native" | "vision" })} />
            </Row>
            {models.browser_backend === "jina" && (
              <Row label={zh ? "Jina 图片链接" : "Jina image links"}
                hint={zh ? `本次有效值：${runDefaults.effective_jina_retain_images}` : `Effective value: ${runDefaults.effective_jina_retain_images}`}>
                <Select value={runDefaults.jina_retain_images} disabled={disabled}
                  ariaLabel={zh ? "Jina 图片链接" : "Jina image links"}
                  options={[
                    { value: "auto", label: zh ? "跟随能力开关" : "Follow capability" },
                    { value: "all", label: zh ? "保留链接" : "Keep links" },
                    { value: "alt", label: zh ? "仅保留说明" : "Alt text only" },
                  ]}
                  onChange={(retain) => setImageReading({ jina_retain_images: retain as "auto" | "alt" | "all" })} />
              </Row>
            )}
            <Row label={zh ? "主模型图片输入" : "Main-model image input"} hint={capability.reason || capabilityLabel}>
              <button type="button" onClick={detectImageInput}
                disabled={disabled || detectingImage || runDefaults.web_image_read_mode === "vision"}
                className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-ink-dim disabled:opacity-40">
                {detectingImage && <Loader2 className="animate-spin" size={12} />}
                {capability.checked_at ? (zh ? "重新检测" : "Retest") : (zh ? "检测图片输入" : "Detect")}
              </button>
            </Row>
          </>
        )}
        <Row label={zh ? "自定义代理" : "Custom proxy"} hint={zh ? "联网请求使用的代理地址；留空表示不使用代理。" : "Proxy for outbound requests. Leave empty to disable."}>
          <TextField
            value={advanced.https_proxy}
            onCommit={(v) => setAdvanced({ https_proxy: v })}
            disabled={disabled}
            placeholder="http://127.0.0.1:7890"
          />
        </Row>
        <Row label={zh ? "网页缓存目录" : "Page cache directory"} hint={zh ? "保存网页读取缓存；留空使用默认目录。" : "Stores fetched-page cache. Leave empty for the default directory."}>
          <TextField
            value={advanced.browser_disk_cache_dir}
            onCommit={(v) => setAdvanced({ browser_disk_cache_dir: v })}
            disabled={disabled}
            placeholder="~/.cache/searchos/page_cache"
          />
        </Row>
      </Card>
      <div>
        <h3 className="mb-2 text-[14px] font-medium text-ink">{zh ? "连接测试" : "Connection tests"}</h3>
        <BackendDiagnosticPanel disabled={disabled} />
      </div>
    </SectionShell>
  );
}
