// The app frame: sidebar on desktop, top bar and bottom tabs on phones.
import { BarChart3, CalendarClock, Film, HelpCircle, Home, LogOut, Server, Settings, ShieldAlert } from "lucide-react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { signOut, useAuth } from "../lib/auth";
import { useToast } from "./Toast";
import { describeError } from "../lib/errors";

/**
 * The app's pages live in the address after "#", so a plain "#main" link
 * would leave the page for Home. Move focus to the content instead.
 */
export function SkipLink() {
  return (
    <a
      className="skip-link"
      href="#main"
      onClick={(e) => {
        e.preventDefault();
        document.getElementById("main")?.focus();
      }}
    >
      Skip to content
    </a>
  );
}

export function Logo({ size = 32 }: { size?: number }) {
  return <img src="/icons/logo.svg" width={size} height={size} alt="" aria-hidden="true" />;
}

const NAV = [
  { to: "/", label: "Home", short: "Home", icon: Home, end: true },
  { to: "/videos", label: "Intro Videos", short: "Videos", icon: Film },
  { to: "/schedules", label: "When They Play", short: "Schedule", icon: CalendarClock },
  { to: "/servers", label: "Media Servers", short: "Servers", icon: Server },
  { to: "/played", label: "What Played", short: "Played", icon: BarChart3, desktopOnly: true },
  { to: "/help", label: "Help", short: "Help", icon: HelpCircle },
  { to: "/settings", label: "Settings", short: "Settings", icon: Settings },
];

function SignOutButton() {
  const { status, refresh } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  if (!status?.auth_enabled || !status.authenticated) return null;
  const run = async () => {
    try {
      await signOut();
      navigate("/");
      await refresh();
      // Forget everything else the signed-in person could see.
      queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "auth-status" });
    } catch (error) {
      toast({ tone: "error", title: describeError(error).message });
    }
  };
  return (
    <button type="button" className="nav-link nav-button" onClick={run}>
      <LogOut size={20} aria-hidden="true" />
      Sign out
    </button>
  );
}

function LoginOffBanner() {
  const { loginOff } = useAuth();
  if (!loginOff) return null;
  return (
    <div className="banner" role="note">
      <ShieldAlert size={18} aria-hidden="true" />
      <span className="grow">Sign-in is turned off, so anyone on your network can change Prerolls Max.</span>
      <Link to="/settings#account">Turn it on</Link>
    </div>
  );
}

export function Layout() {
  const { status } = useAuth();
  const who = status?.user?.display_name || status?.user?.username || status?.display_name;
  return (
    <div className="shell">
      <SkipLink />
      <aside className="sidebar" aria-label="Main menu">
        <Link to="/" className="brand">
          <Logo />
          Prerolls Max
        </Link>
        <nav className="nav" aria-label="Sections">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className="nav-link">
              <Icon size={20} aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          {who && <span className="muted">Signed in as {who}</span>}
          <SignOutButton />
        </div>
      </aside>

      <header className="topbar">
        <Link to="/" className="brand">
          <Logo size={28} />
          Prerolls Max
        </Link>
        <NavLink to="/help" className="btn btn-ghost btn-icon" aria-label="Help">
          <HelpCircle size={22} aria-hidden="true" />
        </NavLink>
      </header>

      <main id="main" className="main" tabIndex={-1}>
        <LoginOffBanner />
        <div className="main-inner">
          <Outlet />
        </div>
      </main>

      <nav className="tabbar" aria-label="Sections">
        {NAV.filter((n) => n.to !== "/help" && !n.desktopOnly).map(({ to, short, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className="tab-link">
            <Icon size={22} aria-hidden="true" />
            {short}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
