"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowDown, ArrowRight, ArrowUp, Bell, BookOpen, CalendarClock, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, Clock3, FileText, FolderOpen, Globe2, ListTodo, Loader2, MessageCircle, Plus, RefreshCw, Search, Settings2, SlidersHorizontal, Sparkles, Square, UserRound, X } from "lucide-react";
import Link from "next/link";
import type { LocalLibraryController } from "@/hooks/useLocalLibrary";
import { useHostStatus } from "@/hooks/useHostStatus";
import { HOST_LABELS, hostMessage } from "@/lib/hostStatus";
import type { HistoryItem } from "@/lib/api";
import { declaredCoverageTables } from "@/lib/coverageTables";
import { mobileReportExcerpt } from "@/lib/mobileReportPreview";
import { mobileSourceSelection } from "@/lib/mobileSources";
import type { Turn } from "@/lib/conversation";
import type { SubmitOpts } from "@/components/shell/Composer";
import { useSettings } from "@/components/settings/SettingsProvider";
import Answer, { cleanAnswer } from "@/components/conversation/Answer";
import AnswerActions from "@/components/conversation/AnswerActions";
import SkillChanges from "@/components/conversation/SkillChanges";
import { localCitationLabels } from "@/lib/localCitations";
import MaterialPicker from "./MaterialPicker";
import MobileSheet from "./MobileSheet";
import MobileReportCards from "./MobileReportCards";
import PlanEditor from "./PlanDrafts";
import type { Plan } from "@/lib/assistant";
import { useAssistant, PlanCard, InboxPanel, ReportPanel, ConnectionPanel, NotificationsPanel } from "./AssistantPanels";
import s from "./mobile-assistant.module.css";

type Page = "assistant" | "tasks" | "me";
type Panel = "materials" | "options" | "notifications" | "connection" | "inbox" | null;
interface Props {
  turns: Turn[]; history: HistoryItem[]; historyStatus: "loading" | "ready" | "error";
  loadingId: string | null; running: boolean; reconnecting: boolean; stopping: boolean;
  error: string | null; localLibrary: LocalLibraryController;
  onSubmit: (query: string, opts: SubmitOpts) => void;
  onRerun: (turn: Turn) => void;
  onSteer: (query: string) => Promise<boolean>; onStop: () => void;
  onNew: () => void; onOpen: (id: string) => Promise<boolean>;
  onRefresh: () => void; onDetails: (id: string) => void;
  onOpenSource: (ref: string) => void; children?: ReactNode;
}
const SOURCE_LABELS = { web: "联网", local: "我的资料", hybrid: "综合" };
const STATE_LABELS = { running: "进行中", completed: "已完成", error: "执行失败", incomplete: "已中断" };

export default function MobileAssistant(props: Props) {
  const { turns, history, historyStatus, localLibrary: library, running, reconnecting, stopping } = props;
  const { overrides, setOverrides, notify } = useSettings();
  const host = useHostStatus();
  const [page, setPage] = useState<Page>("assistant");
  const [pickerMode, setPickerMode] = useState<"local" | "hybrid">("hybrid");
  const [panel, setPanel] = useState<Panel>(null);
  const [draft, setDraft] = useState("");
  const [focused, setFocused] = useState(false);
  const [sending, setSending] = useState(false);
  const [taskTab, setTaskTab] = useState<"runs" | "plans">("runs");
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const assistant = useAssistant();
  const [reportId, setReportId] = useState<string | null>(null);
  const deepLinkLoaded = useRef(false);
  const [editingPlan, setEditingPlan] = useState<Plan | "new" | null>(null);
  const appRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastTurn = turns[turns.length - 1];
  // iOS visual viewport shrinks when the keyboard opens; keep the composer in it.
  useEffect(() => {
    const viewport = window.visualViewport;
    const resize = () => appRef.current?.style.setProperty("--mobile-height", `${viewport?.height ?? window.innerHeight}px`);
    resize();
    viewport?.addEventListener("resize", resize);
    window.addEventListener("resize", resize);
    return () => { viewport?.removeEventListener("resize", resize); window.removeEventListener("resize", resize); };
  }, []);
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 144)}px`;
    }
  }, [draft, page]);
  useEffect(() => { scrollRef.current?.scrollTo({ top: 0 }); }, [page, lastTurn?.id]);
  useEffect(() => {
    if (reportId) return;
    if (page === "assistant" && lastTurn?.sessionId) window.history.replaceState(null, "", `/m?session=${encodeURIComponent(lastTurn.sessionId)}`);
    else if (page === "tasks") window.history.replaceState(null, "", `/m?view=tasks&tab=${taskTab}`);
    else if (page === "me") window.history.replaceState(null, "", "/m?view=me");
  }, [page, taskTab, lastTurn?.sessionId, reportId]);
  const tasks = useMemo(() => {
    const entries = history.filter(item => !item.archived);
    if (!lastTurn) return entries;
    const id = lastTurn.sessionId ?? lastTurn.id;
    const existing = entries.find(item => item.session_id === id);
    const current: HistoryItem = { session_id: id, title: existing?.title ?? lastTurn.query, status: lastTurn.status, coverage_score: null, updated_at: existing?.updated_at ?? (lastTurn.meta.startedAt ?? Date.now()) / 1000, project: "", tags: [], favorite: false, archived: false };
    return [current, ...entries.filter(item => item.session_id !== id)];
  }, [history, lastTurn]);
  const visibleTasks = tasks.filter(item => item.title.toLowerCase().includes(query.trim().toLowerCase()) && (filter === "all" || filter === "attention" && ["error", "incomplete"].includes(item.status) || filter === item.status));
  const activeCount = tasks.filter(item => item.status === "running").length;
  const needsAttention = tasks.filter(item => ["error", "incomplete"].includes(item.status)).length;
  const selectedDocuments = library.documents.filter(doc => library.selectedDocumentIds.includes(doc.document_id));
  const selectedCount = library.selectedDocumentIds.length;
  const openTask = async (id: string) => { if (await props.onOpen(id)) { setPage("assistant"); window.history.replaceState(null, "", `/m?session=${encodeURIComponent(id)}`); } };
  const openTarget = (url: string) => { const target = new URL(url, window.location.origin); if (target.origin !== window.location.origin || target.pathname !== "/m") return; window.history.replaceState(null, "", target.href); if (target.searchParams.has("report")) setReportId(target.searchParams.get("report")); else if (target.searchParams.has("session")) void openTask(target.searchParams.get("session")!); else if (target.searchParams.get("view") === "inbox") setPanel("inbox"); else if (target.searchParams.get("view") === "me") setPage("me"); else if (target.searchParams.get("view") === "tasks") { setPage("tasks"); if (target.searchParams.has("plan") || target.searchParams.get("tab") === "plans") setTaskTab("plans"); } };
  useEffect(() => {
    if (deepLinkLoaded.current) return;
    deepLinkLoaded.current = true;
    const url = window.location.href;
    void Promise.resolve().then(() => openTarget(url));
    // Initial navigation only. Subsequent targets come from inbox and plan actions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const changePage = (next: Page) => { setPage(next); if (next === "tasks") props.onRefresh(); };
  const fillDraft = (text: string) => { setDraft(text); inputRef.current?.focus(); };
  const newTask = () => { window.history.replaceState(null, "", "/m"); props.onNew(); setDraft(""); setPage("assistant"); library.setMode("web"); library.selectedDocumentIds.forEach(id => library.setDocumentSelected(id, false)); };
  const openMaterials = (mode: "local" | "hybrid" = library.mode === "local" ? "local" : "hybrid") => { setPickerMode(mode); setPanel("materials"); };
  const send = async () => {
    if (!draft.trim() || sending || stopping || library.uploading) return;
    if (host.phase === "unreachable" || host.phase === "checking") { notify("暂时无法确认主机连接，输入内容已保留，请稍后重试。"); host.refresh(); return; }
    const sources = mobileSourceSelection(library.mode, library.libraryId, library.documents, library.selectedDocumentIds);
    if (!running && !sources) { openMaterials(); return; }
    const text = draft.trim();
    setSending(true);
    try {
      if (running) { if (!await props.onSteer(text)) return; }
      else props.onSubmit(text, { sources });
      setDraft(""); inputRef.current?.blur();
    } finally { setSending(false); }
  };
  const upload = () => uploadRef.current?.click();

  return <div ref={appRef} className={`${s.app} ${focused ? s.keyboard : ""}`}>
    <header className={s.header}><div className={s.brand}><span className={s.brandMark}>S<span>✦</span></span><span>SearchOS<small>你的搜索助理</small></span></div><button className={s.connectionPill} onClick={() => setPanel("connection")}><i data-ready={host.phase === "online"} />{HOST_LABELS[host.phase]}</button><button className={s.iconButton} aria-label={`消息中心，${assistant.inbox.unread} 条未读`} onClick={() => setPanel("inbox")}><Bell size={20} />{assistant.inbox.unread > 0 && <small>{assistant.inbox.unread}</small>}</button><button className={s.iconButton} aria-label="新建任务" onClick={newTask}><Plus size={22} /></button></header>
    <main ref={scrollRef} className={s.content}>
      {host.phase !== "online" && <div className={s.hostBanner} role="status"><p>{hostMessage(host)}</p><button onClick={host.refresh}>重试</button></div>}
      {host.phase === "online" && host.notice && Date.now() - host.noticeAt < 30000 && <div className={s.hostBanner} role="status"><p>{host.notice === "restarted" ? "主机服务已重启，连接已恢复。请到任务页查看是否有中断的研究。" : "主机连接已恢复，可以继续交办任务。"}</p></div>}
      {page === "assistant" && (turns.length ? <div className={s.conversation}>
        <div className={s.sectionLabel}><span>任务对话</span><button onClick={() => changePage("tasks")}>全部任务 <ChevronRight size={14} /></button></div>
        {turns.map((turn, index) => <MobileTurn key={turn.id} turn={turn} reconnecting={reconnecting && index === turns.length - 1} onDetails={() => props.onDetails(turn.id)} onOpenSource={props.onOpenSource} onContinue={() => inputRef.current?.focus()} onRerun={() => props.onRerun(turn)} runDisabled={running} />)}
      </div> : <div className={s.home}>
        <div className={s.eyebrow}><span /> SEARCHOS ASSISTANT</div>
        <h1>把想知道的，<br />交给我。</h1>
        <p className={s.intro}>查找、比较、读资料。<br />你交代需求，我来整理答案。</p>
        <div className={s.suggestions}>
          <button onClick={() => fillDraft("帮我整理今天值得关注的 AI 新闻，附上原始来源和简短解读。")}><span className={s.suggestionIcon}><Globe2 size={20} /></span><span><b>帮我查一查</b><small>今天有哪些值得关注的 AI 新闻？</small></span><ArrowRight size={17} /></button>
          <button onClick={() => openMaterials()}><span className={s.suggestionIcon}><BookOpen size={20} /></span><span><b>带着资料研究</b><small>归纳重点，再核对关键事实</small></span><ArrowRight size={17} /></button>
        </div>
        <button className={s.planBanner} onClick={() => setEditingPlan("new")}><CalendarClock size={22} /><span><b>让好信息，按时到来</b><small>安排定时简报 · 按时执行</small></span><ChevronRight size={17} /></button>
        <div className={s.sectionLabel}><span>最近交办</span><button onClick={() => changePage("tasks")}>全部任务 <ArrowRight size={14} /></button></div>
        {historyStatus === "loading" && !tasks.length ? <p className={s.caption}>正在读取任务…</p> : historyStatus === "error" ? <button className={s.error} onClick={props.onRefresh}>任务暂时无法加载，点击重试</button> : tasks.length ? tasks.slice(0, 2).map(item => <TaskRow key={item.session_id} item={item} compact loading={props.loadingId === item.session_id} disabled={!!props.loadingId} onClick={() => void openTask(item.session_id)} />) : <p className={s.caption}>你的第一份委托，从下面开始。</p>}
      </div>)}
      {page === "tasks" && <div className={s.page}>
        <div className={s.pageHeading}><div><span className={s.eyebrow}>EVERYTHING IN MOTION</span><h1>任务</h1><p>交办过的事情，都在这里。</p></div><button className={s.iconButton} aria-label="刷新任务" onClick={props.onRefresh}><RefreshCw size={19} className={historyStatus === "loading" ? s.spin : ""} /></button></div>
        <div className={s.segmented} aria-label="任务类型"><button aria-pressed={taskTab === "runs"} onClick={() => setTaskTab("runs")}>执行记录</button><button aria-pressed={taskTab === "plans"} onClick={() => setTaskTab("plans")}>定时计划</button></div>
        {taskTab === "runs" ? <>
          <div className={s.taskStats}><span><b>{activeCount}</b> 进行中</span><i /><span><b>{needsAttention}</b> 待处理</span><span className={s.caption}>共 {tasks.length} 项</span></div>
          <label className={s.searchBox}><Search size={17} /><input aria-label="搜索任务" placeholder="搜索交办过的任务" value={query} onChange={event => setQuery(event.target.value)} /></label>
          <div className={s.filters}>{[["all","全部"],["running","进行中"],["attention","待处理"],["completed","已完成"]].map(([value,label]) => <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div>
          {historyStatus === "error" && <div role="alert" className={s.error}>任务列表更新失败。<button onClick={props.onRefresh}>重试</button></div>}
          {historyStatus === "loading" && <p role="status" className={s.caption}>正在更新任务…</p>}
          <div className={s.taskList}>{visibleTasks.map(item => <TaskRow key={item.session_id} item={item} loading={props.loadingId === item.session_id} disabled={!!props.loadingId} onClick={() => void openTask(item.session_id)} />)}</div>
          {historyStatus !== "loading" && !visibleTasks.length && <div className={s.empty}><CheckCheck size={34} /><h3>{filter === "attention" ? "暂时没有需要处理的任务" : "这里还没有任务"}</h3><p>{query ? "换一个关键词试试。" : "交代一个问题，让助理开始查找。"}</p><button className={s.textButton} onClick={() => setPage("assistant")}>去交办任务 <ArrowRight size={16} /></button></div>}
        </> : <>
          <div className={s.notice}><Clock3 size={20} /><p><b>{host.phase === "online" ? "计划服务正在运行" : HOST_LABELS[host.phase]}</b><span>{host.phase === "online" ? "主机保持在线时，手机离开后计划仍会执行。" : hostMessage(host)}</span></p></div>
          {assistant.error && <p role="alert" className={s.error}>{assistant.error}<button onClick={() => void assistant.refresh()}>重试</button></p>}
          {assistant.plans.map(plan => <PlanCard key={plan.id} plan={plan} onEdit={() => setEditingPlan(plan)} refresh={assistant.refresh} onTarget={openTarget} />)}
          {!assistant.plans.length && <div className={s.empty}><CalendarClock size={36} /><h3>把关心的事，安排成日常</h3><p>每日新闻、每周行业动态，<br />交给助理按时整理。</p></div>}
          <button className={s.outlineButton} onClick={() => setEditingPlan("new")}><Plus size={18} /> 新建定时计划</button>
        </>}
      </div>}
      {page === "me" && <div className={s.page}>
        <div className={s.pageHeading}><div><span className={s.eyebrow}>YOUR SPACE</span><h1>我的</h1><p>资料、连接与偏好。</p></div><span className={s.avatar}><UserRound size={27} /></span></div>
        <button className={s.environmentCard} onClick={() => setPanel("connection")}><span className={s.tileIcon}><Globe2 size={23} /></span><span><b>我的 SearchOS</b><small>{HOST_LABELS[host.phase]}</small></span><ChevronRight size={17} /></button>
        <div className={s.menuList}>
          <button onClick={() => setPanel("inbox")}><Bell size={21} /><span><b>消息中心</b><small>{assistant.inbox.unread ? `${assistant.inbox.unread} 条未读消息` : "报告与异常提醒"}</small></span><ChevronRight size={17} /></button>
          <button onClick={() => openMaterials()}><FolderOpen size={21} /><span><b>我的资料</b><small>选择资料，交给助理研究</small></span><ChevronRight size={17} /></button>
          <button onClick={() => setPanel("notifications")}><Bell size={21} /><span><b>消息通知</b><small>系统推送与免打扰</small></span><ChevronRight size={17} /></button>
          <Link href="/m/settings"><Settings2 size={21} /><span><b>更多设置</b><small>模型、搜索与研究偏好</small></span><ChevronRight size={17} /></Link>
          <Link href="/m/skills"><Sparkles size={21} /><span><b>助理技能</b><small>查看可用的研究能力</small></span><ChevronRight size={17} /></Link>
        </div><p className={s.footnote}>SearchOS · 让研究更从容</p>
      </div>}
    </main>
    {page === "assistant" && <div className={s.composerArea}>
      {props.error && <p role="alert" className={s.error}>{props.error}</p>}
      {library.error && <p role="alert" className={s.error}>{library.error}</p>}
      {library.uploads.length > 0 && <div className={s.uploadProgress} role="status">{library.uploads.slice(0, 3).map(item => <span key={item.id}><FileText size={13} />{item.name}<b>{item.status === "ready" ? "已就绪" : item.status === "error" || item.status === "index_error" ? "处理失败" : item.status === "index_cancelled" ? "已取消" : item.status === "uploading" ? `${item.progress}%` : "处理中"}</b></span>)}</div>}
      {selectedCount > 0 && library.mode !== "web" && <div className={s.attachmentChips}>{library.selectedDocumentIds.map(id => <span key={id}><FileText size={13} /><span>{selectedDocuments.find(doc => doc.document_id === id)?.name ?? "已选资料"}</span><button aria-label={`移除资料 ${selectedDocuments.find(doc => doc.document_id === id)?.name ?? id}`} onClick={() => { library.setDocumentSelected(id, false); if (selectedCount === 1) library.setMode("web"); }}><X size={13} /></button></span>)}</div>}
      <form className={s.composer} onSubmit={event => { event.preventDefault(); void send(); }}>
        <textarea ref={inputRef} aria-label={running ? "追加任务要求" : "交办任务"} placeholder={running ? "补充要求，让助理继续调整…" : lastTurn ? "继续追问，或补充你的想法…" : "想了解什么？交代给我…"} rows={2} value={draft} onChange={event => setDraft(event.target.value)} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} />
        <div className={s.composerTools}><button type="button" className={s.addButton} aria-label="添加资料" disabled={running || library.uploading} onClick={() => openMaterials()}><Plus size={22} /></button><button type="button" className={s.sourceButton} disabled={running} onClick={() => setPanel("options")}><Globe2 size={14} />{SOURCE_LABELS[library.mode]}<ChevronDown size={13} /></button><button type="button" className={s.optionButton} aria-label="本次任务选项" disabled={running} onClick={() => setPanel("options")}><SlidersHorizontal size={18} /></button><span className={s.toolSpacer} />{running && <button type="button" className={s.stopButton} disabled={stopping} onClick={props.onStop} aria-label="停止任务">{stopping ? <Loader2 size={17} className={s.spin} /> : <Square size={15} />}<span>停止</span></button>}<button type="submit" className={s.sendButton} disabled={!draft.trim() || sending || stopping || library.uploading} aria-label={running ? "发送补充要求" : "发送任务"}>{sending ? <Loader2 size={19} className={s.spin} /> : <ArrowUp size={21} />}</button></div>
      </form>
      <p className={s.composerHint}>{running ? "任务正在执行，随时可以补充要求" : "重要信息请结合报告中的来源核实"}</p>
    </div>}
    <nav className={s.bottomNav} aria-label="手机导航">{([["assistant","助理",MessageCircle],["tasks","任务",ListTodo],["me","我的",UserRound]] as const).map(([value,label,Icon]) => <button key={value} aria-current={page === value ? "page" : undefined} onClick={() => changePage(value)}><span><Icon size={22} />{value === "tasks" && activeCount > 0 && <i />}</span>{label}</button>)}</nav>
    <input ref={uploadRef} type="file" multiple className={s.hidden} aria-label="上传资料文件" accept=".md,.markdown,.txt,.pdf,.docx,.pptx,.xlsx,.csv,.tsv,.json,.jsonl,.html,.htm,.png,.jpg,.jpeg,.webp,.tif,.tiff" onChange={event => { const files = Array.from(event.target.files ?? []); event.target.value = ""; if (!files.length) return; setPanel(null); setPage("assistant"); void library.uploadFiles(files).catch(error => notify(error instanceof Error ? error.message : "上传失败，请重试。")); }} />
    {panel === "materials" && <MaterialPicker controller={library} mode={pickerMode} onClose={() => setPanel(null)} onUpload={upload} onApply={selection => { library.restoreSelection(selection); setPanel(null); setPage("assistant"); }} />}
    {panel === "options" && <MobileSheet title="本次任务选项" subtitle="通常保持默认即可，按需要调整。" onClose={() => setPanel(null)} footer={<button className={s.primaryButton} onClick={() => setPanel(null)}>完成 <Check size={16} /></button>}>
      <h3 className={s.optionHeading}>从哪里寻找答案</h3><div className={s.choiceList}>{(["web","local","hybrid"] as const).map(mode => <button key={mode} aria-pressed={library.mode === mode} onClick={() => { if (mode !== "web" && !selectedCount) { openMaterials(mode); return; } library.setMode(mode); }}><span><b>{SOURCE_LABELS[mode]}</b><small>{mode === "web" ? "搜索公开网络信息" : mode === "local" ? "只研究你选中的资料" : "结合网络与选中的资料"}</small></span>{library.mode === mode ? <Check size={19} /> : <ChevronRight size={17} />}</button>)}</div>
      <h3 className={s.optionHeading}>研究深度</h3><div className={s.depthChoices}>{([[null,"默认"],["low","快速"],["medium","标准"],["high","深入"],["max","全面"]] as const).map(([value,label]) => <button key={label} disabled={library.mode === "local"} aria-pressed={(overrides.effort ?? null) === value} onClick={() => setOverrides({ ...overrides, effort: value ?? undefined })}>{label}</button>)}</div><p className={s.caption}>{library.mode === "local" ? "纯资料任务使用专门的文档研究策略，联网研究深度不适用。" : "越深入通常需要更多时间与模型用量。"}</p>
      <Link className={s.settingsLink} href="/m/settings">其他研究偏好 <ChevronRight size={16} /></Link>
    </MobileSheet>}
    {panel === "notifications" && <NotificationsPanel onClose={() => setPanel(null)} />}
    {panel === "connection" && <ConnectionPanel host={host} onClose={() => setPanel(null)} />}
    {panel === "inbox" && <InboxPanel inbox={assistant.inbox} refresh={assistant.refresh} onTarget={openTarget} onClose={() => setPanel(null)} />}
    {reportId && <ReportPanel key={reportId} id={reportId} onClose={() => { setReportId(null); window.history.replaceState(null, "", "/m"); }} onOpen={id => void openTask(id)} onSource={props.onOpenSource} />}
    {editingPlan && <PlanEditor plan={editingPlan === "new" ? undefined : editingPlan} library={library} onUpload={upload} onClose={() => setEditingPlan(null)} onSave={() => { void assistant.refresh(); setPage("tasks"); setTaskTab("plans"); }} />}
    {props.children}
  </div>;
}

function TaskRow({ item, onClick, compact = false, loading, disabled }: { item: HistoryItem; onClick: () => void; compact?: boolean; loading?: boolean; disabled?: boolean }) {
  return <button className={`${s.taskCard} ${compact ? s.compactTask : ""}`} onClick={onClick} disabled={disabled}>
    <span className={s.taskIcon}>{loading ? <Loader2 size={19} className={s.spin} /> : item.status === "completed" ? <FileText size={19} /> : item.status === "running" ? <Clock3 size={19} /> : <CircleHelp size={19} />}</span>
    <span className={s.taskText}><b>{item.title}</b><span className={s.taskMeta}><span className={s.status} data-status={item.status}>{STATE_LABELS[item.status]}</span><time>{new Date(item.updated_at * 1000).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })}</time></span></span><ChevronRight size={17} />
  </button>;
}
function MobileTurn({ turn, reconnecting, onDetails, onOpenSource, onContinue, onRerun, runDisabled }: { turn: Turn; reconnecting: boolean; onDetails: () => void; onOpenSource: (ref: string) => void; onContinue: () => void; onRerun: () => void; runDisabled: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const answer = cleanAnswer(turn.answer);
  const evidence = turn.searchState?.evidence_graph?.nodes ?? [];
  const preview = mobileReportExcerpt(answer, turn.query);
  const tables = declaredCoverageTables(turn.searchState?.coverage_map).filter(table => table.entities.length > 0);
  return <article className={s.turn}>
    <div className={s.userMessage}>{turn.query}</div>
    <div className={s.runSummary}><span className={s.assistantAvatar}><Sparkles size={17} /></span><span><b>{reconnecting ? "正在重新连接" : turn.status === "running" ? answer ? "正在整理结果" : "正在研究你的问题" : turn.status === "completed" ? "这件事，有结果了" : "这次任务需要处理"}</b><small>{turn.status === "running" ? "可以离开此页，稍后从任务中继续查看" : turn.status === "completed" ? "报告与来源已整理在下方" : "查看原因后，可以调整要求再试"}</small></span>{turn.status === "running" && <Loader2 size={17} className={s.spin} />}</div>
    {turn.error && <p className={s.error} role="alert">{turn.error}</p>}
    {answer && <section className={s.report}>
      <div className={s.sectionLabel}><span>{turn.status !== "completed" ? "当前输出 · 非最终报告" : expanded ? "完整报告" : "报告预览"}</span><BookOpen size={15} /></div>
      {expanded ? <Answer markdown={answer} localSources={evidence.map(node => node.source).filter(source => source.startsWith("local://"))} localSourceLabels={localCitationLabels(turn.events, evidence)} evidenceSources={Object.fromEntries(evidence.filter(node => !node.status || node.status === "active").map(node => [node.id, node.source_urls?.length ? node.source_urls : node.source]))} onOpenLocalSource={onOpenSource} /> : <div className={s.reportPreview}>
        {!tables.length && preview && <p>{preview}</p>}
        {tables.map(table => <MobileReportCards key={table.table_id} table={table} cells={turn.searchState?.coverage_map.cells ?? {}} evidence={evidence} onOpenSource={onOpenSource} />)}
        {!preview && !tables.length && <p>报告以结构化信息呈现，展开查看详细内容与来源。</p>}
      </div>}
      <button className={s.readReport} onClick={() => setExpanded(value => !value)}>{expanded ? "收起报告" : "阅读完整报告"}{expanded ? <ChevronDown size={16} /> : <ArrowDown size={16} />}</button>
      {expanded && <AnswerActions query={turn.query} markdown={answer} collapsible={false} collapsed={false} onToggleCollapse={() => {}} onRerun={onRerun} onContinue={onContinue} runDisabled={runDisabled} />}
    </section>}
    <SkillChanges sessionId={turn.sessionId} generationId={turn.skillGenerationId} />
    {turn.followUps?.map((text,index) => <div className={s.followup} key={index}><span>补充要求</span>{text}</div>)}
    <div className={s.turnActions}><button onClick={onDetails}>来源与更多详情 <ChevronRight size={14} /></button>{turn.status === "error" && <button onClick={onRerun} disabled={runDisabled}>重新执行 <RefreshCw size={14} /></button>}{turn.status === "completed" && <button onClick={onContinue}>继续追问 <ArrowRight size={14} /></button>}</div>
  </article>;
}
