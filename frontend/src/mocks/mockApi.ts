import type { EventRecord, IncidentSummary, QueryRequest, QueryResponse, TimelineResponse } from "@/types/api";
import type { IngestResponse, Investigation } from "@/types/extra";
import fixture from "./inc_2026_042.json";

let EVENTS = fixture as EventRecord[];
const ts = (s: string) => new Date(s).getTime();
const byTime = (a: EventRecord, b: EventRecord) => ts(a.timestamp) - ts(b.timestamp);
const delay = (ms = 250) => new Promise((r) => setTimeout(r, ms));

export interface TimelineFilters { start_time?: string | null; end_time?: string | null; source_type?: string | null; }

function eventsFor(incidentId: string) {
  return EVENTS.filter((e) => e.incident_id === incidentId);
}

export async function listIncidents(): Promise<IncidentSummary[]> {
  await delay();
  const ids = [...new Set(EVENTS.map((e) => e.incident_id))];
  return ids.map((id) => {
    const evs = eventsFor(id).sort(byTime);
    return {
      incident_id: id,
      title: id === "INC-2026-042"
        ? "Payment Gateway P99 Latency Spike & Cascading Connection Pool Exhaustion"
        : `Imported collection ${id}`,
      event_count: evs.length,
      start_time: evs[0]?.timestamp ?? "",
      end_time: evs[evs.length - 1]?.timestamp ?? "",
      services_involved: [...new Set(evs.filter((e) => e.source_type !== "slack").map((e) => e.channel_or_service))],
    };
  });
}

export async function getTimeline(incidentId: string, f: TimelineFilters = {}): Promise<TimelineResponse> {
  await delay();
  const all = eventsFor(incidentId);
  const types = f.source_type ? f.source_type.split(",").map((s) => s.trim()).filter(Boolean) : null;
  const start = f.start_time ? ts(f.start_time) : null;
  const end = f.end_time ? ts(f.end_time) : null;
  const events = all
    .filter((e) => (start === null || ts(e.timestamp) >= start) && (end === null || ts(e.timestamp) <= end))
    .filter((e) => !types || types.includes(e.source_type))
    .sort(byTime);
  return { incident_id: incidentId, total_events: all.length, filtered_count: events.length, events };
}

export async function getEvent(incidentId: string, sourceId: string): Promise<EventRecord> {
  await delay(150);
  const e = eventsFor(incidentId).find((x) => x.source_id === sourceId);
  if (!e) throw new Error(`Event ${sourceId} not found`);
  return e;
}

export const QUICK_PROMPTS = [
  "What was the first sign of trouble in the incident?",
  "Who noticed the issue first and who responded or led the incident?",
  "Which deployment preceded the incident?",
  "What evidence suggests recovery?",
  "What was the likely root cause, and what remains unproven?",
] as const;

const ANSWERS: Record<string, string> = {
  [QUICK_PROMPTS[0]]:
    "The first sign of trouble was a Datadog CRITICAL alert at 14:02:00Z reporting checkout-service P99 latency above 2000ms on /checkout [ALERT-201]. About two minutes later alice.dev noticed the alert in #incidents-prod and began investigating error rates [SLACK-301].",
  [QUICK_PROMPTS[1]]:
    "alice.dev noticed the issue first at 14:04:10Z [SLACK-301]. bob.lead declared SEV-1 incident INC-2026-042 at 14:07:00Z and acted as Incident Commander [SLACK-302]. marcus.eng joined the bridge at 14:08:30Z and began inspecting the v2.4.1 deployment [SLACK-303].",
  [QUICK_PROMPTS[2]]:
    "The deployment of checkout-service v2.4.1 (commit a1f9c8d) to production at 13:45:00Z preceded the incident [DEPLOY-101].",
  [QUICK_PROMPTS[3]]:
    "At 14:28:00Z Datadog reported RECOVERY: P99 latency back to 142ms and the 500 error rate at 0.02% baseline [ALERT-205]. This follows marcus.eng confirming the rollback to v2.4.0 was complete with connections draining [SLACK-307], after the rollback deployment at 14:22:00Z [DEPLOY-102].",
  [QUICK_PROMPTS[4]]:
    "The proven root cause is a connection pool leak in db_pool.py introduced by commit a1f9c8d: connections were not released on client timeout [SLACK-305]. charlie.ops' disk-full hypothesis [SLACK-304] was disproved by disk utilization being normal at 34% [ALERT-203]. Unverified hypothesis: upstream Stripe webhook latency may have contributed to the initial slowdown, but there is no tracing data to confirm it [SLACK-309].",
};

const INSUFFICIENT = "Based on the retrieved incident records, there is insufficient evidence to answer this question.";
const TAG_RE = /\[([A-Z]+-\d+)\]/g;

export async function queryIncident(incidentId: string, req: QueryRequest): Promise<QueryResponse> {
  await delay(700);
  const answer = ANSWERS[req.query.trim()];
  if (!answer) return { answer: INSUFFICIENT, citations: [], unverified_citations: [], retrieved_events: [] };
  const all = eventsFor(incidentId);
  const ids = [...new Set([...answer.matchAll(TAG_RE)].map((m) => m[1] ?? ""))];
  const found = ids.map((id) => all.find((e) => e.source_id === id)).filter((e): e is EventRecord => !!e);
  return {
    answer,
    citations: found.map((e) => ({
      source_id: e.source_id, source_type: e.source_type, timestamp: e.timestamp,
      author_or_actor: e.author_or_actor, channel_or_service: e.channel_or_service,
      summary: e.summary, snippet: e.raw_content.slice(0, 160),
    })),
    unverified_citations: ids.filter((id) => !found.some((e) => e.source_id === id)),
    retrieved_events: found.map((e, i) => ({ source_id: e.source_id, timestamp: e.timestamp, source_type: e.source_type, summary: e.summary, score: 1 - i * 0.05 })),
  };
}

export async function ingestIncident(body: { incident_id: string; events: EventRecord[]; title?: string }): Promise<IngestResponse> {
  await delay(600);
  const incoming = body.events.map((e) => ({ ...e, incident_id: body.incident_id }));
  const existing = new Set(EVENTS.map((e) => e.source_id));
  const fresh = incoming.filter((e) => !existing.has(e.source_id));
  EVENTS = [...EVENTS, ...fresh];

  if (!investigations) investigations = seedInvestigations();
  const title = body.title || `Imported collection ${body.incident_id}`;
  const newInv: Investigation = {
    id: `inv-ingest-${body.incident_id}-${Date.now()}`,
    incident_id: body.incident_id,
    title,
    analyst: "You",
    is_mine: true,
    status: "in_progress",
    question_count: 0,
    last_activity: new Date().toISOString(),
    questions: [],
  };
  investigations.unshift(newInv);

  return { incident_id: body.incident_id, ingested_count: fresh.length, status: "ok" };
}

// ---- Investigations (demo seed; "mine" persisted by the UI via saveInvestigation) ----

let investigations: Investigation[] | null = null;

function seedInvestigations(): Investigation[] {
  const q = (idx: number, asked_at: string) => {
    const answer = ANSWERS[QUICK_PROMPTS[idx] as string] ?? "";
    const ids = [...new Set([...answer.matchAll(TAG_RE)].map((m) => m[1] ?? ""))];
    const all = eventsFor("INC-2026-042");
    const citations = ids
      .map((id) => all.find((e) => e.source_id === id))
      .filter((e): e is EventRecord => !!e)
      .map((e) => ({
        source_id: e.source_id, source_type: e.source_type, timestamp: e.timestamp,
        author_or_actor: e.author_or_actor, channel_or_service: e.channel_or_service,
        summary: e.summary, snippet: e.raw_content.slice(0, 160),
      }));
    return { query: QUICK_PROMPTS[idx] as string, answer, citations, asked_at };
  };
  const title = "Payment Gateway P99 Latency Spike & Cascading Connection Pool Exhaustion";
  return [
    {
      id: "inv-priya", incident_id: "INC-2026-042", title, analyst: "priya.sre", is_mine: false,
      status: "completed", question_count: 2, last_activity: "2026-10-30T16:12:00Z",
      questions: [q(0, "2026-10-30T15:40:00Z"), q(4, "2026-10-30T16:12:00Z")],
    },
    {
      id: "inv-dan", incident_id: "INC-2026-042", title, analyst: "dan.oncall", is_mine: false,
      status: "in_progress", question_count: 2, last_activity: "2026-10-30T17:05:00Z",
      questions: [q(1, "2026-10-30T16:50:00Z"), q(2, "2026-10-30T17:05:00Z")],
    },
    {
      id: "inv-mei", incident_id: "INC-2026-042", title, analyst: "mei.platform", is_mine: false,
      status: "in_progress", question_count: 1, last_activity: "2026-10-30T15:20:00Z",
      questions: [q(3, "2026-10-30T15:20:00Z")],
    },
    {
      id: "inv-dan-old", incident_id: "INC-2026-042", title, analyst: "dan.oncall", is_mine: false,
      status: "completed", question_count: 1, last_activity: "2026-10-30T14:55:00Z",
      questions: [q(2, "2026-10-30T14:55:00Z")],
    },
  ];
}

export async function listInvestigations(extra: Investigation[] = []): Promise<Investigation[]> {
  await delay(200);
  if (!investigations) investigations = seedInvestigations();
  const mineIds = new Set(extra.map((i) => i.id));
  return [...extra, ...investigations.filter((i) => !mineIds.has(i.id))].sort(
    (a, b) => ts(b.last_activity) - ts(a.last_activity),
  );
}

export async function saveInvestigation(inv: Investigation): Promise<Investigation> {
  await delay(100);
  if (!investigations) investigations = seedInvestigations();
  const idx = investigations.findIndex((i) => i.id === inv.id);
  if (idx >= 0) investigations[idx] = inv; else investigations.push(inv);
  return inv;
}
