"use client";

import { usePathname } from "next/navigation";

/** Keep shared settings and skill links inside the active workspace surface. */
export function useWorkspaceBase() {
  const pathname = usePathname();
  return pathname === "/m" || pathname.startsWith("/m/") ? "/m" : "";
}
