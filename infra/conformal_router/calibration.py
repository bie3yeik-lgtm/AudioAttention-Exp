from __future__ import annotations

import math
from typing import Iterable


def conformal_quantile(
    residuals: list[float],
    *,
    coverage: float,
    finite_sample_correction: bool = True,
) -> float:
    """
    Split-conformal absolute-residual quantile.

    For nominal coverage 1-alpha, the finite sample conformal index is:

        ceil((n + 1) * (1 - alpha))

    clipped to [1, n].
    """
    xs = sorted(float(x) for x in residuals if math.isfinite(float(x)))
    if not xs:
        raise ValueError("No valid residuals")

    n = len(xs)

    if finite_sample_correction:
        rank = math.ceil((n + 1) * coverage)
        rank = max(1, min(n, rank))
        return xs[rank - 1]

    # Standard empirical quantile with nearest-rank behavior.
    rank = math.ceil(n * coverage)
    rank = max(1, min(n, rank))
    return xs[rank - 1]


def interval(
    prediction: float,
    q: float,
    *,
    clamp_lower_to_zero: bool = True,
    max_relative_half_width: float | None = None,
) -> tuple[float, float, float]:
    prediction = float(prediction)
    q = max(0.0, float(q))

    if max_relative_half_width is not None and prediction > 0:
        q = min(q, prediction * max_relative_half_width)

    lower = prediction - q
    upper = prediction + q

    if clamp_lower_to_zero:
        lower = max(0.0, lower)

    return lower, upper, q
