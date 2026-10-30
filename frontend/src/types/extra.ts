import type { CitationRecord } from "./api";

export interface InvestigationQuestion {
  query: string;
  answer: string;
  citations: CitationRecord[];
  asked_at: string;
}

export interface Investigation {
  id: string;
  incident_id: string;
  title: string;
  analyst: string;
  is_mine: boolean;
  status: "in_progress" | "completed";
  question_count: number;
  last_activity: string;
  questions: InvestigationQuestion[];
}

export interface IngestResponse {
  incident_id: string;
  ingested_count: number;
  status: string;
}
