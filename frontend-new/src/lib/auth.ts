/**
 * Auth API surface — the cookie-session contract in one typed place.
 *
 * `fetchMe` uses a dedicated axios call rather than the shared instance: the
 * shared interceptor flattens every failure into `Error(message)`, which would
 * lose the 401 status that distinguishes "not signed in" (return null) from a
 * backend outage (throw). 401 here is an expected answer, not an incident.
 */
import axios from "axios";

import { api, API_BASE_URL } from "./client";

export interface AuthUser {
  username: string;
}

/** Exchange credentials for the HttpOnly session cookie. Throws on 401. */
export async function loginUser(
  username: string,
  password: string
): Promise<AuthUser> {
  const { data } = await api.post<{ user: AuthUser }>("/api/auth/login", {
    username,
    password,
  });
  return data.user;
}

/** Clear the session cookie. The backend answers 200 even when already out. */
export async function logoutUser(): Promise<void> {
  await api.post("/api/auth/logout");
}

/**
 * The current session user, or `null` when there is none (401).
 *
 * Any other failure (network, 5xx) still throws so callers can tell a signed-out
 * state apart from "the backend is unreachable".
 */
export async function fetchMe(): Promise<AuthUser | null> {
  try {
    const { data } = await axios.get<{ user: AuthUser }>(
      `${API_BASE_URL}/api/auth/me`,
      { withCredentials: true, timeout: 15_000 }
    );
    return data.user;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      return null;
    }
    throw error;
  }
}
