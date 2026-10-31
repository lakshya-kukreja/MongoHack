import { useEffect, useState, useCallback } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard,
  Search,
  FolderUp,
  ChevronLeft,
  ChevronRight,
  User,
  Clock,
  HelpCircle,
  AlertCircle,
  WifiOff,
  Sparkles,
} from "lucide-react";
import type { Investigation } from "@/types/extra";
import { fetchInvestigations, relTime } from "@/lib/investigations";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onCloseMobile?: () => void;
  className?: string;
}

export function Sidebar({ collapsed, onToggleCollapse, onCloseMobile, className }: SidebarProps) {
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;
  // Get active invId from query params
  const searchParams = new URLSearchParams(routerState.location.searchStr);
  const activeInvId = searchParams.get("invId");

  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "mine" | "others">("all");

  const loadData = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchInvestigations()
      .then((data) => {
        setInvestigations(data);
      })
      .catch((err: Error) => {
        setError(err.message || "Failed to load investigations");
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    loadData();
    const handleUpdate = () => loadData();
    window.addEventListener("investigations-updated", handleUpdate);
    return () => window.removeEventListener("investigations-updated", handleUpdate);
  }, [loadData]);

  const filtered = investigations.filter((inv) => {
    if (filter === "mine") return inv.is_mine;
    if (filter === "others") return !inv.is_mine;
    return true;
  });

  const isDashboardActive = currentPath === "/" || currentPath === "/dashboard";
  const isInvestigateActive = currentPath.startsWith("/investigate");
  const isImportActive = currentPath === "/import";

  return (
    <aside
      className={cn(
        "flex h-full flex-col border-r bg-card/60 backdrop-blur transition-all duration-300",
        collapsed ? "w-16" : "w-[260px]",
        className
      )}
    >
      {/* Top Header */}
      <div className="flex h-14 items-center justify-between border-b px-3">
        <Link
          to="/"
          onClick={onCloseMobile}
          className={cn("flex items-center gap-2.5 overflow-hidden", collapsed && "justify-center w-full")}
        >
          <div className="logo-mark shrink-0" />
          {!collapsed && (
            <span className="truncate text-sm font-semibold tracking-tight text-foreground">
              Incident Investigator
            </span>
          )}
        </Link>
        {!collapsed && (
          <button
            onClick={onToggleCollapse}
            className="hidden md:flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            title="Collapse sidebar"
            aria-label="Collapse sidebar"
          >
            <ChevronLeft className="size-4" />
          </button>
        )}
      </div>

      {/* Navigation Links */}
      <div className="space-y-1 p-2">
        {/* Dashboard */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              to="/"
              onClick={onCloseMobile}
              className={cn(
                "flex items-center gap-3 rounded-md px-2.5 py-2 text-xs font-medium transition-colors",
                isDashboardActive
                  ? "bg-primary/15 text-primary font-semibold"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
                collapsed && "justify-center px-0"
              )}
            >
              <LayoutDashboard className="size-4 shrink-0" />
              {!collapsed && <span>Dashboard</span>}
            </Link>
          </TooltipTrigger>
          {collapsed && <TooltipContent side="right">Dashboard</TooltipContent>}
        </Tooltip>

        {/* Investigate */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              to="/investigate"
              onClick={onCloseMobile}
              className={cn(
                "flex items-center gap-3 rounded-md px-2.5 py-2 text-xs font-medium transition-colors",
                isInvestigateActive
                  ? "bg-primary/15 text-primary font-semibold"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
                collapsed && "justify-center px-0"
              )}
            >
              <Search className="size-4 shrink-0" />
              {!collapsed && <span>Investigate</span>}
            </Link>
          </TooltipTrigger>
          {collapsed && <TooltipContent side="right">Investigate</TooltipContent>}
        </Tooltip>

        {/* Import collection */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              to="/import"
              onClick={onCloseMobile}
              className={cn(
                "flex items-center gap-3 rounded-md px-2.5 py-2 text-xs font-medium transition-colors",
                isImportActive
                  ? "bg-primary/15 text-primary font-semibold"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
                collapsed && "justify-center px-0"
              )}
            >
              <FolderUp className="size-4 shrink-0" />
              {!collapsed && <span>Import collection</span>}
            </Link>
          </TooltipTrigger>
          {collapsed && <TooltipContent side="right">Import collection</TooltipContent>}
        </Tooltip>
      </div>

      <div className="my-2 border-t" />

      {/* Recent investigations section */}
      {!collapsed ? (
        <div className="flex min-h-0 flex-1 flex-col px-3">
          <div className="flex items-center justify-between pb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Recent investigations
            </span>
            {/* Filter buttons: All, Mine, Others */}
            <div className="flex rounded-md bg-secondary/80 p-0.5 text-[10px]">
              {(["all", "mine", "others"] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFilter(f)}
                  className={cn(
                    "rounded px-1.5 py-0.5 capitalize transition-colors",
                    filter === f
                      ? "bg-primary text-primary-foreground font-medium"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          {/* List content */}
          <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
            {loading ? (
              <div className="space-y-2 py-3">
                <div className="h-14 animate-pulse rounded-md bg-muted/40" />
                <div className="h-14 animate-pulse rounded-md bg-muted/40" />
                <div className="h-14 animate-pulse rounded-md bg-muted/40" />
              </div>
            ) : error ? (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 p-2.5 text-center text-xs text-destructive">
                <WifiOff className="mx-auto mb-1 size-4 opacity-80" />
                <p>{error}</p>
                <button
                  onClick={loadData}
                  className="mt-1.5 underline hover:text-destructive/80"
                >
                  Retry
                </button>
              </div>
            ) : filtered.length === 0 ? (
              <div className="py-6 text-center text-xs text-muted-foreground">
                <AlertCircle className="mx-auto mb-1 size-4 opacity-50" />
                No {filter !== "all" ? filter : ""} investigations found.
              </div>
            ) : (
              filtered.map((inv) => {
                const isActive = activeInvId === inv.id;
                return (
                  <Tooltip key={inv.id}>
                    <TooltipTrigger asChild>
                      <Link
                        to="/investigate/$incidentId"
                        params={{ incidentId: inv.incident_id }}
                        search={{ invId: inv.id }}
                        onClick={onCloseMobile}
                        className={cn(
                          "group block rounded-md border p-2 text-left transition-all",
                          isActive
                            ? "border-primary bg-primary/10 shadow-sm"
                            : "border-border/60 bg-card/40 hover:border-border hover:bg-accent/60"
                        )}
                      >
                        <div className="flex items-start justify-between gap-1">
                          <span className="line-clamp-1 text-xs font-medium text-foreground group-hover:text-primary">
                            {inv.title}
                          </span>
                          {!inv.is_mine && (
                            <span className="shrink-0 text-muted-foreground/60" title="Demo dataset">
                              <Sparkles className="size-3 text-amber-500/70" />
                            </span>
                          )}
                        </div>

                        <div className="mt-1 flex items-center justify-between text-[10px] text-muted-foreground">
                          <span className="font-mono text-foreground/80">{inv.incident_id}</span>
                          <span
                            className={cn(
                              "inline-flex items-center rounded px-1 py-0.2 text-[9px] font-semibold uppercase",
                              inv.status === "completed"
                                ? "bg-emerald-500/15 text-emerald-400"
                                : "bg-amber-500/15 text-amber-400"
                            )}
                          >
                            {inv.status === "completed" ? "Completed" : "In progress"}
                          </span>
                        </div>

                        <div className="mt-1 flex items-center justify-between text-[10px] text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <User className="size-3" />
                            {inv.is_mine ? <strong className="text-foreground">You</strong> : inv.analyst}
                          </span>
                          <span className="flex items-center gap-1 font-mono">
                            <HelpCircle className="size-3" />
                            {inv.question_count} Qs
                          </span>
                          <span className="flex items-center gap-1 font-mono">
                            <Clock className="size-3" />
                            {relTime(inv.last_activity)}
                          </span>
                        </div>
                      </Link>
                    </TooltipTrigger>
                    {!inv.is_mine && (
                      <TooltipContent side="right">
                        Demo investigation by {inv.analyst}
                      </TooltipContent>
                    )}
                  </Tooltip>
                );
              })
            )}
          </div>
        </div>
      ) : (
        /* Collapsed Icon-Only View */
        <div className="flex flex-1 flex-col items-center gap-3 p-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={onToggleCollapse}
                className="flex size-9 items-center justify-center rounded-md border border-border/60 text-muted-foreground hover:bg-accent hover:text-foreground"
                aria-label="Expand sidebar"
              >
                <ChevronRight className="size-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">Expand sidebar</TooltipContent>
          </Tooltip>

          <div className="h-px w-6 bg-border" />

          {/* Quick icon indicator for recent investigations */}
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex size-8 items-center justify-center rounded-full bg-secondary text-xs text-muted-foreground">
                {investigations.length}
              </div>
            </TooltipTrigger>
            <TooltipContent side="right">
              {investigations.length} investigations
            </TooltipContent>
          </Tooltip>
        </div>
      )}

      {/* Footer / Toggle for collapsed mode on desktop */}
      {collapsed && (
        <div className="hidden border-t p-2 md:flex justify-center">
          <button
            onClick={onToggleCollapse}
            className="size-8 flex items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            title="Expand sidebar"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>
      )}
    </aside>
  );
}

