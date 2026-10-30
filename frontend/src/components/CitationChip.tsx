import { AlertTriangle } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function CitationChip({ id, unverified, onSelect }: { id: string; unverified?: boolean; onSelect: (id: string) => void }) {
  if (unverified) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0} className="chip chip-unverified">
            <AlertTriangle className="size-3" />
            {id}
          </span>
        </TooltipTrigger>
        <TooltipContent>Unverified citation: this source wasn't found in the incident records.</TooltipContent>
      </Tooltip>
    );
  }
  return (
    <button type="button" onClick={() => onSelect(id)} className="chip" aria-label={`Open source ${id}`}>
      {id}
    </button>
  );
}
