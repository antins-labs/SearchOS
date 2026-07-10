"use client";

import { useSyncExternalStore } from "react";

export type ActivityTab = "coverage" | "evidence" | "versions" | "files" | "events";

export const DEFAULT_ACTIVITY_WIDTH = 560;
export const MIN_ACTIVITY_WIDTH = 360;
export const MAX_ACTIVITY_WIDTH = 760;

type ActivityPreferences = {
  tab: ActivityTab;
  width: number;
};

const STORAGE_KEY = "searchos.activity.preferences.v1";
const DEFAULT_PREFERENCES: ActivityPreferences = { tab: "coverage", width: DEFAULT_ACTIVITY_WIDTH };
const VALID_TABS = new Set<ActivityTab>(["coverage", "evidence", "versions", "files", "events"]);
const listeners = new Set<() => void>();
let current: ActivityPreferences | null = null;

const clampWidth = (width: number) => Math.max(MIN_ACTIVITY_WIDTH, Math.min(MAX_ACTIVITY_WIDTH, width));

function readPreferences(): ActivityPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}") as Partial<ActivityPreferences>;
    return {
      tab: parsed.tab && VALID_TABS.has(parsed.tab) ? parsed.tab : DEFAULT_PREFERENCES.tab,
      width: Number.isFinite(parsed.width) ? clampWidth(Number(parsed.width)) : DEFAULT_PREFERENCES.width,
    };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

function getSnapshot() {
  if (!current) current = readPreferences();
  return current;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY) return;
    current = readPreferences();
    listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function useActivityPreferences() {
  return useSyncExternalStore(subscribe, getSnapshot, () => DEFAULT_PREFERENCES);
}

export function updateActivityPreferences(patch: Partial<ActivityPreferences>, persist = true) {
  const previous = getSnapshot();
  current = {
    tab: patch.tab && VALID_TABS.has(patch.tab) ? patch.tab : previous.tab,
    width: patch.width == null ? previous.width : clampWidth(patch.width),
  };
  if (persist && typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
    } catch {
      // Browsers may deny storage in private or embedded contexts; the live
      // preference still works for the current page session.
    }
  }
  listeners.forEach((listener) => listener());
}
