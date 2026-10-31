import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState, useRef, useCallback } from "react";
import { toast } from "sonner";
import {
  UploadCloud,
  FileText,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ArrowRight,
  RefreshCw,
  Info,
  Clock,
  Layers,
} from "lucide-react";
import { ingestIncident, USE_MOCK } from "@/api";
import type { EventRecord, SourceType } from "@/types/api";
import { SourceBadge } from "@/components/SourceBadge";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/import")({
  head: () => ({
    meta: [
      { title: "Import Collection — Incident Investigator" },
      { name: "description", content: "Import and validate incident JSON or JSONL event records." },
    ],
  }),
  component: ImportPage,
});

interface FileValidationResult {
  fileName: string;
  totalRecords: number;
  validCount: number;
  invalidCount: number;
  errors: string[];
  validEvents: EventRecord[];
}

const VALID_SOURCE_TYPES: SourceType[] = ["slack", "monitoring_alert", "deployment_log"];

function validateRecord(raw: any, index: number, seenIds: Set<string>): { valid: boolean; record?: EventRecord; error?: string } {
  if (!raw || typeof raw !== "object") {
    return { valid: false, error: `Record #${index + 1}: Not a valid JSON object` };
  }

  const { source_id, timestamp, source_type, author_or_actor, channel_or_service, summary, raw_content } = raw;

  if (!source_id || typeof source_id !== "string" || !source_id.trim()) {
    return { valid: false, error: `Record #${index + 1}: Missing or invalid source_id` };
  }

  if (seenIds.has(source_id)) {
    return { valid: false, error: `Record #${index + 1} (${source_id}): Duplicate source_id detected` };
  }

  if (!timestamp || typeof timestamp !== "string" || isNaN(new Date(timestamp).getTime())) {
    return { valid: false, error: `Record #${index + 1} (${source_id}): Invalid ISO-8601 timestamp` };
  }

  if (!source_type || !VALID_SOURCE_TYPES.includes(source_type as SourceType)) {
    return {
      valid: false,
      error: `Record #${index + 1} (${source_id}): Invalid source_type '${source_type}'. Must be slack, monitoring_alert, or deployment_log`,
    };
  }

  if (!author_or_actor || typeof author_or_actor !== "string") {
    return { valid: false, error: `Record #${index + 1} (${source_id}): Missing author_or_actor` };
  }

  if (!channel_or_service || typeof channel_or_service !== "string") {
    return { valid: false, error: `Record #${index + 1} (${source_id}): Missing channel_or_service` };
  }

  if (!summary || typeof summary !== "string") {
    return { valid: false, error: `Record #${index + 1} (${source_id}): Missing summary` };
  }

  if (!raw_content || typeof raw_content !== "string") {
    return { valid: false, error: `Record #${index + 1} (${source_id}): Missing raw_content` };
  }

  seenIds.add(source_id);

  const cleanRecord: EventRecord = {
    source_id: source_id.trim(),
    incident_id: typeof raw.incident_id === "string" ? raw.incident_id.trim() : "",
    timestamp: new Date(timestamp).toISOString(),
    source_type: source_type as SourceType,
    author_or_actor: author_or_actor.trim(),
    channel_or_service: channel_or_service.trim(),
    summary: summary.trim(),
    raw_content: raw_content.trim(),
    structured_payload: raw.structured_payload,
    tags: Array.isArray(raw.tags) ? raw.tags : undefined,
  };

  return { valid: true, record: cleanRecord };
}

function parseFileContent(text: string, fileName: string, seenIds: Set<string>): FileValidationResult {
  const errors: string[] = [];
  const validEvents: EventRecord[] = [];
  let items: any[] = [];

  const trimmed = text.trim();
  if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
    try {
      items = JSON.parse(trimmed);
      if (!Array.isArray(items)) {
        errors.push("Top-level JSON is not an array of event objects.");
      }
    } catch (e) {
      errors.push(`JSON syntax error: ${(e as Error).message}`);
    }
  } else {
    // Treat as JSONL
    const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
    lines.forEach((line, idx) => {
      try {
        items.push(JSON.parse(line));
      } catch (e) {
        errors.push(`Line ${idx + 1}: Malformed JSON line`);
      }
    });
  }

  items.forEach((item, idx) => {
    const res = validateRecord(item, idx, seenIds);
    if (res.valid && res.record) {
      validEvents.push(res.record);
    } else if (res.error) {
      if (errors.length < 5) {
        errors.push(res.error);
      }
    }
  });

  return {
    fileName,
    totalRecords: items.length,
    validCount: validEvents.length,
    invalidCount: items.length - validEvents.length,
    errors,
    validEvents,
  };
}

function ImportPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [incidentId, setIncidentId] = useState("INC-2026-043");
  const [incidentTitle, setIncidentTitle] = useState("");
  const [fileResults, setFileResults] = useState<FileValidationResult[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [successResult, setSuccessResult] = useState<{ count: number; incidentId: string } | null>(null);

  const handleFiles = useCallback((files: FileList | File[]) => {
    setSuccessResult(null);
    const seenIds = new Set<string>();
    const results: FileValidationResult[] = [];
    let pending = files.length;

    if (pending === 0) return;

    Array.from(files).forEach((file) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = (e.target?.result as string) || "";
        const res = parseFileContent(text, file.name, seenIds);
        results.push(res);
        pending--;
        if (pending === 0) {
          setFileResults(results);

          // Auto-detect incident_id if available from first valid event
          const firstWithId = results.flatMap((r) => r.validEvents).find((ev) => ev.incident_id);
          if (firstWithId?.incident_id) {
            setIncidentId(firstWithId.incident_id);
          }
        }
      };
      reader.readAsText(file);
    });
  }, []);

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(true);
  };

  const onDragLeave = () => {
    setDragActive(false);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const totalValidRecords = fileResults.reduce((sum, r) => sum + r.validCount, 0);
  const allValidEvents = fileResults.flatMap((r) => r.validEvents);
  const previewEvents = allValidEvents.slice(0, 5);

  const handleIngest = async () => {
    const cleanId = incidentId.trim();
    if (!cleanId || totalValidRecords === 0 || ingesting) return;

    setIngesting(true);
    try {
      const res = await ingestIncident({
        incident_id: cleanId,
        events: allValidEvents,
        title: incidentTitle.trim() || undefined,
      });

      setSuccessResult({
        count: res.ingested_count,
        incidentId: cleanId,
      });

      toast.success(`${res.ingested_count} events ingested successfully!`);
      window.dispatchEvent(new CustomEvent("investigations-updated"));
    } catch (e) {
      toast.error("Ingestion failed", { description: (e as Error).message });
    } finally {
      setIngesting(false);
    }
  };

  const handleReset = () => {
    setFileResults([]);
    setSuccessResult(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">Import Incident Collection</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Validate and ingest incident logs, alerts, and chat records into the timeline repository.
          </p>
        </div>
        <span className="rounded border px-2 py-0.5 font-mono text-[10px] uppercase text-muted-foreground">
          {USE_MOCK ? "mock storage" : "live backend"}
        </span>
      </div>

      {/* Backend Format Notice */}
      <div className="rounded-lg border border-primary/25 bg-primary/5 p-3.5 text-xs text-foreground/90 flex items-start gap-2.5">
        <Info className="size-4 text-primary shrink-0 mt-0.5" />
        <div>
          <strong className="text-primary font-semibold">Strict Format Requirement:</strong>
          <p className="mt-0.5 text-muted-foreground">
            The backend engine accepts only <strong>JSON arrays</strong> (e.g. <code className="text-xs bg-muted px-1 py-0.5 rounded">[&#123;...&#125;]</code>) or <strong>JSONL</strong> (newline-delimited JSON objects). All timestamps must be ISO-8601 UTC.
          </p>
        </div>
      </div>

      {/* Incident Metadata Form */}
      <div className="panel p-5 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1">
            Incident ID <span className="text-destructive">*</span>
          </label>
          <input
            type="text"
            value={incidentId}
            onChange={(e) => setIncidentId(e.target.value)}
            placeholder="e.g. INC-2026-043"
            className="field w-full font-mono text-xs"
            disabled={ingesting}
          />
          <p className="text-[10px] text-muted-foreground mt-1">Unique key used to group events and pre-filter searches.</p>
        </div>

        <div>
          <label className="block text-xs font-semibold text-foreground mb-1">
            Incident Title <span className="text-muted-foreground font-normal">(optional)</span>
          </label>
          <input
            type="text"
            value={incidentTitle}
            onChange={(e) => setIncidentTitle(e.target.value)}
            placeholder="e.g. Payment Gateway Failure Post Release"
            className="field w-full text-xs"
            disabled={ingesting}
          />
          <p className="text-[10px] text-muted-foreground mt-1">Human-friendly title shown in timeline headers.</p>
        </div>
      </div>

      {/* Drag & Drop File Picker */}
      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        className={cn(
          "panel p-8 text-center border-2 border-dashed transition-all cursor-pointer",
          dragActive
            ? "border-primary bg-primary/10"
            : "border-border/80 hover:border-primary/50 hover:bg-card/70"
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".json,.jsonl"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
          className="hidden"
        />
        <UploadCloud className="mx-auto size-10 text-muted-foreground mb-2" />
        <h3 className="text-sm font-semibold text-foreground">
          Drop .json or .jsonl incident files here, or click to browse
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          Supports multiple files simultaneously with client-side syntax and schema verification.
        </p>
      </div>

      {/* Validation Results Table per file */}
      {fileResults.length > 0 && (
        <div className="panel p-5 space-y-4">
          <div className="flex items-center justify-between border-b pb-3">
            <h3 className="text-sm font-semibold text-foreground">File Validation Report</h3>
            <button
              onClick={handleReset}
              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
            >
              <RefreshCw className="size-3" /> Clear files
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="pb-2 font-medium">File Name</th>
                  <th className="pb-2 font-medium">Total</th>
                  <th className="pb-2 font-medium">Valid</th>
                  <th className="pb-2 font-medium">Invalid</th>
                  <th className="pb-2 font-medium">Validation Issues</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {fileResults.map((r, i) => (
                  <tr key={i} className="hover:bg-accent/30">
                    <td className="py-2.5 font-medium flex items-center gap-1.5 font-mono">
                      <FileText className="size-3.5 text-muted-foreground" />
                      {r.fileName}
                    </td>
                    <td className="py-2.5 font-mono">{r.totalRecords}</td>
                    <td className="py-2.5 font-mono text-emerald-400">
                      <span className="inline-flex items-center gap-1">
                        <CheckCircle2 className="size-3" />
                        {r.validCount}
                      </span>
                    </td>
                    <td className="py-2.5 font-mono text-destructive">
                      {r.invalidCount > 0 ? (
                        <span className="inline-flex items-center gap-1">
                          <XCircle className="size-3" />
                          {r.invalidCount}
                        </span>
                      ) : (
                        "0"
                      )}
                    </td>
                    <td className="py-2.5 text-muted-foreground">
                      {r.errors.length === 0 ? (
                        <span className="text-emerald-400/90 font-medium">Schema verified</span>
                      ) : (
                        <ul className="list-disc list-inside space-y-0.5 text-destructive/90 text-[11px]">
                          {r.errors.map((err, errIdx) => (
                            <li key={errIdx}>{err}</li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Preview First 5 Valid Events */}
      {previewEvents.length > 0 && (
        <div className="panel p-5 space-y-3">
          <div className="flex items-center justify-between border-b pb-2">
            <h3 className="text-sm font-semibold text-foreground">Preview Valid Records</h3>
            <span className="text-xs text-muted-foreground font-mono">
              Showing first {previewEvents.length} of {totalValidRecords} valid records
            </span>
          </div>

          <div className="space-y-2">
            {previewEvents.map((e) => (
              <div
                key={e.source_id}
                className="rounded-md border border-border/60 p-2.5 bg-card/40 flex flex-wrap items-center justify-between gap-2"
              >
                <div className="flex items-center gap-2">
                  <SourceBadge type={e.source_type} />
                  <span className="font-mono text-xs font-semibold text-foreground">{e.source_id}</span>
                  <span className="text-xs text-muted-foreground truncate max-w-md">{e.summary}</span>
                </div>
                <div className="flex items-center gap-3 text-[11px] text-muted-foreground font-mono">
                  <span>{e.channel_or_service}</span>
                  <span>{new Date(e.timestamp).toISOString().slice(11, 19)}Z</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Success State Box */}
      {successResult && (
        <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="size-6 text-emerald-400 shrink-0" />
            <div>
              <h4 className="text-sm font-semibold text-foreground">
                {successResult.count} events ingested successfully!
              </h4>
              <p className="text-xs text-muted-foreground mt-0.5">
                Collection {successResult.incidentId} is ready for deterministic timeline reconstruction and cited queries.
              </p>
            </div>
          </div>
          <Link
            to="/investigate/$incidentId"
            params={{ incidentId: successResult.incidentId }}
            className="inline-flex items-center gap-1.5 rounded-md bg-emerald-500 px-4 py-2 text-xs font-semibold text-black transition-colors hover:bg-emerald-400"
          >
            Open Investigation
            <ArrowRight className="size-3.5" />
          </Link>
        </div>
      )}

      {/* Action Footer Button */}
      <div className="flex items-center justify-end gap-3 pt-2">
        <button
          onClick={handleIngest}
          disabled={totalValidRecords === 0 || !incidentId.trim() || ingesting}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed focus-ring"
        >
          {ingesting ? (
            <>
              <RefreshCw className="size-3.5 animate-spin" />
              Ingesting records…
            </>
          ) : (
            <>
              Ingest {totalValidRecords > 0 ? `${totalValidRecords} Events` : "Collection"}
              <ArrowRight className="size-3.5" />
            </>
          )}
        </button>
      </div>
    </div>
  );
}

