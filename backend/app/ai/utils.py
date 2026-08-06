"""JS-compatible numeric helpers.

The frontend formulas use ``Math.round`` (halves round towards +infinity)
and Indian-locale number grouping; these helpers reproduce both exactly so
the Python ports return byte-identical values.
"""

from __future__ import annotations

import math


def js_round(value: float) -> int:
    """Round with JavaScript ``Math.round`` semantics (halves towards +infinity).

    Python's built-in ``round`` uses banker's rounding, which diverges for
    ``.5`` values (e.g. ``round(-3.5) == -4`` but ``Math.round(-3.5) == -3``).
    """
    return math.floor(value + 0.5)


def format_inr(value: float) -> str:
    """Format an amount like JS ``toLocaleString("en-IN")`` (Indian grouping)."""
    integer = int(value)
    negative = integer < 0
    digits = str(abs(integer))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = [tail]
        while len(head) > 2:
            head, group = head[:-2], head[-2:]
            groups.append(group)
        grouped = ",".join([head, *reversed(groups)])
    else:
        grouped = digits
    return f"-{grouped}" if negative else grouped
