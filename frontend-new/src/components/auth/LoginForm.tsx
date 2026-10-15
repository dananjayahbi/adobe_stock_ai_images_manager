"use client";

/**
 * The sign-in form.
 *
 * Owns only form state; the session itself lives in AuthProvider, so a user
 * who arrives already authenticated (valid cookie) is redirected away by the
 * status effect below without a second /me round-trip.
 */
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import Button from "@/components/ui/Button";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  errorClass,
  inputClass,
  labelClass,
} from "@/components/prompts/fieldStyles";

export default function LoginForm() {
  const router = useRouter();
  const { status, login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // An authenticated arrival skips the form entirely (stale tab, back button).
  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/");
    }
  }, [status, router]);

  // While /me resolves the form stays out of the way — showing it and then
  // yanking it would flash credentials UI at a valid session.
  const checking = status === "loading";

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(username, password);
      router.push("/");
    } catch (err) {
      // The interceptor surfaces the backend's `detail` verbatim
      // (e.g. "Invalid credentials").
      setError(err instanceof Error ? err.message : "Sign in failed.");
      setPending(false);
    }
  }

  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4 py-8">
      <div className="frame-card relative w-full max-w-md overflow-hidden px-6 py-9 sm:px-8">
        <p className="text-center font-script text-4xl leading-none text-oxblood-400">
          AI Stock Studio
        </p>
        <h1 className="mt-3 text-center font-display text-3xl text-ink-800">
          Sign in
        </h1>
        <p className="label-caps mt-3 text-center">Local session · one seat</p>

        <div className="divider-dashed mt-6" />

        {checking ? (
          <p
            aria-busy="true"
            className="label-caps mt-6 text-center leading-relaxed"
          >
            Checking session…
          </p>
        ) : (
          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div>
              <label htmlFor="username" className={labelClass}>
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                className={inputClass}
              />
            </div>

            <div>
              <label htmlFor="password" className={labelClass}>
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className={inputClass}
              />
            </div>

            {error && (
              <p role="alert" className={errorClass}>
                {error}
              </p>
            )}

            <Button
              type="submit"
              size="lg"
              className="w-full"
              loading={pending}
              disabled={pending}
            >
              Sign in
            </Button>
          </form>
        )}

        <div className="divider-dashed mt-7" />
        <p className="label-caps mt-4 leading-relaxed">
          Local install — credentials are set in .env (AUTH_USERNAME /
          AUTH_PASSWORD)
        </p>

        {/* Corner flourishes, matching the certificate heroes. */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-3 font-script text-3xl text-brass-400/50"
        >
          ✦
        </span>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-3 right-3 font-script text-3xl text-brass-400/50"
        >
          ✦
        </span>
      </div>
    </div>
  );
}
