"use client";

/**
 * Session context for the whole app tree.
 *
 * Mounted once in the root layout so the header, the platform picker and the
 * login form all read the same state instead of each racing its own /me call.
 * `status` is explicit about the initial load: consumers render a skeleton
 * while `loading` rather than flashing the login redirect at a valid session.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";

import { fetchMe, loginUser, logoutUser, type AuthUser } from "@/lib/auth";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  user: AuthUser | null;
  status: AuthStatus;
  /** Throws the backend's detail (e.g. "Invalid credentials") for the form. */
  login: (username: string, password: string) => Promise<void>;
  /** Best-effort sign-out, then send the user to /login. */
  logout: () => Promise<void>;
  /** Re-check the session (initial mount, or after a stale-cookie 401). */
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  const refresh = useCallback(async () => {
    try {
      const me = await fetchMe();
      setUser(me);
      setStatus(me ? "authenticated" : "unauthenticated");
      if (!me) {
        // A 401 means a cookie survived the middleware's presence check but
        // the backend no longer honours it — clear it so the cookie gate
        // stops admitting a dead session on the next navigation.
        try {
          await logoutUser();
        } catch {
          /* already signed out; nothing to recover */
        }
      }
    } catch {
      // Backend unreachable: treat as signed out; login will surface the error.
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const next = await loginUser(username, password);
    setUser(next);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutUser();
    } catch {
      /* best-effort — local state clears regardless */
    }
    setUser(null);
    setStatus("unauthenticated");
    router.push("/login");
  }, [router]);

  const value = useMemo(
    () => ({ user, status, login, logout, refresh }),
    [user, status, login, logout, refresh]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Read the session. Throws if used outside <AuthProvider>. */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within <AuthProvider>");
  }
  return context;
}
