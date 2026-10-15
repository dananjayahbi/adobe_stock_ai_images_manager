"use client";

/**
 * The research stream hook.
 *
 * Owns one live turn: opens the SSE connection, feeds every event through the
 * reducer, and exposes the accumulated state. The reducer does the thinking;
 * this hook only manages the transport.
 *
 * Why `fetch` + `ReadableStream` rather than `EventSource`
 * -------------
 * `EventSource` reconnects automatically on *any* disconnect, including a normal
 * end of stream. That would restart the whole agent run — re-running every web
 * search — because the endpoint is a GET that starts work when it is called.
 * Reading the body directly gives explicit control: the stream ends when the
 * reader is done, and closing is a real abort.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { parseEvent, researchStreamUrl } from "@/lib/research";
import {
  initialState,
  reduceEvent,
  type ResearchStreamState,
} from "@/lib/researchStream";

export interface UseResearchStreamResult {
  state: ResearchStreamState;
  /** Send a message and stream the reply. Resolves when the stream ends. */
  send: (options: {
    runId: string;
    /** Omit to run the opening turn of a freshly created conversation. */
    message?: string;
    count?: number;
    validityCheck?: boolean;
  }) => Promise<void>;
  /** Abort the in-flight turn, if any. */
  stop: () => void;
  /** Clear the accumulated state, e.g. when starting a different thread. */
  reset: (next?: Partial<ResearchStreamState>) => void;
}

/** Parse one SSE frame's `data:` payload. */
function payloadOf(frame: string): string | null {
  const dataLines = frame
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice("data:".length).trimStart());
  return dataLines.length ? dataLines.join("\n") : null;
}

export function useResearchStream(): UseResearchStreamResult {
  const [state, setState] = useState<ResearchStreamState>(initialState);
  const controllerRef = useRef<AbortController | null>(null);

  // Abort an in-flight stream on unmount so navigating away does not leave a
  // reader looping over a body nobody consumes. The backend notices the
  // disconnect and stops the run — the cheapest available cancellation.
  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
    };
  }, []);

  const stop = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setState((current) => ({ ...current, isStreaming: false }));
  }, []);

  const reset = useCallback((next?: Partial<ResearchStreamState>) => {
    setState({ ...initialState(), ...next });
  }, []);

  const send = useCallback(
    async (options: {
      runId: string;
      message?: string;
      count?: number;
      validityCheck?: boolean;
    }) => {
      // A turn already in flight would interleave two transcripts; the backend
      // refuses it too, but stopping here keeps the UI consistent.
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      setState((current) => ({
        ...current,
        isStreaming: true,
        finished: false,
        // Cleared so a turn that ends without `run_finished` (an error) cannot
        // surface the *previous* turn's answer as its own.
        answer: "",
        error: "",
      }));

      let response: Response;
      try {
        response = await fetch(
          researchStreamUrl(options.runId, {
            message: options.message,
            count: options.count,
            validityCheck: options.validityCheck,
          }),
          {
            signal: controller.signal,
            headers: { Accept: "text/event-stream" },
            // Cross-origin to the API host — the session cookie rides along
            // only when credentials are included, or the stream 401s.
            credentials: "include",
          }
        );
      } catch (error) {
        if ((error as Error)?.name === "AbortError") return;
        setState((current) => ({
          ...current,
          isStreaming: false,
          finished: true,
          error: `Could not reach the backend: ${(error as Error).message}`,
        }));
        return;
      }

      if (!response.ok || !response.body) {
        // The backend answers a bad request with a JSON `detail`, so read it
        // rather than showing a bare status code.
        let detail = `HTTP ${response.status}`;
        try {
          const payload = await response.json();
          if (payload?.detail) detail = String(payload.detail);
        } catch {
          /* keep the status-code message */
        }
        setState((current) => ({
          ...current,
          isStreaming: false,
          finished: true,
          error: detail,
        }));
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // SSE frames are separated by a blank line; the final element is an
          // incomplete frame, kept in the buffer for the next chunk. The
          // terminal frame is `event: done\ndata: {}` — an empty payload with
          // no `type`, so `parseEvent` drops it and the reader's `done` ends
          // the loop.
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";

          for (const frame of frames) {
            const payload = payloadOf(frame);
            if (!payload) continue;
            let decoded: unknown;
            try {
              decoded = JSON.parse(payload);
            } catch {
              continue;
            }
            const event = parseEvent(decoded);
            if (!event) continue;
            setState((current) => reduceEvent(current, event));
          }
        }
      } catch (error) {
        if ((error as Error)?.name !== "AbortError") {
          setState((current) => ({
            ...current,
            isStreaming: false,
            finished: true,
            error: `The stream ended unexpectedly: ${(error as Error).message}`,
          }));
        }
      } finally {
        reader.releaseLock();
        if (controllerRef.current === controller) controllerRef.current = null;
        // A stream that ended without a terminal event must not leave the UI
        // spinning forever.
        setState((current) =>
          current.finished
            ? current
            : { ...current, isStreaming: false, finished: true }
        );
      }
    },
    []
  );

  return { state, send, stop, reset };
}
