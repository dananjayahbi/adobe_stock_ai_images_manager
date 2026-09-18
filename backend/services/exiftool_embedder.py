"""ExifTool embedder - writes IPTC/XMP metadata into JPEG files."""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

EXIFTOOL_TIMEOUT = 30  # seconds

# Well-known install locations, checked when `exiftool` is not on PATH
# (e.g. the process was started before PATH was updated).
_FALLBACK_PATHS = (
    Path.home() / "AppData" / "Local" / "Programs" / "ExifTool" / "exiftool.exe",
    Path("C:/Program Files/ExifTool/exiftool.exe"),
    Path("C:/Program Files (x86)/ExifTool/exiftool.exe"),
)

_resolved_executable: str | None = None


def _resolve_executable() -> str | None:
    """Return the exiftool executable path, or None if unavailable.

    Prefers PATH, then falls back to known install locations. The result is
    cached, including negative results, to avoid repeated filesystem probes.
    """
    global _resolved_executable
    if _resolved_executable is not None:
        return _resolved_executable or None

    found = shutil.which("exiftool")
    if not found:
        for candidate in _FALLBACK_PATHS:
            if candidate.exists():
                found = str(candidate)
                logger.info("ExifTool not on PATH; using %s", found)
                break

    _resolved_executable = found or ""
    return found


def _check_exiftool() -> bool:
    """Verify ExifTool is available on PATH or at a known install location."""
    return _resolve_executable() is not None


def embed_metadata(file_path: str | Path, metadata_dict: dict) -> bool:
    """Invoke ExifTool subprocess to embed IPTC/XMP metadata into a JPEG file.

    Args:
        file_path: Absolute path to the target JPEG file (should be in ready_to_upload dir).
        metadata_dict: Dict with keys 'title', 'description', and 'keywords' (list of strings).

    Returns True on success, False on failure.
    """
    executable = _resolve_executable()
    if not executable:
        logger.error("ExifTool not found on system PATH. Cannot embed metadata.")
        return False

    abs_path = Path(file_path).resolve()
    if not abs_path.exists():
        logger.error("File not found for metadata embedding: %s", abs_path)
        return False

    title = metadata_dict.get("title", "")
    description = metadata_dict.get("description", "")
    keywords = metadata_dict.get("keywords", [])

    if not isinstance(keywords, list):
        keywords = []

    # Cap keywords at 35 per spec
    keywords = keywords[:35]

    # Build ExifTool command arguments
    cmd = [executable, "-overwrite_original"]

    if title:
        cmd.append(f"-IPTC:ObjectName={title}")
        cmd.append(f"-XMP-dc:Title={title}")

    if description:
        cmd.append(f"-IPTC:Caption-Abstract={description}")
        cmd.append(f"-XMP-dc:Description={description}")
    elif title:
        # Use title as description fallback per Adobe Stock convention
        cmd.append(f"-IPTC:Caption-Abstract={title}")
        cmd.append(f"-XMP-dc:Description={title}")

    # Add each keyword individually to preserve commas within keywords
    for kw in keywords:
        kw_str = str(kw).strip()
        if kw_str:
            cmd.append(f"-IPTC:Keywords={kw_str}")
            cmd.append(f"-XMP-dc:Subject={kw_str}")

    # File path must be the final argument
    cmd.append(str(abs_path))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=EXIFTOOL_TIMEOUT,
        )

        if result.returncode == 0:
            logger.info("Successfully embedded metadata into %s", abs_path.name)
            return True
        else:
            logger.error(
                "ExifTool failed for %s (exit code %d): %s",
                abs_path.name,
                result.returncode,
                result.stderr.strip(),
            )
            return False

    except subprocess.TimeoutExpired:
        logger.error("ExifTool timed out after %ds for %s", EXIFTOOL_TIMEOUT, abs_path.name)
        return False
    except FileNotFoundError:
        logger.error("ExifTool executable not found despite PATH check")
        return False
    except Exception as e:
        logger.error("Unexpected error running ExifTool for %s: %s", abs_path.name, e)
        return False
