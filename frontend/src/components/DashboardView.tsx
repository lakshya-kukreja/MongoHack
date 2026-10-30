import { useEffect, useState, useMemo, useCallback } from "react";
import { Link } from "@tanstack/react-router";
import {
  Flame,
  Activity,
  Layers,
  Clock,
  ArrowRight,
  WifiOff,
  User,
  HelpCircle,
  CheckCircle2,
  AlertCircle,
  FileSearch,
} from "lucide-react";
import { listIncidents, getTimeline, USE_MOCK } from "@/api";
import type { IncidentSummary, EventRecord } from "@/types/api";
import type { Investigation } from "@/types/extra";
import { fetchInvestigations, relTime } from "@/lib/investigations";
import { SourceBadge, fmtTime } from "@/components/SourceBadge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

function formatDuration(startIso: string, endIso: string): string {
  if (!startIso || !endIso) return "N/A";
  const start = new Date(startIso).getTime();
  const end = new Date(endIso).getTime();
  const diffMs = Math.max(0, end - start);
  const totalMin = Math.round(diffMs / 60000);
  const hours = Math.floor(totalMin / 60);
  const mins = totalMin % 60;
  if (hours === 0) return `${mins}m`;
  return `${hours}h ${mins.toString().padStart(2, "0")}m`;
}

export function DashboardView() {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [incList, invList] = await Promise.all([
        listIncidents(),
        fetchInvestigations(),
      ]);
      setIncidents(incList);
      setInvestigations(invList);

      // Load events for the primary incident (or all incidents)
      if (incList.length > 0) {
        const primaryId = incList[0]!.incident_id;
        const timelineRes = await getTimeline(primaryId);
        setEvents(timelineRes.events);
      }
    } catch (e) {
      setError((e as Error).message || "Failed to load dashboard metrics");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
    const handleUpdate = () => loadAll();
    window.addEventListener("investigations-updated", handleUpdate);
    return () => window.removeEventListener("investigations-updated", handleUpdate);
  }, [loadAll]);

  // Computed metrics from loaded data:
  const totalIncidents = incidents.length;
  const totalEvents = useMemo(() => {
    return incidents.reduce((acc, inc) => acc + inc.event_count, 0);
  }, [incidents]);

  const allServices = useMemo(() => {
    const set = new Set<string>();
    incidents.forEach((inc) => inc.services_involved.forEach((s) => set.add(s)));
    return Array.from(set);
  }, [incidents]);

  const incidentDuration = useMemo(() => {
    if (incidents.length === 0) return "0m";
    const primary = incidents[0]!;
    return formatDuration(primary.start_time, primary.end_time);
  }, [incidents]);

  // Source Type breakdown counts
  const sourceBreakdown = useMemo(() => {
    const counts = {
      slack: 0,
      monitoring_alert: 0,
      deployment_log: 0,
    };
    events.forEach((e) => {
      if (e.source_type in counts) {
        counts[e.source_type as keyof typeof counts]++;
      }
    });
    const total = events.length || 1;
    return {
      counts,
      percentages: {
        slack: Math.round((counts.slack / total) * 100),
        monitoring_alert: Math.round((counts.monitoring_alert / total) * 100),
        deployment_log: Math.round((counts.deployment_log / total) * 100),
      },
    };
  }, [events]);

  // Investigation activity metrics
  const activityMetrics = useMemo(() => {
    let inProgress = 0;
    let completed = 0;
    let withCitations = 0;
    let insufficient = 0;

    investigations.forEach((inv) => {
      if (inv.status === "completed") completed++;
      else inProgress++;

      inv.questions.forEach((q) => {
        if (q.citations && q.citations.length > 0) {
          withCitations++;
        } else {
          insufficient++;
        }
      });
    });

    return { inProgress, completed, withCitations, insufficient };
  }, [investigations]);

  // 5 most recent investigations
  const recentFive = useMemo(() => {
    return [...investigations]
      .sort((a, b) => new Date(b.last_activity).getTime() - new Date(a.last_activity).getTime())
      .slice(0, 5);
  }, [investigations]);

  // Mini timeline calculations
  const miniTimelineMarkers = useMemo(() => {
    if (events.length === 0) return [];
    const startTime = new Date(events[0]!.timestamp).getTime();
    const endTime = new Date(events[events.length - 1]!.timestamp).getTime();
    const span = Math.max(1, endTime - startTime);

    return events.map((e) => {
      const t = new Date(e.timestamp).getTime();
      const posPercent = Math.min(100, Math.max(0, ((t - startTime) / span) * 100));
      return { event: e, posPercent };
    });
  }, [events]);

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <div className="flex items-center justify-between">
          <div className="h-6 w-48 animate-pulse rounded bg-muted/60" />
          <div className="h-6 w-24 animate-pulse rounded bg-muted/60" />
        </div>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 animate-pulse rounded-xl bg-card border" />
          ))}
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="h-64 animate-pulse rounded-xl bg-card border" />
          <div className="h-64 animate-pulse rounded-xl bg-card border" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="panel max-w-md p-6 text-center">
          <WifiOff className="mx-auto size-7 text-destructive" />
          <h2 className="mt-3 text-base font-semibold">Couldn't load dashboard</h2>
          <p className="mt-1 text-xs text-muted-foreground">{error}</p>
          <button
            onClick={loadAll}
            className="mt-4 rounded-md border px-3 py-1.5 text-xs hover:bg-accent"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const primaryIncident = incidents[0];

  return (
    <div className="space-y-6 p-6 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">Incident Dashboard</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Operational overview computed deterministically from incident telemetry & investigation records.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="rounded border px-2 py-0.5 font-mono text-[10px] uppercase text-muted-foreground">
            {USE_MOCK ? "mock data" : "live api"}
          </span>
          <Link
            to="/investigate"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Open Investigation
            <ArrowRight className="size-3.5" />
          </Link>
        </div>
      </div>

      {/* 4 Stat Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {/* Incidents Count */}
        <div className="panel p-4">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-xs font-medium">Active Incidents</span>
            <Flame className="size-4 text-amber-500" />
          </div>
          <div className="mt-2 text-2xl font-bold tracking-tight text-foreground">
            {totalIncidents}
          </div>
          <p className="mt-1 truncate text-[11px] text-muted-foreground font-mono">
            {primaryIncident?.incident_id ?? "None"}
          </p>
        </div>

        {/* Total Events */}
        <div className="panel p-4">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-xs font-medium">Total Events</span>
            <Activity className="size-4 text-primary" />
          </div>
          <div className="mt-2 text-2xl font-bold tracking-tight text-foreground font-mono">
            {totalEvents}
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Across {events.length} chronological records
          </p>
        </div>

        {/* Incident Duration */}
        <div className="panel p-4">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-xs font-medium">Incident Duration</span>
            <Clock className="size-4 text-emerald-500" />
          </div>
          <div className="mt-2 text-2xl font-bold tracking-tight text-foreground font-mono">
            {incidentDuration}
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {primaryIncident ? `${fmtTime(primaryIncident.start_time)} → ${fmtTime(primaryIncident.end_time)}` : "N/A"}
          </p>
        </div>

        {/* Services Involved */}
        <div className="panel p-4">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-xs font-medium">Services Involved</span>
            <Layers className="size-4 text-indigo-400" />
          </div>
          <div className="mt-2 text-2xl font-bold tracking-tight text-foreground font-mono">
            {allServices.length}
          </div>
          <p className="mt-1 truncate text-[11px] text-muted-foreground">
            {allServices.join(", ") || "None"}
          </p>
        </div>
      </div>

      {/* Row 2: Event Breakdown Chart & Compact Mini-Timeline */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Source Type Breakdown Bar Chart */}
        <div className="panel p-5">
          <h2 className="text-sm font-semibold text-foreground flex items-center justify-between">
            <span>Events by Source Type</span>
            <span className="font-mono text-xs text-muted-foreground font-normal">
              {events.length} total events
            </span>
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Normalized data distribution across communication and observability platforms.
          </p>

          <div className="mt-5 space-y-4">
            {/* Slack */}
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="flex items-center gap-2">
                  <span className="size-2.5 rounded-full" style={{ backgroundColor: "var(--src-slack)" }} />
                  <span className="font-medium">Slack Chat Messages</span>
                </span>
                <span className="font-mono text-muted-foreground">
                  {sourceBreakdown.counts.slack} ({sourceBreakdown.percentages.slack}%)
                </span>
              </div>
              <div className="h-3 w-full rounded-full bg-secondary overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${sourceBreakdown.percentages.slack}%`,
                    backgroundColor: "var(--src-slack)",
                  }}
                />
              </div>
            </div>

            {/* Monitoring Alert */}
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="flex items-center gap-2">
                  <span className="size-2.5 rounded-full" style={{ backgroundColor: "var(--src-alert)" }} />
                  <span className="font-medium">Monitoring Alerts (Datadog / CW)</span>
                </span>
                <span className="font-mono text-muted-foreground">
                  {sourceBreakdown.counts.monitoring_alert} ({sourceBreakdown.percentages.monitoring_alert}%)
                </span>
              </div>
              <div className="h-3 w-full rounded-full bg-secondary overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${sourceBreakdown.percentages.monitoring_alert}%`,
                    backgroundColor: "var(--src-alert)",
                  }}
                />
              </div>
            </div>

            {/* Deployment Log */}
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="flex items-center gap-2">
                  <span className="size-2.5 rounded-full" style={{ backgroundColor: "var(--src-deploy)" }} />
                  <span className="font-medium">Deployment & CI/CD Logs</span>
                </span>
                <span className="font-mono text-muted-foreground">
                  {sourceBreakdown.counts.deployment_log} ({sourceBreakdown.percentages.deployment_log}%)
                </span>
              </div>
              <div className="h-3 w-full rounded-full bg-secondary overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${sourceBreakdown.percentages.deployment_log}%`,
                    backgroundColor: "var(--src-deploy)",
                  }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Compact Horizontal Mini-Timeline */}
        <div className="panel p-5 flex flex-col justify-between">
          <div>
            <h2 className="text-sm font-semibold text-foreground flex items-center justify-between">
              <span>Incident Event Chronology</span>
              {primaryIncident && (
                <span className="font-mono text-xs text-muted-foreground font-normal">
                  {primaryIncident.incident_id}
                </span>
              )}
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Deterministic horizontal distribution of telemetry markers. Hover marker for event detail.
            </p>
          </div>

          <div className="py-8">
            <div className="relative h-2 w-full rounded-full bg-secondary/80">
              {/* Event Markers along the line */}
              {miniTimelineMarkers.map(({ event: e, posPercent }) => {
                const color =
                  e.source_type === "slack"
                    ? "var(--src-slack)"
                    : e.source_type === "deployment_log"
                    ? "var(--src-deploy)"
                    : "var(--src-alert)";

                return (
                  <Tooltip key={e.source_id}>
                    <TooltipTrigger asChild>
                      <Link
                        to="/investigate/$incidentId"
                        params={{ incidentId: e.incident_id }}
                        search={{ event: e.source_id }}
                        className="group absolute top-1/2 -translate-y-1/2 -translate-x-1/2 cursor-pointer transition-transform hover:scale-150"
                        style={{ left: `${posPercent}%` }}
                      >
                        <span
                          className="block size-3 rounded-full border-2 border-background shadow-md transition-shadow group-hover:ring-2 group-hover:ring-primary"
                          style={{ backgroundColor: color }}
                        />
                      </Link>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-xs max-w-xs">
                      <div className="font-mono font-semibold flex items-center gap-1.5">
                        <SourceBadge type={e.source_type} />
                        <span>{e.source_id}</span>
                        <span className="text-[10px] text-muted-foreground">{fmtTime(e.timestamp)}</span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-foreground/90">{e.summary}</p>
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </div>

            {/* Time boundaries */}
            {primaryIncident && (
              <div className="mt-3 flex justify-between font-mono text-[10px] text-muted-foreground">
                <span>{fmtTime(primaryIncident.start_time)}</span>
                <span className="text-foreground/70">100% Deterministic Sorting</span>
                <span>{fmtTime(primaryIncident.end_time)}</span>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground border-t pt-3">
            <span className="flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ backgroundColor: "var(--src-slack)" }} />
              Slack ({sourceBreakdown.counts.slack})
            </span>
            <span className="flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ backgroundColor: "var(--src-alert)" }} />
              Alerts ({sourceBreakdown.counts.monitoring_alert})
            </span>
            <span className="flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ backgroundColor: "var(--src-deploy)" }} />
              Deployments ({sourceBreakdown.counts.deployment_log})
            </span>
          </div>
        </div>
      </div>

      {/* Row 3: Investigation Activity & 5 Most Recent Investigations */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Investigation Activity Card */}
        <div className="panel p-5 lg:col-span-1">
          <h2 className="text-sm font-semibold text-foreground">Investigation Activity</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Post-incident triage cases and RAG evaluation questions.
          </p>

          <div className="mt-5 space-y-4">
            <div className="flex items-center justify-between rounded-lg border p-3 bg-card/40">
              <div className="flex items-center gap-2.5">
                <div className="size-2 rounded-full bg-amber-400" />
                <span className="text-xs font-medium">In Progress Cases</span>
              </div>
              <span className="font-mono text-sm font-bold text-foreground">
                {activityMetrics.inProgress}
              </span>
            </div>

            <div className="flex items-center justify-between rounded-lg border p-3 bg-card/40">
              <div className="flex items-center gap-2.5">
                <div className="size-2 rounded-full bg-emerald-400" />
                <span className="text-xs font-medium">Completed Cases</span>
              </div>
              <span className="font-mono text-sm font-bold text-foreground">
                {activityMetrics.completed}
              </span>
            </div>

            <div className="flex items-center justify-between rounded-lg border p-3 bg-card/40">
              <div className="flex items-center gap-2.5">
                <CheckCircle2 className="size-3.5 text-primary" />
                <span className="text-xs font-medium">Answered with Verified Citations</span>
              </div>
              <span className="font-mono text-sm font-bold text-primary">
                {activityMetrics.withCitations}
              </span>
            </div>

            <div className="flex items-center justify-between rounded-lg border p-3 bg-card/40">
              <div className="flex items-center gap-2.5">
                <AlertCircle className="size-3.5 text-muted-foreground" />
                <span className="text-xs font-medium">Insufficient Evidence Flags</span>
              </div>
              <span className="font-mono text-sm font-bold text-muted-foreground">
                {activityMetrics.insufficient}
              </span>
            </div>
          </div>
        </div>

        {/* 5 Most Recent Investigations List */}
        <div className="panel p-5 lg:col-span-2 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">Recent Investigations</h2>
              <span className="text-xs text-muted-foreground">Top 5 active cases</span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Select an investigation to inspect questions, timeline interactions, and citations.
            </p>

            <div className="mt-4 space-y-2">
              {recentFive.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">
                  <FileSearch className="mx-auto mb-1.5 size-6 opacity-40" />
                  No investigations recorded yet.
                </div>
              ) : (
                recentFive.map((inv) => (
                  <Link
                    key={inv.id}
                    to="/investigate/$incidentId"
                    params={{ incidentId: inv.incident_id }}
                    search={{ invId: inv.id }}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/70 p-3 transition-colors hover:border-primary/50 hover:bg-accent/40"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-xs font-medium text-foreground">
                          {inv.title}
                        </span>
                        <span className="font-mono text-[10px] text-muted-foreground">
                          {inv.incident_id}
                        </span>
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-[10px] text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <User className="size-3" />
                          {inv.is_mine ? <strong className="text-foreground">You</strong> : inv.analyst}
                        </span>
                        <span className="flex items-center gap-1 font-mono">
                          <HelpCircle className="size-3" />
                          {inv.question_count} questions asked
                        </span>
                        <span>{relTime(inv.last_activity)}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "rounded px-2 py-0.5 text-[9px] font-semibold uppercase",
                          inv.status === "completed"
                            ? "bg-emerald-500/15 text-emerald-400"
                            : "bg-amber-500/15 text-amber-400"
                        )}
                      >
                        {inv.status === "completed" ? "Completed" : "In progress"}
                      </span>
                      <ArrowRight className="size-3.5 text-muted-foreground" />
                    </div>
                  </Link>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

