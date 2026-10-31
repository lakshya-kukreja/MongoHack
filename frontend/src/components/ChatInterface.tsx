import { Fragment, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowUp, SearchX } from "lucide-react";
import { QUICK_PROMPTS, queryIncident } from "@/api";
import type { QueryResponse } from "@/types/api";
import type { Investigation } from "@/types/extra";
import { recordQuestion } from "@/lib/investigations";
import { Skeleton } from "@/components/ui/skeleton";
import { CitationChip } from "./CitationChip";

type Msg = { role: "user"; text: string } | { role: "assistant"; res: QueryResponse } | { role: "error"; text: string };

const TAG_RE = /\[([A-Z]+-\d+)\]/g;

function Answer({ res, onCite }: { res: QueryResponse; onCite: (id: string) => void }) {
  if (res.citations.length === 0) {
    return (
      <div className="insufficient">
        <SearchX className="mt-0.5 size-4 shrink-0" />
        <p>{res.answer}</p>
      </div>
    );
  }
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of res.answer.matchAll(TAG_RE)) {
    const id = m[1] ?? "";
    parts.push(res.answer.slice(last, m.index));
    parts.push(<CitationChip key={m.index} id={id} unverified={res.unverified_citations?.includes(id)} onSelect={onCite} />);
    last = (m.index ?? 0) + m[0].length;
  }
  parts.push(res.answer.slice(last));
  return <p className="text-sm leading-relaxed">{parts.map((p, i) => <Fragment key={i}>{p}</Fragment>)}</p>;
}

export function ChatInterface({
  incidentId,
  incidentTitle,
  initialInvestigation,
  onCite,
}: {
  incidentId: string;
  incidentTitle?: string;
  initialInvestigation?: Investigation | null;
  onCite: (id: string) => void;
}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, loading]);

  // Load saved questions when an investigation is opened
  useEffect(() => {
    if (initialInvestigation && initialInvestigation.questions && initialInvestigation.questions.length > 0) {
      const loadedMsgs: Msg[] = [];
      for (const q of initialInvestigation.questions) {
        loadedMsgs.push({ role: "user", text: q.query });
        loadedMsgs.push({
          role: "assistant",
          res: {
            answer: q.answer,
            citations: q.citations || [],
            unverified_citations: [],
            retrieved_events: [],
          },
        });
      }
      setMsgs(loadedMsgs);
    } else {
      setMsgs([]);
    }
  }, [incidentId, initialInvestigation?.id]);

  const ask = async (q: string) => {
    const query = q.trim();
    if (!query || loading || !incidentId) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", text: query }]);
    setLoading(true);
    try {
      const res = await queryIncident(incidentId, { query });
      setMsgs((m) => [...m, { role: "assistant", res }]);
      // Record question and update/create my investigation
      await recordQuestion(incidentId, incidentTitle || `Incident ${incidentId}`, query, res);
    } catch (e) {
      const msg = (e as Error).message;
      setMsgs((m) => [...m, { role: "error", text: msg }]);
      toast.error("Query failed", { description: msg });
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="panel flex min-h-0 flex-col">
      <div className="border-b p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Ask the incident</h2>
          {initialInvestigation && (
            <span className="font-mono text-[11px] text-muted-foreground">
              Case by {initialInvestigation.analyst}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground">Answers cite source events. Click a citation to inspect it.</p>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {msgs.length === 0 && (
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Suggested questions</p>
            {QUICK_PROMPTS.map((q) => (
              <button key={q} type="button" onClick={() => ask(q)} disabled={loading} className="quick-prompt">
                {q}
              </button>
            ))}
          </div>
        )}
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="bubble-user">{m.text}</div>
            </div>
          ) : m.role === "error" ? (
            <div key={i} className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              {m.text}
            </div>
          ) : (
            <div key={i}>
              <Answer res={m.res} onCite={onCite} />
            </div>
          ),
        )}
        {loading && (
          <div className="space-y-2" aria-label="Thinking">
            <Skeleton className="h-3 w-11/12" />
            <Skeleton className="h-3 w-4/5" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        )}
        <div ref={endRef} />
      </div>

      {msgs.length > 0 && (
        <div className="flex gap-2 overflow-x-auto border-t px-4 py-2">
          {QUICK_PROMPTS.map((q) => (
            <button key={q} type="button" onClick={() => ask(q)} disabled={loading} className="quick-prompt-sm">
              {q}
            </button>
          ))}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
        className="flex gap-2 border-t p-3"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this incident…"
          className="field flex-1"
          aria-label="Question"
        />
        <button type="submit" disabled={loading || !input.trim()} className="send-btn" aria-label="Send">
          <ArrowUp className="size-4" />
        </button>
      </form>
    </section>
  );
}
