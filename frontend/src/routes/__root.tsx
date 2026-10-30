import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
  type ErrorComponentProps,
} from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";
import { Menu, X } from "lucide-react";

import appCss from "../styles.css?url";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { Sidebar } from "@/components/Sidebar";
import { USE_MOCK } from "@/api";

function NotFoundComponent() {
  return (
    <div className="flex flex-1 items-center justify-center p-6 bg-background">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The route you are looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Dashboard
          </Link>
          <Link
            to="/investigate"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Investigate
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: ErrorComponentProps) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          This page didn't load
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong on our end. You can try refreshing or head back home.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Incident Timeline Investigator" },
      { name: "description", content: "Investigate production incidents." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap",
      },
      { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={150}>
        <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
          {/* Desktop Left Sidebar */}
          <div className="hidden md:flex h-full shrink-0">
            <Sidebar
              collapsed={collapsed}
              onToggleCollapse={() => setCollapsed((c) => !c)}
            />
          </div>

          {/* Mobile Hamburger Drawer & Backdrop */}
          {mobileOpen && (
            <div className="fixed inset-0 z-50 flex md:hidden">
              <div
                className="fixed inset-0 bg-background/80 backdrop-blur-sm transition-opacity"
                onClick={() => setMobileOpen(false)}
              />
              <div className="relative z-10 flex h-full w-[280px] max-w-[85vw] flex-col bg-card shadow-2xl">
                <div className="absolute right-2 top-2 z-20">
                  <button
                    onClick={() => setMobileOpen(false)}
                    className="flex size-8 items-center justify-center rounded-md hover:bg-accent text-muted-foreground hover:text-foreground"
                    aria-label="Close menu"
                  >
                    <X className="size-4" />
                  </button>
                </div>
                <Sidebar
                  collapsed={false}
                  onToggleCollapse={() => {}}
                  onCloseMobile={() => setMobileOpen(false)}
                  className="w-full border-r-0"
                />
              </div>
            </div>
          )}

          {/* Main Area with Mobile Top Bar */}
          <div className="flex flex-1 flex-col min-w-0 h-full overflow-hidden">
            {/* Mobile Header */}
            <div className="flex h-12 items-center justify-between border-b px-4 md:hidden shrink-0 bg-card/60 backdrop-blur">
              <button
                onClick={() => setMobileOpen(true)}
                className="flex size-8 items-center justify-center rounded-md hover:bg-accent text-muted-foreground"
                aria-label="Open menu"
              >
                <Menu className="size-5" />
              </button>
              <span className="text-xs font-semibold">Incident Investigator</span>
              <span className="rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase text-muted-foreground">
                {USE_MOCK ? "mock" : "live"}
              </span>
            </div>

            {/* Page Content Outlet */}
            <main className="flex-1 min-h-0 overflow-y-auto">
              <Outlet />
            </main>
          </div>
        </div>
      </TooltipProvider>
      <Toaster theme="dark" />
    </QueryClientProvider>
  );
}
