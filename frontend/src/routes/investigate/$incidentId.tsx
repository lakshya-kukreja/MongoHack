import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { WifiOff, ChevronDown, Check } from "lucide-react";
import { BackendUnreachableError, USE_MOCK, listIncidents } from "@/api";
import type { IncidentSummary } from "@/types/api";
import type { Investigation } from "@/types/extra";
import { fetchInvestigations } from "@/lib/investigations";
import { TimelineView } from "@/components/TimelineView";
import { ChatInterface } from "@/components/ChatInterface";
import { EventDrawer } from "@/components/EventDrawer";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface InvestigateSearch {
  invId?: string;
  event?: string;
}

export const Route = createFileRoute("/investigate/$incidentId")({
  validateSearch: (search: Record<string, unknown>): InvestigateSearch => ({
    invId: typeof search["invId"] === "string" ? search["invId"] : undefined,
    event: typeof search["event"] === "string" ? search["event"] : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Investigate — Incident Timeline Investigator" },
      { name: "description", content: "Reconstruct timelines and ask grounded questions with verified citations." },
    ],
  }),
  component: InvestigatePage,
});

function InvestigatePage() {
  const { incidentId } = Route.useParams();
  const { invId, event: eventParam } = Route.useSearch();
  const navigate = useNavigate();

  const [incidents, setIncidents] = useState<IncidentSummary[] | null>(null);
  const [activeInvestigation, setActiveInvestigation] = useState<Investigation | null>(null);
  const [loadError, setLoadError] = useState<{ msg: string; unreachable: boolean } | null>(null);
  const [drawerId, setDrawerId] = useState<string | null>(eventParam || null);
  const [highlightId, setHighlightId] = useState<string | null>(eventParam || null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const load = useCallback(() => {
    setLoadError(null);
    listIncidents()
      .then((list) => {
        setIncidents(list);
      })
      .catch((e: Error) => {
        setLoadError({ msg: e.message, unreachable: e instanceof BackendUnreachableError });
        toast.error("Couldn't load incidents", { description: e.message });
      });
  }, []);

  useEffect(load, [load]);

  // Handle active investigation from search param
  useEffect(() => {
    if (invId) {
      fetchInvestigations()
        .then((all) => {
          const found = all.find((i) => i.id === invId);
          if (found) {
            setActiveInvestigation(found);
          }
        })
        .catch(() => {});
    } else {
      setActiveInvestigation(null);
    }
  }, [invId]);

  // Handle event highlighting from search param
  useEffect(() => {
    if (eventParam) {
      setHighlightId(eventParam);
      setDrawerId(eventParam);
      document.getElementById(`event-${eventParam}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [eventParam]);

  const onCite = useCallback((id: string) => {
    document.getElementById(`event-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlightId(id);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setHighlightId(null), 2500);
    setDrawerId(id);
  }, []);

  const incident = incidents?.find((i) => i.incident_id === incidentId) || incidents?.[0];

  const handleIncidentChange = (newId: string) => {
    void navigate({
      to: "/investigate/$incidentId",
      params: { incidentId: newId },
      search: {},
    });
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Top Header */}
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b px-5 py-2.5 shrink-0 bg-card/40">
        <div className="flex items-center gap-3">
          {incidents && incidents.length > 1 ? (
            <DropdownMenu>
              <DropdownMenuTrigger className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs font-semibold hover:bg-accent focus-ring">
                <span className="font-mono text-primary">{incident?.incident_id || incidentId}</span>
                <ChevronDown className="size-3.5 text-muted-foreground" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-56">
                {incidents.map((inc) => (
                  <DropdownMenuItem
                    key={inc.incident_id}
                    onClick={() => handleIncidentChange(inc.incident_id)}
                    className="flex items-center justify-between text-xs"
                  >
                    <span className="font-mono">{inc.incident_id}</span>
                    {inc.incident_id === incidentId && <Check className="size-3 text-primary" />}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <span className="font-mono text-xs font-semibold text-primary">{incident?.incident_id || incidentId}</span>
          )}
        </div>

        {incident && (
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="truncate max-w-sm text-foreground font-medium">{incident.title}</span>
            <span className="font-mono">{incident.event_count} events</span>
            <span className="font-mono">{incident.services_involved.join(", ")}</span>
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          {activeInvestigation && (
            <span className="rounded bg-secondary/80 px-2 py-0.5 text-[10px] text-muted-foreground">
              Case: <strong className="text-foreground">{activeInvestigation.analyst}</strong> ({activeInvestigation.status})
            </span>
          )}
          <span className="rounded border px-2 py-0.5 font-mono text-[10px] uppercase text-muted-foreground">
            {USE_MOCK ? "mock data" : "live api"}
          </span>
        </div>
      </header>

      {/* Main Content */}
      {loadError ? (
        <div className="flex flex-1 items-center justify-center p-6">
          <div className="panel max-w-md p-6 text-center">
            <WifiOff className="mx-auto size-6 text-muted-foreground" />
            <h2 className="mt-3 font-semibold">
              {loadError.unreachable ? "Can't reach the backend" : "Something went wrong"}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">{loadError.msg}</p>
            <button onClick={load} className="mt-4 rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-ring">
              Retry
            </button>
          </div>
        </div>
      ) : !incidents ? (
        <div className="grid flex-1 gap-4 p-4 lg:grid-cols-[3fr_2fr]">
          <Skeleton className="h-[60vh]" />
          <Skeleton className="h-[60vh]" />
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-[3fr_2fr] overflow-hidden">
          <TimelineView
            incidents={incidents}
            incidentId={incident?.incident_id || incidentId}
            onIncidentChange={handleIncidentChange}
            highlightId={highlightId}
            onSelectEvent={setDrawerId}
          />
          <ChatInterface
            incidentId={incident?.incident_id || incidentId}
            incidentTitle={incident?.title}
            initialInvestigation={activeInvestigation}
            onCite={onCite}
          />
        </div>
      )}

      <EventDrawer
        incidentId={incident?.incident_id || incidentId}
        sourceId={drawerId}
        onClose={() => setDrawerId(null)}
      />
    </div>
  );
}

