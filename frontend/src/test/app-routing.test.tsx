import { QueryClient } from "@tanstack/react-query";
import { createRouter, rootRouteId } from "@tanstack/react-router";
import { describe, expect, it } from "vitest";

import { routeTree } from "@/routeTree.gen";

// Match routes without running loaders or rendering: loaders may need a server or
// network the test run lacks, and jsdom never loads the stylesheets React waits on.
describe("App routing", () => {
  const makeRouter = () =>
    createRouter({ routeTree, context: { queryClient: new QueryClient() } });

  it("matches a page for / (dashboard)", () => {
    const router = makeRouter();
    const matches = router.matchRoutes("/");
    expect(matches.at(-1)?.routeId).not.toBe(rootRouteId);
  });

  it("matches /dashboard route", () => {
    const router = makeRouter();
    const matches = router.matchRoutes("/dashboard");
    expect(matches.some((m) => m.routeId === "/dashboard")).toBe(true);
  });

  it("matches /investigate route", () => {
    const router = makeRouter();
    const matches = router.matchRoutes("/investigate");
    expect(matches.at(-1)?.routeId).not.toBe(rootRouteId);
  });

  it("matches /investigate/:incidentId route", () => {
    const router = makeRouter();
    const matches = router.matchRoutes("/investigate/INC-2026-042");
    expect(matches.some((m) => m.routeId === "/investigate/$incidentId")).toBe(true);
  });

  it("matches /import route", () => {
    const router = makeRouter();
    const matches = router.matchRoutes("/import");
    expect(matches.some((m) => m.routeId === "/import")).toBe(true);
  });
});
