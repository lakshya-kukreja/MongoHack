import * as mock from "@/mocks/mockApi";
import type { TimelineFilters } from "@/mocks/mockApi";
import type { EventRecord, IncidentSummary, QueryRequest, QueryResponse, TimelineResponse } from "@/types/api";
import type { IngestRequest, IngestResponse, Investigation } from "@/types/extra";

export { QUICK_PROMPTS } from "@/mocks/mockApi";
export type { TimelineFilters };

const BASE = import.meta.env["VITE_API_URL"] || "http://127.0.0.1:8000/api";
export const USE_MOCK = import.meta.env["VITE_USE_MOCK"] === "true";

export class BackendUnreachableError extends Error {
  constructor() { super(`Backend unreachable at ${BASE}. Is the API server running?`); }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  const headers = { "Content-Type": "application/json", ...init?.headers };
  try {
    res = await fetch(BASE + path, { ...init, headers });
  } catch {
    throw new BackendUnreachableError();
  }
  if (!res.ok) throw new Error(`Request failed (${res.status}): ${await res.text().catch(() => "")}`);
  return res.json();
}

export function listIncidents(): Promise<IncidentSummary[]> {
  return USE_MOCK ? mock.listIncidents() : req("/incidents");
}

export function getTimeline(incidentId: string, f: TimelineFilters = {}): Promise<TimelineResponse> {
  if (USE_MOCK) return mock.getTimeline(incidentId, f);
  const q = new URLSearchParams();
  if (f.start_time) q.set("start_time", f.start_time);
  if (f.end_time) q.set("end_time", f.end_time);
  if (f.source_type) q.set("source_type", f.source_type);
  return req(`/incidents/${encodeURIComponent(incidentId)}/timeline?${q}`);
}

export function getEvent(incidentId: string, sourceId: string): Promise<EventRecord> {
  return USE_MOCK
    ? mock.getEvent(incidentId, sourceId)
    : req(`/incidents/${encodeURIComponent(incidentId)}/events/${encodeURIComponent(sourceId)}`);
}

export function queryIncident(incidentId: string, body: QueryRequest): Promise<QueryResponse> {
  return USE_MOCK
    ? mock.queryIncident(incidentId, body)
    : req(`/incidents/${encodeURIComponent(incidentId)}/query`, { method: "POST", body: JSON.stringify(body) });
}

export async function ingestIncident(payload: IngestRequest): Promise<IngestResponse> {
  if (USE_MOCK) {
    return mock.ingestIncident(payload);
  }
  return req("/incidents/ingest", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
