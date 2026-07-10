"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { CheckCircle2, CircleAlert, Info, X } from "lucide-react";

import { getSettings } from "@/lib/api";
import type { EffortLevel, SettingsData } from "@/lib/types";

export interface RunOverrides {
  effort?: EffortLevel;
  max_time?: number;
}

export interface UiPrefs {
  verboseCards: boolean;
}

type Status = "loading" | "ready" | "offline";
export type ToastTone = "error" | "success" | "info";

interface ToastState {
  message: string;
  tone: ToastTone;
}

interface SettingsCtx {
  settings: SettingsData | null;
  status: Status;
  refresh: () => void;
  /**
   * Optimistic mutation: apply `optimistic` locally, run the API `call`,
   * merge the authoritative result back; roll back + toast on failure.
   * Stale responses (superseded by a newer mutation) are dropped.
   */
  mutate: <T>(args: {
    optimistic?: (s: SettingsData) => SettingsData;
    call: () => Promise<T>;
    merge?: (s: SettingsData, result: T) => SettingsData;
    errorLabel: string;
  }) => Promise<T | null>;
  overrides: RunOverrides;
  setOverrides: (o: RunOverrides) => void;
  clearOverrides: () => void;
  uiPrefs: UiPrefs;
  setUiPrefs: (p: Partial<UiPrefs>) => void;
  /** Show a transient toast (used for non-settings failures too). */
  notify: (msg: string, tone?: ToastTone) => void;
}

const Ctx = createContext<SettingsCtx | null>(null);

// uiPrefs live in localStorage, read via useSyncExternalStore so SSR renders
// the default and the client snapshot takes over without a setState-in-effect.
const PREFS_KEY = "searchos.uiPrefs";
const DEFAULT_PREFS: UiPrefs = { verboseCards: false };

function subscribePrefs(cb: () => void) {
  window.addEventListener("storage", cb);
  return () => window.removeEventListener("storage", cb);
}
function getPrefsSnapshot(): string {
  try { return localStorage.getItem(PREFS_KEY) ?? ""; } catch { return ""; }
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [overrides, setOverrides] = useState<RunOverrides>({});
  const [toast, setToast] = useState<ToastState | null>(null);
  const seqRef = useRef(0);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(() => {
    const seq = ++seqRef.current;
    getSettings().then((data) => {
      if (seq !== seqRef.current) return;
      if (data) {
        setSettings(data);
        setStatus("ready");
      } else {
        setStatus((s) => (s === "ready" ? s : "offline"));
      }
    });
  }, []);

  // Initial fetch; retry while offline (same cadence as the health poll).
  useEffect(() => {
    refresh();
  }, [refresh]);
  useEffect(() => {
    if (status !== "offline") return;
    const iv = setInterval(refresh, 15000);
    return () => clearInterval(iv);
  }, [status, refresh]);

  const prefsRaw = useSyncExternalStore(subscribePrefs, getPrefsSnapshot, () => "");
  const uiPrefs = useMemo<UiPrefs>(() => {
    if (!prefsRaw) return DEFAULT_PREFS;
    try { return { ...DEFAULT_PREFS, ...JSON.parse(prefsRaw) }; } catch { return DEFAULT_PREFS; }
  }, [prefsRaw]);

  const setUiPrefs = useCallback((patch: Partial<UiPrefs>) => {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify({ ...uiPrefs, ...patch }));
      // "storage" only fires cross-tab natively — notify this tab's store too.
      window.dispatchEvent(new Event("storage"));
    } catch { /* ignore */ }
  }, [uiPrefs]);

  const showToast = useCallback((message: string, tone: ToastTone = "error") => {
    setToast({ message, tone });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3500);
  }, []);

  const mutate = useCallback(
    async <T,>(args: {
      optimistic?: (s: SettingsData) => SettingsData;
      call: () => Promise<T>;
      merge?: (s: SettingsData, result: T) => SettingsData;
      errorLabel: string;
    }): Promise<T | null> => {
      const snapshot = settings;
      const seq = ++seqRef.current;
      if (args.optimistic && snapshot) setSettings(args.optimistic(snapshot));
      try {
        const result = await args.call();
        if (seq === seqRef.current && args.merge) {
          setSettings((s) => (s ? args.merge!(s, result) : s));
        }
        return result;
      } catch (e) {
        if (seq === seqRef.current && snapshot) setSettings(snapshot);
        const detail = e instanceof Error ? e.message : String(e);
        showToast(`${args.errorLabel}: ${detail}`);
        return null;
      }
    },
    [settings, showToast],
  );

  const clearOverrides = useCallback(() => setOverrides({}), []);

  return (
    <Ctx.Provider
      value={{
        settings, status, refresh, mutate,
        overrides, setOverrides, clearOverrides,
        uiPrefs, setUiPrefs,
        notify: showToast,
      }}
    >
      {children}
      {toast && (
        <div
          role={toast.tone === "error" ? "alert" : "status"}
          aria-live={toast.tone === "error" ? "assertive" : "polite"}
          className={`rise-in fixed bottom-6 left-1/2 z-[100] flex max-w-[min(92vw,520px)] -translate-x-1/2 items-start gap-2 rounded-lg border bg-surface px-3.5 py-3 text-[13px] shadow-xl ${
            toast.tone === "error"
              ? "border-err/40 text-err"
              : toast.tone === "success"
                ? "border-ok/40 text-ok"
                : "border-line-strong text-ink"
          }`}
        >
          {toast.tone === "error" ? (
            <CircleAlert className="mt-0.5 shrink-0" size={16} />
          ) : toast.tone === "success" ? (
            <CheckCircle2 className="mt-0.5 shrink-0" size={16} />
          ) : (
            <Info className="mt-0.5 shrink-0 text-accent-ink" size={16} />
          )}
          <span className="min-w-0 flex-1 leading-5">{toast.message}</span>
          <button
            type="button"
            onClick={() => setToast(null)}
            title="Dismiss"
            aria-label="Dismiss notification"
            className="shrink-0 rounded p-0.5 text-ink-faint hover:bg-surface-2 hover:text-ink"
          >
            <X size={14} />
          </button>
        </div>
      )}
    </Ctx.Provider>
  );
}

export function useSettings(): SettingsCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSettings must be used within SettingsProvider");
  return ctx;
}
