import type { Metadata } from "next";
import SkillLibraryPage from "@/components/skills/SkillLibraryPage";

export const metadata: Metadata = {
  title: "技能库 — SearchOS",
};

export default function Page() {
  return <SkillLibraryPage />;
}
