"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelInstall as cancelInstallRequest,
  fetchSetupStatus,
  probeSetup as probeSetupRequest,
  startInstall as startInstallRequest,
} from "@/lib/setup";
import type { ProbeResult, SetupStatus } from "@/lib/setup";

/** Cadence while an install runs — the operator is watching progress. */
const RUNNING_POLL_MS = 2000;
/** Cadence when idle — keeps config/installed state fresh without hammering. */
const IDLE_POLL_MS = 15000;

/**
 * Poll the server setup status.
 *
 * The cadence is derived from `status.running` and the interval is re-armed
 * when it flips (per the useBatchPolling lesson: a timer must *resume*, never
 * get stuck). Critically this hook is owned by the Config page, not the
 * install modal — closing the modal unmounts nothing here, so polling (and
 * the persistent indicator fed by `status`) keeps running for as long as the
 * page is mounted.
 *
 * Actions (`startInstall` / `cancelInstall` / `probeSetup`) optimistically
 * adopt the `SetupStatus` the POST returns, which both refreshes the view
 * immediately and re-arms the fast cadence without waiting for the next tick.
 */
export function useSetupStatus() {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [probing, setProbing] = useState(false);
  const [probe, setProbe] = useState<ProbeResult | null>(null);
  const requestId = useRef(0);

  const running = status?.running ?? false;

  const refresh = useCallback(async () => {
    const id = ++requestId.current;
    try {
      const data = await fetchSetupStatus();
      if (id !== requestId.current) return; // stale response — a newer id exists
      setStatus(data);
      setError(null);
    } catch (err) {
      if (id === requestId.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), running ? RUNNING_POLL_MS : IDLE_POLL_MS);
    return () => window.clearInterval(timer);
  }, [running, refresh]);

  const startInstall = useCallback(async (groups: string[]) => {
    setBusy(true);
    setError(null);
    try {
      const data = await startInstallRequest(groups);
      // A poll response already in flight predates this POST — invalidate it
      // so it cannot overwrite the adopted `running: true` (which would also
      // flip the interval back to the slow cadence until the next tick).
      requestId.current += 1;
      setStatus(data); // 202 body — running flips true, interval re-arms at 2s
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, []);

  const cancelInstall = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await cancelInstallRequest();
      requestId.current += 1; // same race guard as startInstall
      setStatus(data); // running flips false, interval re-arms at 15s
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, []);

  const doProbe = useCallback(async () => {
    setProbing(true);
    setError(null);
    try {
      const result = await probeSetupRequest();
      setProbe(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProbing(false);
    }
  }, []);

  return {
    status,
    refresh,
    startInstall,
    cancelInstall,
    probeSetup: doProbe,
    probe,
    probing,
    error,
    busy,
  };
}
