import type { Metadata } from "next";
import SkillCreationPage from "@/components/skills/SkillCreationPage";

export const metadata: Metadata = {
  title: "技能创建 — SearchOS",
};

export default function Page() {
  return <SkillCreationPage />;
}
