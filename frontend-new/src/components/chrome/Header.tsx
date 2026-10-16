"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/auth/AuthProvider";

/**
 * Site header: script wordmark + contextual chrome, reference-style.
 *
 * Product nav only appears inside a platform pipeline (Adobe Stock today) —
 * master and coming-soon pages carry their own wayfinding, so the header
 * there is just brand + session. The user cluster renders only once the
 * session is confirmed, keeping the loading state layout-stable.
 */
export default function Header() {
  const pathname = usePathname();
  const { status, user, logout } = useAuth();

  const onPipeline = pathname.startsWith("/adobe-stock");
  const onLogin = pathname === "/login";

  // Root item is active only on an exact match — /adobe-stock/gallery must
  // not light up "Home".
  const navItems = [
    { href: "/adobe-stock", label: "Home", exact: true },
    { href: "/adobe-stock/gallery", label: "Gallery", exact: false },
    { href: "/adobe-stock/prompts", label: "Prompts", exact: false },
    { href: "/adobe-stock/settings", label: "Config", exact: false },
  ];

  const showNav = onPipeline && !onLogin;
  const showUser = status === "authenticated" && !!user && !onLogin;

  return (
    <header className="sticky top-0 z-40 safe-top border-b border-parchment-400/70 bg-parchment-100/90 backdrop-blur-sm">
      {/* Two bands on narrow screens (brand+session, then nav), one row from lg. */}
      <div className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 sm:px-6 lg:flex-nowrap lg:px-8 xl:px-10">
        <Link
          href="/"
          className="group mr-auto flex min-w-0 items-baseline gap-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400"
        >
          <span className="whitespace-nowrap font-script text-2xl leading-none text-oxblood-400 transition-colors group-hover:text-oxblood-300 sm:text-3xl">
            AI Stock Studio
          </span>
          <span className="label-caps hidden whitespace-nowrap sm:inline">
            {onPipeline ? "Adobe Stock Pipeline" : "Universal Pipeline"}
          </span>
        </Link>

        {showNav && (
          <nav
            aria-label="Adobe Stock"
            className="order-last flex w-full min-w-0 flex-wrap items-center gap-1 overflow-x-auto pb-0.5 lg:order-none lg:w-auto lg:flex-nowrap lg:overflow-visible lg:pb-0"
          >
            {navItems.map((item) => {
              const active = item.exact
                ? pathname === item.href
                : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`whitespace-nowrap rounded-sm px-2.5 py-1.5 font-stamp text-xs uppercase tracking-[0.14em] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400 sm:px-3 ${
                    active
                      ? "bg-oxblood-500 text-ink-50"
                      : "text-ink-600 hover:bg-parchment-200 hover:text-ink-800"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        )}

        {showUser && (
          <div className="flex items-center gap-2">
            <span className="label-caps hidden max-w-[10rem] truncate rounded-sm border border-parchment-400 px-2 py-1 lg:inline-block">
              {user.username}
            </span>
            <button
              type="button"
              onClick={() => void logout()}
              className="whitespace-nowrap rounded-sm px-2 py-1.5 font-stamp text-xs uppercase tracking-[0.14em] text-ink-600 transition-colors hover:text-oxblood-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400 sm:px-3"
            >
              Sign out
            </button>
          </div>
        )}
      </div>
      {/* Double rule — the reference's layered header line. */}
      <div className="h-px bg-brass-400/50" />
      <div className="mt-[2px] h-px bg-parchment-400" />
    </header>
  );
}
