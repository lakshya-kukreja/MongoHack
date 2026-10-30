import type { QueryResponse } from "@/types/api";
import type { Investigation } from "@/types/extra";
import { listInvestigations, saveInvestigation } from "@/api";

const KEY = "incident-investigator:my-investigations";

export function loadMine(): Investigation[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as Investigation[]) : [];
  } catch {
    return [];
  }
}

function persistMine(list: Investigation[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    // storage unavailable — app keeps working with in-memory state
  }
}

/** Fetch all investigations: demo/seed ones plus the current user's from localStorage. */
export async function fetchInvestigations(): Promise<Investigation[]> {
  return listInvestigations(loadMine());
}

/** Create or update the current user's investigation for an incident after a question is answered. */
export async function recordQuestion(incidentId: string, title: string, query: string, res: QueryResponse): Promise<Investigation> {
  const mine = loadMine();
  let inv = mine.find((i) => i.incident_id === incidentId);
  const now = new Date().toISOString();
  if (!inv) {
    inv = {
      id: `inv-mine-${incidentId}`,
      incident_id: incidentId,
      title,
      analyst: "You",
      is_mine: true,
      status: "in_progress",
      question_count: 0,
      last_activity: now,
      questions: [],
    };
    mine.push(inv);
  }
  inv.questions.push({ query, answer: res.answer, citations: res.citations, asked_at: now });
  inv.question_count = inv.questions.length;
  inv.last_activity = now;
  persistMine(mine);
  await saveInvestigation(inv).catch(() => inv);
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("investigations-updated"));
  }
  return inv;
}

export function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (!Number.isFinite(diff)) return "";
  const min = Math.max(0, Math.round(diff / 60000));
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}
