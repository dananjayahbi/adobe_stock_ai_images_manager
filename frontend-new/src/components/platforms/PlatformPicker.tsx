"use client";

/**
 * The master platform picker: hero + the full catalog as cards.
 *
 * Session-aware because it is the app's landing page — while the /me check
 * runs it shows a skeleton rather than bouncing a valid session to /login,
 * and an unauthenticated arrival is replaced (not pushed) so Back never
 * returns to a page that would only redirect again.
 */
import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth/AuthProvider";
import { PLATFORMS } from "@/lib/platforms";
import PlatformCard from "@/components/platforms/PlatformCard";

export default function PlatformPicker() {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div aria-busy="true" className="space-y-6">
        <div className="frame-card h-44 animate-pulse" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <div className="frame-card h-44 animate-pulse" />
          <div className="frame-card h-44 animate-pulse" />
        </div>
      </div>
    );
  }

  if (status === "unauthenticated") {
    return null;
  }

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden frame-card px-6 py-10 text-center sm:py-14">
        <p className="label-caps">AI Stock Studio</p>
        <h1 className="mt-3 font-display text-4xl leading-tight text-ink-800 sm:text-5xl">
          Where are today&apos;s images going?
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-lg leading-relaxed text-ink-400">
          One studio, every marketplace — pick a destination and the pipeline
          follows.
        </p>

        {/* Corner flourishes, like an engraved certificate. */}
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
      </section>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {PLATFORMS.map((platform) => (
          <PlatformCard key={platform.id} platform={platform} />
        ))}
      </div>
    </div>
  );
}
