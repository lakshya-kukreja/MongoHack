import { useEffect, useState } from "react";
import { getEvent } from "@/api";
import type { EventRecord } from "@/types/api";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { SourceBadge, alertSeverity } from "./SourceBadge";

function Value({ v }: { v: unknown }) {
  if (v !== null && typeof v === "object") return <code className="break-all font-mono text-xs">{JSON.stringify(v)}</code>;
  return <span className="break-all font-mono text-xs">{String(v)}</span>;
}

export function EventDrawer({ incidentId, sourceId, onClose }: { incidentId: string; sourceId: string | null; onClose: () => void }) {
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sourceId) return;
    let alive = true;
    setEvent(null); setError(null);
    getEvent(incidentId, sourceId).then((e) => alive && setEvent(e)).catch((e: Error) => alive && setError(e.message));
    return () => { alive = false; };
  }, [incidentId, sourceId]);

  return (
    <Sheet open={!!sourceId} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto border-l bg-card sm:max-w-md">
        <SheetHeader>
          <SheetTitle className="font-mono">{sourceId}</SheetTitle>
          <SheetDescription>{event ? event.summary : "Source event"}</SheetDescription>
        </SheetHeader>

        <div className="space-y-6 px-4 pb-6">
          {error && <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
          {!event && !error && (
            <div className="space-y-3"><Skeleton className="h-4 w-1/2" /><Skeleton className="h-4 w-2/3" /><Skeleton className="h-24 w-full" /></div>
          )}
          {event && (
            <>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">Time</dt><dd className="font-mono text-xs">{event.timestamp}</dd>
                <dt className="text-muted-foreground">Source</dt>
                <dd><SourceBadge type={event.source_type} severity={event.source_type === "monitoring_alert" ? alertSeverity(event.summary) : undefined} /></dd>
                <dt className="text-muted-foreground">Actor</dt><dd>{event.author_or_actor}</dd>
                <dt className="text-muted-foreground">Channel</dt><dd>{event.channel_or_service}</dd>
              </dl>
              <div>
                <h3 className="drawer-label">Raw content</h3>
                <pre className="whitespace-pre-wrap rounded-md border bg-background p-3 font-mono text-xs leading-relaxed">{event.raw_content}</pre>
              </div>
              {event.structured_payload && Object.keys(event.structured_payload).length > 0 && (
                <div>
                  <h3 className="drawer-label">Structured payload</h3>
                  <dl className="divide-y rounded-md border">
                    {Object.entries(event.structured_payload).map(([k, v]) => (
                      <div key={k} className="grid grid-cols-[8rem_1fr] gap-3 px-3 py-2">
                        <dt className="truncate text-xs text-muted-foreground">{k}</dt><dd><Value v={v} /></dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}
              {event.tags && event.tags.length > 0 && (
                <div>
                  <h3 className="drawer-label">Tags</h3>
                  <div className="flex flex-wrap gap-1.5">
                    {event.tags.map((t) => <span key={t} className="rounded border px-2 py-0.5 font-mono text-xs text-muted-foreground">{t}</span>)}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
