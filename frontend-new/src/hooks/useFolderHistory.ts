"use client";

import { useCallback, useEffect, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * The open gallery folder lives in the URL (`?group=<id>`).
 *
 * Deriving the folder from `useSearchParams` — rather than mirroring it into
 * component state — is what makes the *browser's* back button work for free:
 * Next intercepts popstate, updates the params, and the folder closes exactly
 * like the on-screen Back button. Deep links (`/gallery?group=x`) also work on
 * first load with no history to rewind.
 */
export function useFolderHistory(options: {
  /** Called whenever the folder id changes (open, close, browser back/forward). */
  onGroupIdChange?: (groupId: string | null) => void;
  /**
   * Once the group list has loaded, a URL pointing at a folder that no longer
   * exists (deleted in another tab, stale bookmark) is corrected in place.
   */
  knownGroupIds?: string[] | null;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const groupId = searchParams.get("group");

  /** True once *we* pushed a folder entry — i.e. browser-back is safe. */
  const pushedRef = useRef(false);

  const { onGroupIdChange, knownGroupIds } = options;

  useEffect(() => {
    onGroupIdChange?.(groupId);
  }, [groupId, onGroupIdChange]);

  // Stale/unknown folder in the URL → quietly return to the top level.
  useEffect(() => {
    if (!groupId || !knownGroupIds) return;
    if (!knownGroupIds.includes(groupId)) {
      pushedRef.current = false;
      router.replace(pathname, { scroll: false });
    }
  }, [groupId, knownGroupIds, pathname, router]);

  const openFolder = useCallback(
    (id: string) => {
      pushedRef.current = true;
      router.push(`${pathname}?group=${encodeURIComponent(id)}`, { scroll: false });
    },
    [router, pathname]
  );

  /**
   * The in-page Back button. Rewind history when the folder was opened from
   * here; when the URL was *loaded* with `?group=` (nothing of ours to rewind)
   * fall back to a replace so the button can never leave the site.
   */
  const closeFolder = useCallback(() => {
    if (pushedRef.current) {
      pushedRef.current = false;
      router.back();
    } else {
      router.replace(pathname, { scroll: false });
    }
  }, [router, pathname]);

  /** Leave the folder without touching history (e.g. the folder was deleted). */
  const resetFolder = useCallback(() => {
    pushedRef.current = false;
    router.replace(pathname, { scroll: false });
  }, [router, pathname]);

  return { groupId, openFolder, closeFolder, resetFolder };
}
