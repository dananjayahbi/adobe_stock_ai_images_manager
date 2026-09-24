/**
 * Priority sources — the operator's own list of sites the agent should prefer.
 *
 * The general web search is a fallback chain, and a chain fails as a unit: when
 * the primary provider is rate-limited the agent gets editorial coverage instead
 * of the catalogue pages it needs. Measured live, a research run returned Google
 * News articles for every query and reported "0 of 16 stock marketplaces" — which
 * reads as an empty market but is really a search that never reached one.
 *
 * This module is the client for the upload, plus the shape of the stored list. It
 * deliberately does **not** parse the file: the file is the interface the operator
 * edits, so the server is the thing that reads it. A client-side parse would turn
 * a format error into a silent no-op.
 */

import { api, API_BASE_URL } from "./client";

/** One site the operator wants preferred. */
export interface PrioritySource {
  url: string;
  name: string;
  /** Lower is more important. */
  priority: number;
  notes: string;
  tags: string[];
}

export interface PrioritySourceFile {
  version: number;
  sources: PrioritySource[];
  /** Non-fatal remarks from the parser: entries dropped, fields trimmed. */
  warnings: string[];
  /** The uploaded file's name, for display. Empty when none is stored. */
  filename: string;
  template_version: number;
}

export async function fetchPrioritySources(): Promise<PrioritySourceFile> {
  const { data } = await api.get<PrioritySourceFile>("/api/research/sources");
  return data;
}

/**
 * Upload a source file's *text*.
 *
 * The text is sent verbatim rather than a parsed structure, so the server is the
 * only thing that decides whether a file is valid. A client that parsed first
 * would let a malformed file look like a successful upload with no sources.
 */
export async function uploadPrioritySources(
  content: string,
  filename: string
): Promise<PrioritySourceFile> {
  const { data } = await api.post<PrioritySourceFile>("/api/research/sources", {
    content,
    filename,
  });
  return data;
}

export async function clearPrioritySources(): Promise<PrioritySourceFile> {
  const { data } = await api.delete<PrioritySourceFile>("/api/research/sources");
  return data;
}

/** The URL of the downloadable template, so the anchor can point straight at it. */
export function sourceTemplateUrl(): string {
  return `${API_BASE_URL}/api/research/sources/template`;
}

/**
 * Download the template by fetching it and clicking a synthetic anchor.
 *
 * Not a plain `<a href download>`: the app is served from a different origin to
 * the API, and a cross-origin `download` attribute is ignored by browsers — the
 * file would open in a tab instead of saving. Fetching the body and using a
 * blob URL keeps the filename and works regardless of origin.
 */
export async function downloadSourceTemplate(): Promise<void> {
  const response = await fetch(sourceTemplateUrl());
  if (!response.ok) {
    throw new Error(`Could not download the template (HTTP ${response.status}).`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "research-priority-sources.json";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    // Revoked on the next tick: revoking synchronously can cancel the download in
    // some browsers before it has read the blob.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}

/**
 * The host of a source URL, for a compact display.
 *
 * Derived in the client for the same reason the backend has a `host` property:
 * the operator recognises "stock.adobe.com", not the full search URL.
 */
export function sourceHost(source: PrioritySource): string {
  try {
    return new URL(source.url).hostname.replace(/^www\./, "");
  } catch {
    return source.url;
  }
}
