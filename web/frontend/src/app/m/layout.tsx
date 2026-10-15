import type { Metadata, Viewport } from "next";
import AssistantAccess from "@/components/mobile/AssistantAccess";
export const metadata: Metadata = { title: "SearchOS · 搜索助理", manifest: "/searchos.webmanifest", appleWebApp: { capable: true, title: "SearchOS", statusBarStyle: "default" }, icons: { apple: "/mobile-icon-180.png" } };
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };
export default function MobileLayout({ children }: { children: React.ReactNode }) { return <AssistantAccess>{children}</AssistantAccess>; }
