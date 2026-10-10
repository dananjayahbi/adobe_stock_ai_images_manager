/** Typed API client + wire types for the server setup (`/api/setup`) endpoints. */
import { api } from "./client";

export type InstallState = {
  state: "idle" | "resolving" | "downloading" | "installing" | "done" | "failed" | "cancelled";
  phase: string;              // human label, e.g. "Downloading torch-2.14.1…"
  percent: number;            // 0..100
  bytes_done: number;
  bytes_total: number;
  current_file: string;
  groups: string[];
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  log: string[];              // newest last, capped at 500
};

export type InstallGroup = {
  key: "torch-cpu" | "matting-stack" | "vitmatte-weights";
  label: string;
  size_mb: number;
  installed: boolean;
  version: string | null;
  ready: boolean;
};

export type ModelStorage = {
  models_dir: string;
  rembg_dir: string;
  hf_dir: string;
  rembg_bytes: number;
  hf_bytes: number;
  env: { U2NET_HOME: string; REMBG_HOME: string; HF_HOME: string };
};

export type Environment = {
  python: string;
  venv: string;
  torch: string | null;
  transformers: string | null;
  tokenizers: string | null;
  onnxruntime_gpu: string | null;
  opencv: string | null;
  vitmatte_ready: boolean;
};

export type ProbeResult = { ok: boolean; ran_at: string; output: string };

export type SetupStatus = {
  running: boolean;
  install: InstallState;
  groups: InstallGroup[];
  models: ModelStorage;
  environment: Environment;
  probe: ProbeResult | null;
};

/** Human labels for the install state machine (indicator + modal header). */
export const INSTALL_STATE_LABELS: Record<InstallState["state"], string> = {
  idle: "Idle",
  resolving: "Resolving",
  downloading: "Downloading",
  installing: "Installing",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

export interface JobProgress {
  /** 0..100 across the *whole* job, not just the group in flight. */
  percent: number;
  /** Groups the server now reports as installed, within this job. */
  done: number;
  /** How many groups the running job requested. */
  total: number;
  /** The group currently being worked on. */
  current: InstallGroup | null;
}

/**
 * Job-wide progress for a (possibly multi-group) install.
 *
 * The engine installs one group at a time, so its own `percent` runs 0→100
 * for *each* group — three bars in a row for an "install all" job. Folding the
 * finished groups back in turns that into one honest bar. A group counts as
 * finished once the server reports it installed, which is also why the
 * `installing` and `done` states of the last group resolve to the same number.
 *
 * Shared by the modal and the floating indicator so the two can never show
 * different percentages for the same job.
 */
export function jobProgress(status: SetupStatus | null): JobProgress {
  const install = status?.install;
  const requested = install?.groups ?? [];
  const total = requested.length;

  if (!status || total === 0) {
    return { percent: install?.percent ?? 0, done: 0, total: 0, current: null };
  }

  const done = requested.filter((key) =>
    status.groups.some((group) => group.key === key && group.installed),
  ).length;

  const percent =
    total > 1
      ? Math.min(
          100,
          Math.round(((done + (install?.percent ?? 0) / 100) / total) * 100),
        )
      : (install?.percent ?? 0);

  const current =
    status.groups.find(
      (group) =>
        group.key === requested[Math.min(done, Math.max(total - 1, 0))],
    ) ?? null;

  return { percent, done, total, current };
}

/**
 * Pull a human message out of a FastAPI error body.
 *
 * FastAPI sends `{ detail: string }` for most errors but an *array* of
 * `{ loc, msg, type }` objects for 422 — stringifying the array would show
 * the operator "[object Object]".
 */
function detailMessage(data: unknown): string | null {
  if (typeof data !== "object" || data === null || !("detail" in data)) return null;
  const { detail } = data as { detail: unknown };
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        typeof item === "object" && item !== null && "msg" in item
          ? String((item as { msg: unknown }).msg)
          : ""
      )
      .filter(Boolean);
    if (messages.length > 0) return messages.join(" ");
  }
  return null;
}

/**
 * POST that keeps 4xx/5xx in the fulfilled branch so the *status code*
 * reaches this layer.
 *
 * The shared axios interceptor collapses every rejection into a plain
 * `Error(detail)`, which would make a 409 (install already running /
 * nothing to cancel) indistinguishable from any other failure — and the UI
 * needs to turn exactly those into friendly copy.
 */
async function postSetup<T>(
  path: string,
  body: unknown,
  conflictCopy: string
): Promise<T> {
  const response = await api.post<T>(path, body, { validateStatus: () => true });
  if (response.status >= 400) {
    const detail = detailMessage(response.data);
    if (detail) throw new Error(detail);
    if (response.status === 409) throw new Error(conflictCopy);
    throw new Error(`Setup request failed (HTTP ${response.status}).`);
  }
  return response.data;
}

/** Current setup status (groups, environment, storage, live install state). */
export async function fetchSetupStatus(): Promise<SetupStatus> {
  const { data } = await api.get<SetupStatus>("/api/setup/dependencies");
  return data;
}

/**
 * Start installing the given groups. 409 when an install is already
 * running, 422 on an unknown group — both surface as thrown errors.
 */
export async function startInstall(groups: string[]): Promise<SetupStatus> {
  return postSetup<SetupStatus>(
    "/api/setup/dependencies/install",
    { groups },
    "An install is already running — wait for it to finish, or cancel it first."
  );
}

/** Cancel the running install. 409 when nothing is running. */
export async function cancelInstall(): Promise<SetupStatus> {
  return postSetup<SetupStatus>(
    "/api/setup/dependencies/cancel",
    undefined,
    "Nothing is running to cancel."
  );
}

/** Run the verification probe — can take a few seconds. */
export async function probeSetup(): Promise<ProbeResult> {
  const { data } = await api.post<ProbeResult>("/api/setup/dependencies/probe");
  return data;
}
