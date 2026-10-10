"""Stock-grade cut-out refinement for PNG background removal.

The salient-object mask a SOD model produces is only the *middle* of a
stock-acceptable cut-out. This package implements the rest of the blueprint:

======================  ==========================================
Stage                   Module
======================  ==========================================
auto-trimap             :mod:`.trimap`
sub-pixel matting       :mod:`.refine` (:mod:`.guided`, ViTMatte)
colour decontamination  :mod:`.defringe`
alpha sanitising        :mod:`.sanitize`
dual-matte QC           :mod:`.qc`
orchestration           :mod:`.pipeline`
======================  ==========================================

Everything takes and returns ``numpy`` arrays, so the whole package is
testable without ``rembg``, a GPU, or a file on disk.
"""

from .defringe import decontaminate, estimate_background, nearest_colour
from .pipeline import DEFAULT_CONFIG, refine_cutout, resolve_config
from .qc import DualMatteReport, audit, contour_jaggedness, dual_matte_report
from .refine import METHODS, refine_alpha
from .sanitize import sanitize_alpha
from .trimap import build_trimap

__all__ = [
    "DEFAULT_CONFIG",
    "DualMatteReport",
    "METHODS",
    "audit",
    "build_trimap",
    "contour_jaggedness",
    "decontaminate",
    "dual_matte_report",
    "estimate_background",
    "nearest_colour",
    "refine_alpha",
    "refine_cutout",
    "resolve_config",
    "sanitize_alpha",
]
