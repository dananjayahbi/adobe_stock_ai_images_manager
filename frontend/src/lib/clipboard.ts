/**
 * Clipboard helpers with a textarea fallback for non-secure contexts.
 *
 * `navigator.clipboard` is unavailable on plain-HTTP origins other than
 * localhost, so the fallback keeps copy buttons working everywhere.
 */
export async function copyText(value: string): Promise<boolean> {
  const text = value ?? "";
  if (!text) return false;

  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the legacy path below.
  }

  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand("copy");
    textarea.remove();
    return ok;
  } catch {
    return false;
  }
}

/** Copy several lines as a single newline-delimited block. */
export function copyLines(lines: string[]): Promise<boolean> {
  return copyText(lines.join("\n"));
}
