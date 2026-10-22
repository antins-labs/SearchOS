"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, ArrowUp, Bell, BookOpen, CalendarClock, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, Clock3, FileText, FolderOpen, Globe2, ListTodo, Loader2, MessageCircle, Plus, RefreshCw, Search, Settings2, SlidersHorizontal, Blocks, Square, UserRound, X } from "lucide-react";
import Link from "next/link";
import Image from "next/image";
import type { LocalLibraryController } from "@/hooks/useLocalLibrary";
import { useHostStatus } from "@/hooks/useHostStatus";
import { HOST_LABELS, hostMessage } from "@/lib/hostStatus";
import type { HistoryItem } from "@/lib/api";
import { mobileSourceSelection } from "@/lib/mobileSources";
import type { Turn } from "@/lib/conversation";
import type { SubmitOpts } from "@/components/shell/Composer";
import { useSettings } from "@/components/settings/SettingsProvider";
import SkillChanges from "@/components/conversation/SkillChanges";
import MaterialPicker from "./MaterialPicker";
import MobileSheet from "./MobileSheet";
import MobileReport from "./MobileReport";
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
  onSubmit: (query: string, opts: SubmitOpts, freshRun?: boolean) => void;
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
  const [screen, setScreen] = useState<"home" | "session">("home");
  const [compose, setCompose] = useState<"new" | "continue" | null>(null);
  const [navigationReady, setNavigationReady] = useState(false);
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
  useEffect(() => { scrollRef.current?.scrollTo({ top: 0 }); }, [page, screen, lastTurn?.id]);
  useEffect(() => {
    if (!navigationReady || reportId) return;
    const url = page === "tasks" ? `/m?view=tasks&tab=${taskTab}` : page === "me" ? "/m?view=me" : screen === "session" && lastTurn?.sessionId ? `/m?session=${encodeURIComponent(lastTurn.sessionId)}` : "/m";
    window.history.replaceState(null, "", url);
  }, [page, screen, taskTab, lastTurn?.sessionId, reportId, navigationReady]);
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
  const openTask = async (id: string) => { if (await props.onOpen(id)) { setPage("assistant"); setScreen("session"); setCompose(null); window.history.replaceState(null, "", `/m?session=${encodeURIComponent(id)}`); } };
  const openTarget = async (url: string) => { const target = new URL(url, window.location.origin); if (target.origin !== window.location.origin || target.pathname !== "/m") return; window.history.replaceState(null, "", target.href); if (target.searchParams.has("report")) setReportId(target.searchParams.get("report")); else if (target.searchParams.has("session")) await openTask(target.searchParams.get("session")!); else if (target.searchParams.get("view") === "inbox") setPanel("inbox"); else if (target.searchParams.get("view") === "me") setPage("me"); else if (target.searchParams.get("view") === "tasks") { setPage("tasks"); if (target.searchParams.has("plan") || target.searchParams.get("tab") === "plans") setTaskTab("plans"); } };
  useEffect(() => {
    if (deepLinkLoaded.current) return;
    deepLinkLoaded.current = true;
    const url = window.location.href;
    void openTarget(url).finally(() => setNavigationReady(true));
    // Initial navigation only. Subsequent targets come from inbox and plan actions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const changePage = (next: Page) => { setPage(next); setCompose(null); if (next === "assistant") setScreen("home"); if (next === "tasks") props.onRefresh(); };
  const newTask = () => { setCompose("new"); };
  const fillDraft = (text: string) => { setDraft(text); newTask(); };
  const continueTask = () => { setCompose("continue"); };
  const openMaterials = (mode: "local" | "hybrid" = library.mode === "local" ? "local" : "hybrid") => { setPickerMode(mode); setPanel("materials"); };
  const send = async () => {
    if (!draft.trim() || sending || stopping || library.uploading) return;
    if (host.phase === "unreachable" || host.phase === "checking") { notify("暂时无法确认主机连接，输入内容已保留，请稍后重试。"); host.refresh(); return; }
    const sources = mobileSourceSelection(library.mode, library.libraryId, library.documents, library.selectedDocumentIds);
    if (!(running && compose === "continue") && !sources) { openMaterials(); return; }
    const text = draft.trim();
    setSending(true);
    try {
      if (running && compose === "continue") { if (!await props.onSteer(text)) return; }
      else if (compose === "new") props.onSubmit(text, { sources }, true);
      else props.onSubmit(text, { sources });
      setCompose(null); setPage("assistant"); setScreen("session"); setDraft(""); inputRef.current?.blur();
    } finally { setSending(false); }
  };
  const upload = () => uploadRef.current?.click();
  const latestReport = tasks.filter(item => item.status === "completed").sort((a, b) => b.updated_at - a.updated_at)[0];
  const currentTask = tasks.find(item => item.status === "running");
  const supplement = compose === "continue" && running;

  return <div ref={appRef} className={`${s.app} ${focused ? s.keyboard : ""}`}>
    <header className={s.header}><Link href="/m" className={s.brand} onClick={event => { event.preventDefault(); changePage("assistant"); }}><Image unoptimized src="/searchos-mark.png" alt="" className={s.brandMark} width={30} height={30} /><span>SearchOS</span></Link><button className={s.connectionPill} onClick={() => setPanel("connection")}><i data-ready={host.phase === "online"} />{HOST_LABELS[host.phase]}</button><button className={s.iconButton} aria-label={`消息中心，${assistant.inbox.unread} 条未读`} onClick={() => setPanel("inbox")}><Bell size={19} />{assistant.inbox.unread > 0 && <i className={s.unreadDot} />}</button></header>
    <main ref={scrollRef} className={s.content}>
      {host.phase !== "online" && <div className={s.hostBanner} role="status"><p>{hostMessage(host)}</p><button onClick={host.refresh}>重试</button></div>}
      {host.phase === "online" && host.notice && Date.now() - host.noticeAt < 30000 && <div className={s.hostBanner} role="status"><p>{host.notice === "restarted" ? "主机服务已重启，连接已恢复。请到任务页查看是否有中断的研究。" : "主机连接已恢复，可以继续交办任务。"}</p></div>}
      {page === "assistant" && (screen === "session" && turns.length ? <div className={s.conversation}>
        <div className={s.sectionLabel}><button onClick={() => setScreen("home")}><ArrowLeft size={16} />助理</button><span /><button onClick={() => changePage("tasks")}>全部任务 <ChevronRight size={14} /></button></div>
        {turns.map((turn, index) => <MobileTurn key={turn.id} turn={turn} reconnecting={reconnecting && index === turns.length - 1} onDetails={() => props.onDetails(turn.id)} onOpenSource={props.onOpenSource} onContinue={continueTask} onRerun={() => props.onRerun(turn)} runDisabled={running} />)}
      </div> : <div className={s.home}>
        <p className={s.homeDate}>{new Date().toLocaleDateString("zh-CN", { month: "long", day: "numeric", weekday: "long" })}</p>
        <h1>有什么想了解的？</h1>
        <div className={s.launchCard}>
          <button className={s.launchInput} onClick={newTask}>{draft || "交代一个问题，剩下的交给我"}</button>
          <div className={s.launchTools}><button onClick={() => { newTask(); setPanel("options"); }}><Globe2 size={15} />{SOURCE_LABELS[library.mode]}<ChevronDown size={13} /></button><button aria-label="添加资料" onClick={() => { newTask(); openMaterials(); }}><Plus size={19} /></button><button className={s.launchSend} aria-label="交办新任务" onClick={newTask}><ArrowUp size={20} /></button></div>
        </div>
        <div className={s.shortcuts}>
          <button onClick={() => fillDraft("帮我整理今天值得关注的 AI 新闻，附上原始来源和简短解读。")}><span><Globe2 size={18} /></span>今日 AI 新闻<ChevronRight size={14} /></button>
          <button onClick={() => setEditingPlan("new")}><span><CalendarClock size={18} /></span>定时简报<ChevronRight size={14} /></button>
        </div>
        <div className={s.sectionLabel}><span>最近报告</span><button onClick={() => { setFilter("completed"); setTaskTab("runs"); changePage("tasks"); }}>全部 <ArrowRight size={14} /></button></div>
        {historyStatus === "error" && <button className={s.error} onClick={props.onRefresh}>任务暂时无法加载，重试</button>}
        {latestReport ? <button className={s.briefCard} onClick={() => void openTask(latestReport.session_id)} disabled={!!props.loadingId}>
          <span className={s.briefKicker}><BookOpen size={15} />SEARCHOS · REPORT<time>{new Date(latestReport.updated_at * 1000).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" })}</time></span>
          <h2>{latestReport.title}</h2><span className={s.briefFooter}>{props.loadingId === latestReport.session_id ? "正在打开…" : "阅读报告"}<ArrowRight size={18} /></span>
        </button> : <div className={s.emptyCard}><BookOpen size={23} /><h3>{historyStatus === "loading" ? "正在读取报告…" : "你的下一份发现，从这里开始"}</h3><p>完成的研究会整理在这里。</p></div>}
        <div className={s.sectionLabel}><span>{currentTask ? "正在进行" : "最近任务"}</span><button onClick={() => { setFilter("all"); setTaskTab("runs"); changePage("tasks"); }}>查看任务 <ChevronRight size={14} /></button></div>
        {(currentTask ? [currentTask] : tasks.slice(0, 1)).map(item => <TaskRow key={item.session_id} item={item} compact loading={props.loadingId === item.session_id} disabled={!!props.loadingId} onClick={() => void openTask(item.session_id)} />)}
      </div>)}
      {page === "tasks" && <div className={s.page}>
        <div className={s.pageHeading}><div><h1>任务</h1></div><button className={s.newButton} onClick={() => taskTab === "plans" ? setEditingPlan("new") : newTask()}><Plus size={17} />新建</button><button className={s.iconButton} aria-label="刷新任务" onClick={() => { props.onRefresh(); void assistant.refresh(); }}><RefreshCw size={19} className={historyStatus === "loading" ? s.spin : ""} /></button></div>
        <div className={s.segmented} aria-label="任务类型"><button aria-pressed={taskTab === "runs"} onClick={() => setTaskTab("runs")}>执行记录</button><button aria-pressed={taskTab === "plans"} onClick={() => setTaskTab("plans")}>定时计划</button></div>
        {taskTab === "runs" ? <>
          <div className={s.taskStats}><span><b>{activeCount}</b> 进行中</span><i /><span><b>{needsAttention}</b> 待处理</span><span className={s.caption}>共 {tasks.length} 项</span></div>
          <label className={s.searchBox}><Search size={17} /><input aria-label="搜索任务" placeholder="搜索交办过的任务" value={query} onChange={event => setQuery(event.target.value)} /></label>
          <div className={s.filters}>{[["all","全部"],["running","进行中"],["attention","待处理"],["completed","已完成"]].map(([value,label]) => <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div>
          {historyStatus === "error" && <div role="alert" className={s.error}>任务列表更新失败。<button onClick={props.onRefresh}>重试</button></div>}
          {historyStatus === "loading" && <p role="status" className={s.caption}>正在更新任务…</p>}
          <div className={s.taskList}>{visibleTasks.map(item => <TaskRow key={item.session_id} item={item} loading={props.loadingId === item.session_id} disabled={!!props.loadingId} onClick={() => void openTask(item.session_id)} />)}</div>
          {historyStatus !== "loading" && !visibleTasks.length && <div className={s.empty}><CheckCheck size={34} /><h3>{filter === "attention" ? "暂时没有需要处理的任务" : "这里还没有任务"}</h3><p>{query ? "换一个关键词试试。" : "交代一个问题，让助理开始查找。"}</p><button className={s.textButton} onClick={newTask}>去交办任务 <ArrowRight size={16} /></button></div>}
        </> : <>
          <div className={s.notice}><Clock3 size={20} /><p><b>{host.phase === "online" ? "计划服务正在运行" : HOST_LABELS[host.phase]}</b><span>{host.phase === "online" ? "主机保持在线时，手机离开后计划仍会执行。" : hostMessage(host)}</span></p></div>
          {assistant.error && <p role="alert" className={s.error}>{assistant.error}<button onClick={() => void assistant.refresh()}>重试</button></p>}
          {assistant.plans.map(plan => <PlanCard key={plan.id} plan={plan} onEdit={() => setEditingPlan(plan)} refresh={assistant.refresh} onTarget={url => void openTarget(url)} />)}
          {!assistant.plans.length && <div className={s.empty}><CalendarClock size={36} /><h3>把关心的事，安排成日常</h3><p>每日新闻、每周行业动态，<br />交给助理按时整理。</p></div>}
          <button className={s.outlineButton} onClick={() => setEditingPlan("new")}><Plus size={18} /> 新建定时计划</button>
        </>}
      </div>}
      {page === "me" && <div className={s.page}>
        <div className={s.pageHeading}><div><h1>我的</h1></div></div>
        <button className={s.environmentCard} onClick={() => setPanel("connection")}><span className={s.avatar}><Image unoptimized src="/searchos-mark.png" alt="" width={32} height={32} /></span><span><b>我的 SearchOS</b><small>{HOST_LABELS[host.phase]}</small></span><ChevronRight size={17} /></button>
        <div className={s.menuList}>
          <button onClick={() => setPanel("inbox")}><Bell size={21} /><span><b>消息中心</b><small>{assistant.inbox.unread ? `${assistant.inbox.unread} 条未读消息` : "报告与异常提醒"}</small></span><ChevronRight size={17} /></button>
          <button onClick={() => openMaterials()}><FolderOpen size={21} /><span><b>我的资料</b><small>选择资料，交给助理研究</small></span><ChevronRight size={17} /></button>
          <button onClick={() => setPanel("notifications")}><Bell size={21} /><span><b>消息通知</b><small>系统推送与免打扰</small></span><ChevronRight size={17} /></button>
          <Link href="/m/settings"><Settings2 size={21} /><span><b>更多设置</b><small>模型、搜索与研究偏好</small></span><ChevronRight size={17} /></Link>
          <Link href="/m/skills"><Blocks size={21} /><span><b>助理技能</b><small>查看可用的研究能力</small></span><ChevronRight size={17} /></Link>
        </div><p className={s.footnote}>SearchOS · 让研究更从容</p>
      </div>}
    </main>
    {page === "assistant" && screen === "session" && lastTurn && <div className={s.sessionFooter}>
      {props.error && <p role="alert" className={s.error}>{props.error}</p>}
      <div>{running && <button className={s.outlineButton} disabled={stopping} onClick={props.onStop}><Square size={15} />{stopping ? "正在停止…" : "停止任务"}</button>}<button className={s.primaryButton} onClick={continueTask}><MessageCircle size={17} />{running ? "补充要求" : "继续追问"}</button></div>
    </div>}
    <nav className={s.bottomNav} aria-label="手机导航">{([["assistant","助理",MessageCircle],["tasks","任务",ListTodo],["me","我的",UserRound]] as const).map(([value,label,Icon]) => <button key={value} aria-current={page === value ? "page" : undefined} onClick={() => changePage(value)}><span><Icon size={20} />{value === "tasks" && activeCount > 0 && <i />}</span>{label}</button>)}</nav>
    {compose && !panel && <MobileSheet title={compose === "new" ? "新任务" : supplement ? "补充要求" : "继续追问"} onClose={() => setCompose(null)} footer={<button className={s.primaryButton} disabled={!draft.trim() || sending || stopping || library.uploading} onClick={() => void send()}>{sending ? <Loader2 size={18} className={s.spin} /> : <ArrowUp size={18} />}{supplement ? "发送补充" : "开始研究"}</button>}>
      <div className={s.composePage}>
        <h2>{compose === "new" ? "想查些什么？" : supplement ? "还有什么需要留意？" : "接下来，想了解什么？"}</h2>
        {compose === "continue" && lastTurn && <p className={s.contextLabel}>{lastTurn.query}</p>}
        <textarea ref={inputRef} aria-label={supplement ? "追加任务要求" : "交办任务"} placeholder="写下问题、背景，或你希望得到的结果…" value={draft} onChange={event => setDraft(event.target.value)} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} />
        {props.error && <p role="alert" className={s.error}>{props.error}</p>}
        {library.error && <p role="alert" className={s.error}>{library.error}</p>}
        {library.uploads.length > 0 && <div className={s.uploadProgress} role="status">{library.uploads.map(item => <span key={item.id}><FileText size={13} />{item.name}<b>{item.status === "ready" ? "已就绪" : item.status === "error" || item.status === "index_error" ? "处理失败" : item.status === "index_cancelled" ? "已取消" : item.status === "uploading" ? `${item.progress}%` : "处理中"}</b></span>)}</div>}
        {!supplement && <><div className={s.attachmentChips}>{library.mode !== "web" && library.selectedDocumentIds.map(id => <span key={id}><FileText size={13} /><span>{selectedDocuments.find(doc => doc.document_id === id)?.name ?? "已选资料"}</span><button aria-label={`移除资料 ${selectedDocuments.find(doc => doc.document_id === id)?.name ?? id}`} onClick={() => { library.setDocumentSelected(id, false); if (selectedCount === 1) library.setMode("web"); }}><X size={13} /></button></span>)}</div>
        <div className={s.composeOptions}>
          <button onClick={() => openMaterials()}><span className={s.tileIcon}><FolderOpen size={18} /></span><b>参考资料</b><span>{selectedCount && library.mode !== "web" ? `${selectedCount} 份资料` : "添加资料"}<ChevronRight size={15} /></span></button>
          <button onClick={() => setPanel("options")}><span className={s.tileIcon}><Globe2 size={18} /></span><b>搜索范围</b><span>{SOURCE_LABELS[library.mode]}<ChevronRight size={15} /></span></button>
          <button onClick={() => setPanel("options")}><span className={s.tileIcon}><SlidersHorizontal size={18} /></span><b>研究深度</b><span>{library.mode === "local" ? "文档研究" : ({ low: "快速", medium: "标准", high: "深入", max: "全面" }[overrides.effort || "medium"])}<ChevronRight size={15} /></span></button>
        </div></>}
      </div>
    </MobileSheet>}
    <input ref={uploadRef} type="file" multiple className={s.hidden} aria-label="上传资料文件" accept=".md,.markdown,.txt,.pdf,.docx,.pptx,.xlsx,.csv,.tsv,.json,.jsonl,.html,.htm,.png,.jpg,.jpeg,.webp,.tif,.tiff" onChange={event => { const files = Array.from(event.target.files ?? []); event.target.value = ""; if (!files.length) return; void library.uploadFiles(files).catch(error => notify(error instanceof Error ? error.message : "上传失败，请重试。")); }} />
    {panel === "materials" && <MaterialPicker controller={library} mode={pickerMode} onClose={() => setPanel(null)} onUpload={upload} onApply={selection => { library.restoreSelection(selection); setPanel(null); if (!editingPlan) setCompose(compose || "new"); }} />}
    {panel === "options" && <MobileSheet title="研究选项" onClose={() => setPanel(null)} footer={<button className={s.primaryButton} onClick={() => setPanel(null)}>完成 <Check size={16} /></button>}>
      <h3 className={s.optionHeading}>从哪里寻找答案</h3><div className={s.choiceList}>{(["web","local","hybrid"] as const).map(mode => <button key={mode} aria-pressed={library.mode === mode} onClick={() => { if (mode !== "web" && !selectedCount) { openMaterials(mode); return; } library.setMode(mode); }}><span><b>{SOURCE_LABELS[mode]}</b><small>{mode === "web" ? "搜索公开网络信息" : mode === "local" ? "只研究你选中的资料" : "结合网络与选中的资料"}</small></span>{library.mode === mode ? <Check size={19} /> : <ChevronRight size={17} />}</button>)}</div>
      <h3 className={s.optionHeading}>研究深度</h3><div className={s.depthChoices}>{([[null,"默认"],["low","快速"],["medium","标准"],["high","深入"],["max","全面"]] as const).map(([value,label]) => <button key={label} disabled={library.mode === "local"} aria-pressed={(overrides.effort ?? null) === value} onClick={() => setOverrides({ ...overrides, effort: value ?? undefined })}>{label}</button>)}</div><p className={s.caption}>{library.mode === "local" ? "纯资料任务使用专门的文档研究策略，联网研究深度不适用。" : "越深入通常需要更多时间与模型用量。"}</p>
      <Link className={s.settingsLink} href="/m/settings">其他研究偏好 <ChevronRight size={16} /></Link>
    </MobileSheet>}
    {panel === "notifications" && <NotificationsPanel onClose={() => setPanel(null)} />}
    {panel === "connection" && <ConnectionPanel host={host} onClose={() => setPanel(null)} />}
    {panel === "inbox" && <InboxPanel inbox={assistant.inbox} refresh={assistant.refresh} onTarget={url => void openTarget(url)} onClose={() => setPanel(null)} />}
    {reportId && <ReportPanel key={reportId} id={reportId} onClose={() => { setReportId(null); window.history.replaceState(null, "", "/m"); }} onOpen={id => void openTask(id)} onSource={props.onOpenSource} />}
    {editingPlan && <PlanEditor plan={editingPlan === "new" ? undefined : editingPlan} library={library} onUpload={upload} onClose={() => setEditingPlan(null)} onSave={() => { void assistant.refresh(); setPage("tasks"); setTaskTab("plans"); }} />}
    {props.children}
  </div>;
}

function TaskRow({ item, onClick, compact = false, loading, disabled }: { item: HistoryItem; onClick: () => void; compact?: boolean; loading?: boolean; disabled?: boolean }) {
  return <button className={`${s.taskCard} ${compact ? s.compactTask : ""}`} onClick={onClick} disabled={disabled}>
    <span className={s.taskMeta}><span className={s.status} data-status={item.status}>{loading ? "正在打开…" : STATE_LABELS[item.status]}</span><time>{new Date(item.updated_at * 1000).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })}</time></span>
    <span className={s.taskTitle}><span className={s.taskIcon}>{loading ? <Loader2 size={18} className={s.spin} /> : item.status === "completed" ? <FileText size={18} /> : item.status === "running" ? <Clock3 size={18} /> : <CircleHelp size={18} />}</span><b>{item.title}</b><ChevronRight size={17} /></span>
  </button>;
}
function MobileTurn({ turn, reconnecting, onDetails, onOpenSource, onContinue, onRerun, runDisabled }: { turn: Turn; reconnecting: boolean; onDetails: () => void; onOpenSource: (ref: string) => void; onContinue: () => void; onRerun: () => void; runDisabled: boolean }) {
  const evidence = turn.searchState?.evidence_graph?.nodes ?? [];
  return <article className={s.turn}>
    {turn.status !== "completed" && <><div className={s.userMessage}>{turn.query}</div><div className={s.runSummary}><span className={s.assistantAvatar}><Search size={18} /></span><span><b>{reconnecting ? "正在重新连接" : turn.status === "running" ? "正在研究" : "任务需要处理"}</b><small>{evidence.length ? `已收集 ${evidence.length} 条依据` : "研究进度会实时更新"}</small></span>{turn.status === "running" && <Loader2 size={17} className={s.spin} />}</div></>}
    {turn.status === "running" && <div className={s.progressCard} role="status"><div><span className={s.progressDot} /><span><b>{turn.answer ? "正在整理报告" : turn.workers.some(worker => worker.status === "running") ? "正在查找与核对资料" : "研究任务执行中"}</b><small>{evidence.length} 条依据{turn.meta.elapsed ? ` · 已用时 ${Math.floor(turn.meta.elapsed / 60)} 分 ${Math.floor(turn.meta.elapsed % 60)} 秒` : ""}</small></span></div>{turn.workers.slice(-3).map((worker, index) => <div key={`${worker.name}-${index}`}><span className={s.progressDot} data-status={worker.status} /><span><b>{worker.intent || worker.name}</b><small>{{ pending: "等待执行", running: "进行中", completed: "已完成", error: "执行异常" }[worker.status]}</small></span></div>)}</div>}
    {turn.error && <p className={s.error} role="alert">{turn.error}</p>}
    {turn.answer && <MobileReport query={turn.query} answer={turn.answer} searchState={turn.searchState} events={turn.events} partial={turn.status !== "completed"} onSource={onOpenSource} onContinue={onContinue} onRerun={onRerun} runDisabled={runDisabled} />}
    <SkillChanges sessionId={turn.sessionId} generationId={turn.skillGenerationId} />
    {turn.followUps?.map((text,index) => <div className={s.followup} key={index}><span>补充要求</span>{text}</div>)}
    <div className={s.turnActions}><button onClick={onDetails}>来源与执行详情 <ChevronRight size={14} /></button>{turn.status === "error" && <button onClick={onRerun} disabled={runDisabled}>重新执行 <RefreshCw size={14} /></button>}</div>
  </article>;
}
