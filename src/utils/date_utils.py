"""
src/utils/date_utils.py
=======================
Temporal primitive functions for the Redrob career scoring engine.

All functions are:
- Pure (no side-effects, no global mutable state)
- Fully typed (PEP 484)
- Gracefully handle None / malformed input
- Safe to call from multiple threads simultaneously

Design notes
------------
* parse_date() accepts full ISO-8601 ('YYYY-MM-DD') and partial ('YYYY-MM')
  formats — the candidate dataset uses both.
* career_gap_months() correctly handles overlapping roles by tracking the
  running maximum end-date seen, so concurrent roles are not double-counted
  as gaps.
* recency_decay() uses a half-life parameterisation rather than a raw rate λ
  so callers express policy in days (e.g. 365 days ≡ 1-year half-life) without
  needing to compute logarithms at the call site.

Public API
----------
    parse_date(date_str)                        -> date | None
    months_between(start, end)                  -> int
    years_between(start, end)                   -> float
    career_gap_months(career_history, today)    -> int
    recency_decay(event_date, today, half_life_days) -> float
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Reference "today" — injected at call time so tests can override
# ---------------------------------------------------------------------------
def _today() -> date:
    """Return UTC today.  Separate function so tests can monkeypatch easily."""
    return datetime.utcnow().date()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_date(date_str: Optional[str]) -> Optional[date]:
    """
    Parse a date string into a :class:`datetime.date`.

    Accepted formats
    ----------------
    * ``'YYYY-MM-DD'``  — ISO-8601 full date (preferred)
    * ``'YYYY-MM'``     — Year-month only; day defaults to 1
    * ``'YYYY'``        — Year only; defaults to January 1

    Returns ``None`` for any of:
    - ``None`` / empty string input
    - Unrecognised format
    - Out-of-range values (e.g. month 13)

    Parameters
    ----------
    date_str : str or None
        The date string to parse.

    Returns
    -------
    date or None

    Examples
    --------
    >>> parse_date('2022-03-15')
    datetime.date(2022, 3, 15)
    >>> parse_date('2022-03') is not None
    True
    >>> parse_date(None) is None
    True
    >>> parse_date('not-a-date') is None
    True

    Complexity: O(1)
    """
    if not date_str:
        return None

    s = str(date_str).strip()
    if not s:
        return None

    # Try formats in order of specificity (most → least)
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    return None


def months_between(start: date, end: date) -> int:
    """
    Return the number of complete calendar months between *start* and *end*.

    The result is always ≥ 0; if ``end < start`` the function returns ``0``
    rather than raising.

    Parameters
    ----------
    start : date
    end   : date

    Returns
    -------
    int
        Number of full calendar months.  Partial months are truncated.

    Examples
    --------
    >>> from datetime import date
    >>> months_between(date(2020, 1, 1), date(2022, 7, 1))
    30
    >>> months_between(date(2022, 7, 1), date(2020, 1, 1))  # reversed
    0

    Complexity: O(1)
    """
    delta = (end.year - start.year) * 12 + (end.month - start.month)
    return max(0, delta)


def years_between(start: date, end: date) -> float:
    """
    Return the fractional number of years between *start* and *end*.

    Parameters
    ----------
    start : date
    end   : date

    Returns
    -------
    float
        Fractional years (e.g. 2.5 = two and a half years).
        Always ≥ 0.0.

    Examples
    --------
    >>> from datetime import date
    >>> years_between(date(2018, 1, 1), date(2024, 7, 1))  # doctest: +ELLIPSIS
    6.5

    Complexity: O(1)
    """
    total_days = (end - start).days
    return max(0.0, total_days / 365.25)


def career_gap_months(
    career_history: list[dict],
    today: Optional[date] = None,
) -> int:
    """
    Compute the total number of months with no recorded employment across a
    candidate's career history.

    Algorithm
    ---------
    1. Filter roles with a valid ``start_date``.
    2. Sort by ``start_date`` ascending.
    3. Track ``max_end_seen`` (the furthest end-date seen so far).
       This correctly handles concurrent / overlapping roles — they do not
       artificially create gaps or double-count coverage.
    4. For each role, if its start is after ``max_end_seen`` → that interval
       is a gap.  Accumulate gap months.

    Current roles (``is_current=True`` or missing ``end_date``) use *today*
    as their end date.

    Parameters
    ----------
    career_history : list[dict]
        Each dict should have ``start_date`` (str) and optionally
        ``end_date`` (str) and ``is_current`` (bool).
    today : date, optional
        Reference date for open-ended current roles.  Defaults to UTC today.

    Returns
    -------
    int
        Total gap months (≥ 0).  Returns 0 for empty histories.

    Examples
    --------
    >>> from datetime import date
    >>> history = [
    ...     {'start_date': '2018-01-01', 'end_date': '2020-01-01'},
    ...     {'start_date': '2021-01-01', 'end_date': '2023-01-01'},  # 12-month gap
    ... ]
    >>> career_gap_months(history, today=date(2024, 1, 1))
    12

    Complexity: O(C log C) — dominated by sort over C career roles.
    """
    if not career_history:
        return 0

    ref_date: date = today or _today()

    # Build (start, end) pairs — skip roles without a parseable start
    intervals: list[tuple[date, date]] = []
    for role in career_history:
        start = parse_date(role.get("start_date"))
        if start is None:
            continue

        is_current = bool(role.get("is_current", False))
        end_str = role.get("end_date")

        if is_current or not end_str:
            end = ref_date
        else:
            end = parse_date(end_str) or ref_date

        # Guard against start > end (data error — integrity scorer handles this separately)
        if end < start:
            end = start

        intervals.append((start, end))

    if not intervals:
        return 0

    # Sort by start date
    intervals.sort(key=lambda x: x[0])

    total_gap_months = 0
    max_end_seen: date = intervals[0][0]  # initialise to very first start

    for start, end in intervals:
        if start > max_end_seen:
            # Gap detected
            gap = months_between(max_end_seen, start)
            total_gap_months += gap

        # Advance the frontier
        if end > max_end_seen:
            max_end_seen = end

    return total_gap_months


def recency_decay(
    event_date: date,
    today: Optional[date] = None,
    half_life_days: float = 365.0,
) -> float:
    """
    Compute an exponential recency-decay weight for an event that occurred on
    *event_date*, relative to *today*.

    Formula
    -------
    .. code-block:: text

        weight = e^(-λ × age_days)
        where  λ = ln(2) / half_life_days

    This means:
    - ``age_days = 0``              → weight = 1.0  (happened today)
    - ``age_days = half_life_days`` → weight = 0.5
    - ``age_days = 2×half_life``    → weight = 0.25

    If *event_date* is in the future, weight is clamped to 1.0.

    Parameters
    ----------
    event_date : date
        The date of the event (e.g. role start date, publication date).
    today : date, optional
        Reference date.  Defaults to UTC today.
    half_life_days : float
        Number of days after which the weight halves.  Default 365 (1 year).

    Returns
    -------
    float
        Decay weight in (0, 1].

    Examples
    --------
    >>> from datetime import date
    >>> recency_decay(date(2024, 1, 1), today=date(2024, 1, 1))  # same day
    1.0
    >>> w = recency_decay(date(2023, 1, 1), today=date(2024, 1, 1), half_life_days=365)
    >>> abs(w - 0.5) < 0.01  # half-life of exactly 1 year
    True

    Complexity: O(1)
    """
    ref_date: date = today or _today()
    age_days = (ref_date - event_date).days

    if age_days <= 0:
        return 1.0  # future event or today → full weight

    lam = math.log(2.0) / max(half_life_days, 1.0)
    return math.exp(-lam * age_days)
