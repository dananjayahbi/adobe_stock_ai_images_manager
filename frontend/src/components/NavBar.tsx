"use client";

import { ChevronDown, Table2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";
import { ALL_STAGE_META } from "@/lib/stageMeta";

import StageProgressRail from "./shell/StageProgressRail";

/** Routes that are not stages but still deserve a nav entry. */
const UTILITY_ITEMS = [{ href: "/upload-table", label: "Upload Table", icon: Table2 }];

/**
 * Application header.
 *
 * Full-bleed (no `max-w-*`) and stage-driven: the seven stages are real routes,
 * not tabs. Below `lg` the stage strip collapses into a disclosure menu so the
 * header never wraps into two rows on small screens.
 */
export default function NavBar() {
  const pathname = usePathname();
  const [isMenuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close the compact menu whenever the route changes.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!isMenuOpen) return;

    function onPointerDown(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [isMenuOpen]);

  const activeMeta =
    ALL_STAGE_META.find((meta) => pathname.startsWith(`/stages/${meta.slug}`)) ?? null;

  return (
    <header className="sticky top-0 z-40 border-b border-navy-700/50 bg-navy-900/80 backdrop-blur-xl">
      <div className="flex w-full items-center gap-4 px-4 py-3 sm:px-6 lg:px-8 xl:px-10">
        <Link href="/" className="flex shrink-0 items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent-sheen text-[13px] font-bold text-navy-950 shadow-glow-sm">
            AS
          </span>
          <span className="hidden text-sm font-semibold tracking-tight text-navy-50 sm:block">
            Adobe Stock <span className="text-navy-400">AI Image Studio</span>
          </span>
        </Link>

        {/* Full stage strip — the primary navigation on large screens. */}
        <div className="ml-2 hidden min-w-0 flex-1 lg:block">
          <StageProgressRail />
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          {UTILITY_ITEMS.map((item) => {
            const isActive = pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "hidden items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors duration-150 sm:inline-flex",
                  isActive
                    ? "bg-accent-500/15 text-accent-200"
                    : "text-navy-300 hover:bg-navy-750/70 hover:text-navy-100"
                )}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden />
                {item.label}
              </Link>
            );
          })}

          {/* Compact stage switcher below `lg`. */}
          <div className="relative lg:hidden" ref={menuRef}>
            <button
              type="button"
              onClick={() => setMenuOpen((open) => !open)}
              aria-expanded={isMenuOpen}
              aria-haspopup="menu"
              className="inline-flex items-center gap-2 rounded-lg border border-navy-700/60 bg-navy-800/60 px-3 py-1.5 text-xs font-medium text-navy-100 transition-colors hover:bg-navy-750"
            >
              <span className="tabular-nums text-accent-400">
                {activeMeta ? activeMeta.number : "—"}
              </span>
              <span className="max-w-[9rem] truncate">
                {activeMeta ? activeMeta.name : "Stages"}
              </span>
              <ChevronDown
                className={cn("h-3.5 w-3.5 transition-transform", isMenuOpen && "rotate-180")}
                aria-hidden
              />
            </button>

            {isMenuOpen ? (
              <div
                role="menu"
                className="absolute right-0 top-full z-50 mt-2 w-64 overflow-hidden rounded-xl border border-navy-700/60 bg-navy-900 p-1.5 shadow-raised"
              >
                {ALL_STAGE_META.map((meta) => {
                  const Icon = meta.icon;
                  const isActive = activeMeta?.slug === meta.slug;
                  return (
                    <Link
                      key={meta.slug}
                      href={`/stages/${meta.slug}`}
                      role="menuitem"
                      aria-current={isActive ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors",
                        isActive
                          ? "bg-accent-500/15 text-accent-100"
                          : "text-navy-200 hover:bg-navy-800"
                      )}
                    >
                      <span className="w-4 shrink-0 text-center text-[11px] font-semibold tabular-nums text-navy-500">
                        {meta.number}
                      </span>
                      <Icon className="h-4 w-4 shrink-0" aria-hidden />
                      <span className="truncate">{meta.name}</span>
                    </Link>
                  );
                })}
                <div className="my-1 border-t border-navy-800" />
                {UTILITY_ITEMS.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      role="menuitem"
                      className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-navy-200 transition-colors hover:bg-navy-800"
                    >
                      <Icon className="h-4 w-4 shrink-0" aria-hidden />
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </header>
  );
}
