import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
  Link,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { Sidebar } from "@/components/layout/sidebar";
import { TopBar } from "@/components/layout/top-bar";
import { CopilotPanel } from "@/components/layout/copilot-panel";
import { DemoOverlay } from "@/components/layout/demo-overlay";
import { AppProvider } from "@/lib/app-context";
import { Toaster } from "@/components/ui/sonner";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-gradient-mahindra">404</h1>
        <h2 className="mt-4 text-xl font-semibold">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          This module isn't part of the AI Command Center yet.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-full mahindra-gradient px-5 py-2 text-sm font-semibold text-white"
          >
            Back to Executive Overview
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="glass max-w-md rounded-2xl p-8 text-center">
        <h1 className="text-xl font-semibold">This page didn't load</h1>
        <p className="mt-2 text-sm text-muted-foreground">Something went wrong.</p>
        <div className="mt-6 flex justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="rounded-full mahindra-gradient px-4 py-2 text-sm font-semibold text-white"
          >
            Try again
          </button>
          <a href="/" className="rounded-full border border-white/10 px-4 py-2 text-sm">
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
      { title: "Mahindra AI Command Center" },
      {
        name: "description",
        content:
          "Predict. Explain. Simulate. Act. Learn. A closed-loop AI operating layer across Mahindra Auto, Finance, Logistics, Circularity, Renewables, Real Estate and Hospitality.",
      },
      { property: "og:title", content: "Mahindra AI Command Center" },
      {
        property: "og:description",
        content: "A closed-loop AI operating layer across the Mahindra Group.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
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
  return (
    <QueryClientProvider client={queryClient}>
      <AppProvider>
        <div className="min-h-screen">
          <Sidebar />
          <div className="lg:pl-64">
            <TopBar />
            <main className="p-4 md:p-6 lg:p-8">
              <Outlet />
            </main>
          </div>
          <CopilotPanel />
          <DemoOverlay />
          <Toaster theme="dark" position="top-right" richColors />
        </div>
      </AppProvider>
    </QueryClientProvider>
  );
}
