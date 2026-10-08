"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** Site header: script wordmark + primary navigation, reference-style. */
export default function Header() {
  const pathname = usePathname();

  const navItems = [
    { href: "/", label: "Home" },
    { href: "/gallery", label: "Gallery" },
  ];

  return (
    <header className="sticky top-0 z-40 border-b border-parchment-400/70 bg-parchment-100/90 backdrop-blur-sm">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
        <Link href="/" className="group flex items-baseline gap-3">
          <span className="font-script text-3xl leading-none text-oxblood-500 transition-colors group-hover:text-oxblood-600">
            Batch Studio
          </span>
          <span className="label-caps hidden sm:inline">Adobe Stock Pipeline</span>
        </Link>

        <nav className="flex items-center gap-1">
          {navItems.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-sm px-3 py-1.5 font-stamp text-xs uppercase tracking-[0.14em] transition-colors ${
                  active
                    ? "bg-oxblood-500 text-parchment-50"
                    : "text-ink-600 hover:bg-parchment-200 hover:text-ink-800"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
      {/*双 rule — the reference's layered header line */}
      <div className="h-px bg-brass-400/50" />
      <div className="mt-[2px] h-px bg-parchment-400" />
    </header>
  );
}
