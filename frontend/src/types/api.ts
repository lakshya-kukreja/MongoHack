export type SourceType = 'slack' | 'monitoring_alert' | 'deployment_log';
export interface EventRecord { source_id: string; incident_id: string; timestamp: string; source_type: SourceType; author_or_actor: string; channel_or_service: string; summary: string; raw_content: string; structured_payload?: Record<string, any>; tags?: string[]; }
export interface CitationRecord { source_id: string; source_type: SourceType; timestamp: string; author_or_actor: string; channel_or_service: string; summary: string; snippet: string; }
export interface TimelineResponse { incident_id: string; total_events: number; filtered_count: number; events: EventRecord[]; }
export interface QueryRequest { query: string; limit?: number; start_time?: string | null; end_time?: string | null; }
export interface QueryResponse { answer: string; citations: CitationRecord[]; unverified_citations: string[]; retrieved_events: Array<{ source_id: string; timestamp: string; source_type: SourceType; summary: string; score: number; }>; }
export interface IncidentSummary { incident_id: string; title: string; event_count: number; start_time: string; end_time: string; services_involved: string[]; }
