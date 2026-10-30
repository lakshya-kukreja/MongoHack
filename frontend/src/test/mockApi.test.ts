import { describe, expect, it } from "vitest";
import { getTimeline, listIncidents, queryIncident, QUICK_PROMPTS } from "@/mocks/mockApi";

const ID = "INC-2026-042";

describe("mock API", () => {
  it("returns timeline sorted ascending by timestamp", async () => {
    const r = await getTimeline(ID);
    const t = r.events.map((e) => new Date(e.timestamp).getTime());
    expect(t).toEqual([...t].sort((a, b) => a - b));
    expect(r.total_events).toBe(17);
  });

  it("treats both time bounds as inclusive", async () => {
    const r = await getTimeline(ID, { start_time: "2026-10-30T14:02:00Z", end_time: "2026-10-30T14:07:00Z" });
    expect(r.events.map((e) => e.source_id)).toEqual(["ALERT-201", "SLACK-301", "ALERT-202", "SLACK-302"]);
    expect(r.filtered_count).toBe(4);
  });

  it("filters by comma-separated source types", async () => {
    const r = await getTimeline(ID, { source_type: "deployment_log" });
    expect(r.events.map((e) => e.source_id)).toEqual(["DEPLOY-101", "DEPLOY-102"]);
  });

  it("lists the incident with the required title", async () => {
    const [i] = await listIncidents();
    expect(i?.title).toBe("Payment Gateway P99 Latency Spike & Cascading Connection Pool Exhaustion");
    expect(i?.event_count).toBe(17);
  });

  it("returns exact insufficient-evidence answer for unknown questions", async () => {
    const r = await queryIncident(ID, { query: "Did an expired SSL certificate on the Kubernetes ingress cause this outage?" });
    expect(r.answer).toBe("Based on the retrieved incident records, there is insufficient evidence to answer this question.");
    expect(r.citations).toEqual([]);
  });

  it("cites DEPLOY-101 for the deployment question", async () => {
    const r = await queryIncident(ID, { query: QUICK_PROMPTS[2] });
    expect(r.citations.map((c) => c.source_id)).toEqual(["DEPLOY-101"]);
  });
});
