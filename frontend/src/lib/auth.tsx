// Who is signed in, and whether this install still needs its first account.
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, onAuthProblem } from "./api";
import type { AuthStatus } from "./types";

export type AuthPhase = "loading" | "error" | "setup" | "signin" | "ready";

interface AuthValue {
  phase: AuthPhase;
  status?: AuthStatus;
  error: unknown;
  retry: () => void;
  refresh: () => Promise<unknown>;
  /** Login is off but accounts exist: anyone on the network can change things. */
  loginOff: boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthValue | null>(null);
export const AUTH_KEY = ["auth-status"] as const;

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: AUTH_KEY,
    queryFn: () => api.get<AuthStatus>("/auth/status", undefined, { timeoutMs: 10_000 }),
    staleTime: 60_000,
    retry: 1,
  });

  useEffect(
    () =>
      onAuthProblem(() => {
        void queryClient.invalidateQueries({ queryKey: AUTH_KEY });
      }),
    [queryClient],
  );

  const status = query.data;
  let phase: AuthPhase = "loading";
  if (query.isError && !status) phase = "error";
  else if (status) {
    const setupRequired = status.setup_required ?? !status.users_exist;
    if (setupRequired) phase = "setup";
    else if (status.auth_enabled && !status.authenticated) phase = "signin";
    else phase = "ready";
  }

  const value: AuthValue = {
    phase,
    status,
    error: query.error,
    retry: () => void query.refetch(),
    refresh: () => queryClient.invalidateQueries({ queryKey: AUTH_KEY }),
    loginOff: Boolean(status && !status.auth_enabled && status.users_exist),
    isAdmin: !status?.auth_enabled || status.user?.role === "admin",
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export interface SetupInput {
  username: string;
  password: string;
  display_name?: string;
}

/** Creates the first admin account and signs this browser in (POST /auth/setup, CONTRACTS §4). */
export async function createFirstAccount(input: SetupInput): Promise<void> {
  await api.post("/auth/setup", input, { quietAuth: true });
}

export async function signIn(username: string, password: string, remember: boolean): Promise<void> {
  await api.post("/auth/login", { username, password, remember_me: remember }, { quietAuth: true });
}

export async function signOut(): Promise<void> {
  await api.post("/auth/logout", {}, { quietAuth: true });
}
