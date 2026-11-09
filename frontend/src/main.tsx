import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as RTooltip from "@radix-ui/react-tooltip";
import { HashRouter } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./lib/auth";
import { applyTheme } from "./lib/prefs";
import { isApiError } from "./lib/errors";
import { ToastProvider } from "./components/Toast";
import { HelpPanelProvider } from "./components/HelpPanel";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components.css";
import "./styles/layout.css";
import "./styles/pages.css";
import "./styles/features.css";
import "./styles/smart.css";

applyTheme();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: true,
      // Retry once for flaky networks, never for "you're signed out" or "not found".
      retry: (count, error) => count < 1 && !(isApiError(error) && error.status >= 400 && error.status < 500),
    },
  },
});

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RTooltip.Provider>
          <ToastProvider>
            {/* Hash routes: several page names (/schedules, /settings) are also API addresses. */}
            <HashRouter>
              <HelpPanelProvider>
                <AuthProvider>
                  <App />
                </AuthProvider>
              </HelpPanelProvider>
            </HashRouter>
          </ToastProvider>
        </RTooltip.Provider>
      </QueryClientProvider>
    </StrictMode>,
  );
}
