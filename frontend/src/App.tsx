import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { Layout, Logo } from "./components/Layout";
import { ErrorNotice, Loading } from "./components/Notice";
import { SetupPage } from "./pages/auth/SetupPage";
import { SignInPage } from "./pages/auth/SignInPage";
import { HomePage } from "./pages/home/HomePage";

const VideosPage = lazy(() => import("./pages/videos/VideosPage"));
const SchedulesPage = lazy(() => import("./pages/schedules/SchedulesPage"));
const ScheduleWizard = lazy(() => import("./pages/schedules/ScheduleWizard"));
const RulesPage = lazy(() => import("./pages/rules/RulesPage"));
const RuleEditor = lazy(() => import("./pages/rules/RuleEditor"));
const NeverPlayPage = lazy(() => import("./pages/rules/NeverPlayPage"));
const StatsPage = lazy(() => import("./pages/stats/StatsPage"));
const ServersPage = lazy(() => import("./pages/servers/ServersPage"));
const ConnectPage = lazy(() => import("./pages/servers/ConnectPage"));
const HelpPage = lazy(() => import("./pages/help/HelpPage"));
const HelpArticlePage = lazy(() => import("./pages/help/HelpArticlePage"));
const TroubleshooterPage = lazy(() => import("./pages/help/TroubleshooterPage"));
const ReportPage = lazy(() => import("./pages/help/ReportPage"));
const SettingsPage = lazy(() => import("./pages/settings/SettingsPage"));
const AdvancedPage = lazy(() => import("./pages/settings/advanced/AdvancedPage"));
const PlaylistEditor = lazy(() => import("./pages/settings/advanced/playlists/PlaylistEditor"));
const OnboardingPage = lazy(() => import("./pages/onboarding/OnboardingPage"));

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function FullScreen({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth-screen">
      <div className="card auth-card">
        <div className="brand">
          <Logo size={40} />
          Prerolls Max
        </div>
        {children}
      </div>
    </div>
  );
}

export function App() {
  const { phase, error, retry } = useAuth();

  if (phase === "loading") {
    return (
      <FullScreen>
        <Loading label="Starting Prerolls Max…" />
      </FullScreen>
    );
  }
  if (phase === "error") {
    return (
      <FullScreen>
        <ErrorNotice error={error} onRetry={retry} />
      </FullScreen>
    );
  }
  if (phase === "setup") return <SetupPage />;
  if (phase === "signin") return <SignInPage />;

  return (
    <Suspense
      fallback={
        <div className="main-inner">
          <Loading />
        </div>
      }
    >
      <ScrollToTop />
      <Routes>
        <Route path="/welcome" element={<OnboardingPage />} />
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="videos/*" element={<VideosPage />} />
          <Route path="schedules" element={<SchedulesPage />} />
          <Route path="schedules/new" element={<ScheduleWizard />} />
          <Route path="schedules/:id/edit" element={<ScheduleWizard />} />
          <Route path="schedules/rules" element={<RulesPage />} />
          <Route path="schedules/rules/new" element={<RuleEditor />} />
          <Route path="schedules/rules/:id" element={<RuleEditor />} />
          <Route path="schedules/never-play" element={<NeverPlayPage />} />
          <Route path="played" element={<StatsPage />} />
          <Route path="servers" element={<ServersPage />} />
          <Route path="servers/:type" element={<ConnectPage />} />
          <Route path="help" element={<HelpPage />} />
          <Route path="help/troubleshoot" element={<TroubleshooterPage />} />
          <Route path="help/report" element={<ReportPage />} />
          <Route path="help/:slug" element={<HelpArticlePage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="settings/advanced/playlists/:id" element={<PlaylistEditor />} />
          <Route path="settings/advanced/:page" element={<AdvancedPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
