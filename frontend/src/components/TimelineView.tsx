import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { getTimeline } from "@/api";
import type { IncidentSummary, SourceType, TimelineResponse } from "@/types/api";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { SourceBadge, alertSeverity, fmtTime } from "./SourceBadge";
import { cn } from "@/lib/utils";

const TYPES: { value: SourceType; label: string }[] = [
  { value: "slack", label: "Slack" },
  { value: "monitoring_alert", label: "Alerts" },
  { value: "deployment_log", label: "Deploys" },
];

// datetime-local value (treated as UTC) <-> ISO
const toLocalInput = (iso: string) => (iso ? iso.slice(0, 16) : "");
const fromLocalInput = (v: string) => (v ? `${v}:00Z` : null);

interface Props {
  incidents: IncidentSummary[];
  incidentId: string;
  onIncidentChange: (id: string) => void;
  highlightId: string | null;
  onSelectEvent: (id: string) => void;
}

export function TimelineView({ incidents, incidentId, onIncidentChange, highlightId, onSelectEvent }: Props) {
  const incident = incidents.find((i) => i.incident_id === incidentId);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [types, setTypes] = useState<SourceType[]>(TYPES.map((t) => t.value));
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (incident) { setStart(toLocalInput(incident.start_time)); setEnd(toLocalInput(incident.end_time)); }
  }, [incident]);

  const load = useCallback(async () => {
    if (!incidentId) return;
    setLoading(true); setError(null);
    try {
      setData(await getTimeline(incidentId, {
        start_time: fromLocalInput(start), end_time: fromLocalInput(end),
        source_type: types.join(","),
      }));
    } catch (e) {
      const msg = (e as Error).message;
      setError(msg); toast.error("Couldn't load timeline", { description: msg });
    } finally { setLoading(false); }
  }, [incidentId, start, end, types]);

  useEffect(() => { void load(); }, [load]);

  const toggle = (t: SourceType) => setTypes((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));

  return (
    <section className="panel flex min-h-0 flex-col">
      <div className="space-y-3 border-b p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold">Timeline</h2>
          {data && (
            <span className="font-mono text-xs text-muted-foreground">
              {data.filtered_count} of {data.total_events} events
            </span>
          )}
        </div>
        <select value={incidentId} onChange={(e) => onIncidentChange(e.target.value)} className="field w-full" aria-label="Incident">
          {incidents.map((i) => (
            <option key={i.incident_id} value={i.incident_id}>{i.incident_id} — {i.title}</option>
          ))}
        </select>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <label className="space-y-1 text-xs text-muted-foreground">Start (UTC)
            <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className="field w-full" />
          </label>
          <label className="space-y-1 text-xs text-muted-foreground">End (UTC)
            <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} className="field w-full" />
          </label>
        </div>
        <div className="flex flex-wrap gap-4">
          {TYPES.map((t) => (
            <label key={t.value} className="flex cursor-pointer items-center gap-2 text-xs">
              <Checkbox checked={types.includes(t.value)} onCheckedChange={() => toggle(t.value)} />
              {t.label}
            </label>
          ))}
        </div>
      </div>

      <ol className="min-h-0 flex-1 overflow-y-auto">
        {loading && !data && Array.from({ length: 6 }).map((_, i) => (
          <li key={i} className="space-y-2 border-b p-4"><Skeleton className="h-3 w-40" /><Skeleton className="h-4 w-full" /></li>
        ))}
        {error && <li className="p-4 text-sm text-destructive">{error}</li>}
        {data?.events.length === 0 && !loading && <li className="p-6 text-center text-sm text-muted-foreground">No events match these filters.</li>}
        {data?.events.map((e) => (
          <li key={e.source_id} id={`event-${e.source_id}`}>
            <button
              type="button"
              onClick={() => onSelectEvent(e.source_id)}
              className={cn("timeline-row", highlightId === e.source_id && "timeline-row-highlight", loading && "opacity-60")}
            >
              <div className="flex flex-wrap items-center gap-2 font-mono text-xs text-muted-foreground">
                <span className="text-foreground">{fmtTime(e.timestamp)}</span>
                <SourceBadge type={e.source_type} severity={e.source_type === "monitoring_alert" ? alertSeverity(e.summary) : undefined} />
                <span>{e.author_or_actor}</span>
                <span>·</span>
                <span>{e.channel_or_service}</span>
                <span className="ml-auto opacity-60">{e.source_id}</span>
              </div>
              <p className="mt-1 text-sm">{e.summary}</p>
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
