import { notFound, redirect } from "next/navigation";
import ResearchWorkspace from "@/components/research/ResearchWorkspace";
import SettingsPage from "@/components/settings/SettingsPage";
import SkillLibraryPage from "@/components/skills/SkillLibraryPage";
import SkillCreationPage from "@/components/skills/SkillCreationPage";
export default async function MobilePage({ params }: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await params;
  const route = path.join("/");
  if (!route) return <ResearchWorkspace mobile />;
  if (route === "settings") return <SettingsPage />;
  if (route === "skills") return <SkillLibraryPage />;
  if (route === "skills/new") return <SkillCreationPage />;
  // The previous independent prototype is superseded by the shared workspace.
  if (/^(tasks|inbox|schedules|reports|runs|conversations)(\/|$)/.test(route) || route.startsWith("settings/")) redirect("/m");
  notFound();
}
