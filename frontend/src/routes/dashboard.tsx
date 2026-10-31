import { createFileRoute } from "@tanstack/react-router";
import { DashboardView } from "@/components/DashboardView";

export const Route = createFileRoute("/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — Incident Investigator" },
      { name: "description", content: "Post-incident review metrics, event distribution, and recent investigations." },
    ],
  }),
  component: DashboardView,
});

