import type { Metadata, Viewport } from "next";
import s from "@/components/mobile/mobile-assistant.module.css";
import AssistantAccess from "@/components/mobile/AssistantAccess";
import { SelectSizeProvider } from "@/components/ui/Select";
export const metadata: Metadata = { title: "SearchOS · 搜索助理", manifest: "/searchos.webmanifest", appleWebApp: { capable: true, title: "SearchOS", statusBarStyle: "default" }, icons: { apple: "/mobile-icon-180.png" } };
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#2563EB" };
export default function MobileLayout({ children }: { children: React.ReactNode }) { return <div className={s.theme}><SelectSizeProvider size="lg"><AssistantAccess>{children}</AssistantAccess></SelectSizeProvider></div>; }
