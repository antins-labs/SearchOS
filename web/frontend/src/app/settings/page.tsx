import type { Metadata } from "next";

import SettingsPage from "@/components/settings/SettingsPage";

export const metadata: Metadata = {
  title: "Settings — SearchOS",
};

export default function Page() {
  return <SettingsPage />;
}
