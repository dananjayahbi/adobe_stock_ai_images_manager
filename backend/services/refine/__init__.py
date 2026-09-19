"""Stage 4 - automatic image refinement.

Public surface:

* :func:`refine_image` - the loop that drives corrections to the acceptance gate.
* :mod:`services.refine.recipe` - issue-code to operation mapping.
* :mod:`services.refine.ops` - the individual pixel operations.
"""

from services.refine.refiner import RefineResult, refine_image

__all__ = ["RefineResult", "refine_image"]
