import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { listIncidents } from "@/api";
import { Skeleton } from "@/components/ui/skeleton";

export const Route = createFileRoute("/investigate/")({
  component: InvestigateIndex,
});

function InvestigateIndex() {
  const navigate = useNavigate();

  useEffect(() => {
    listIncidents()
      .then((list) => {
        const firstId = list[0]?.incident_id || "INC-2026-042";
        void navigate({
          to: "/investigate/$incidentId",
          params: { incidentId: firstId },
          replace: true,
        });
      })
      .catch(() => {
        void navigate({
          to: "/investigate/$incidentId",
          params: { incidentId: "INC-2026-042" },
          replace: true,
        });
      });
  }, [navigate]);

  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="w-full max-w-md space-y-3 text-center">
        <Skeleton className="h-4 w-3/4 mx-auto" />
        <Skeleton className="h-4 w-1/2 mx-auto" />
      </div>
    </div>
  );
}

