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
  const [toast, setToast] = useState<string | null>(null);
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

  const showToast = useCallback((msg: string) => {
    setToast(msg);
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
      }}
    >
      {children}
      {toast && (
        <div className="rise-in fixed bottom-6 left-1/2 z-50 -translate-x-1/2">
          <div className="surface rounded-xl border-err/40 px-4 py-2.5 text-[13px] text-err shadow-xl">
            {toast}
          </div>
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
