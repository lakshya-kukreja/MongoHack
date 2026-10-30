import type { SourceType } from "@/types/api";
import { cn } from "@/lib/utils";

const label: Record<SourceType, string> = { slack: "slack", monitoring_alert: "alert", deployment_log: "deploy" };

export function SourceBadge({ type, severity, className }: { type: SourceType; severity?: "critical" | "warning" | undefined; className?: string }) {
  const cls =
    type === "slack" ? "badge-slack" : type === "deployment_log" ? "badge-deploy" : severity === "warning" ? "badge-warn" : "badge-alert";
  return (
    <span className={cn("inline-flex shrink-0 items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide", cls, className)}>
      {label[type]}
    </span>
  );
}

export function alertSeverity(summary: string): "critical" | "warning" {
  return /^CRITICAL/i.test(summary) ? "critical" : "warning";
}

export function fmtTime(iso: string) {
  return new Date(iso).toISOString().slice(11, 19) + "Z";
}
