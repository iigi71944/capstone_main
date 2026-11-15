"""Conservative ledger for whole-program action reversions (Batch 14).

No code is executed or transformed here. A checkpoint is the normalized AST
source after a *successful* transformation. If a subsequent action returns to
one of those snapshots, all actions on the now-reverted path (including the
restoring action) must not be reported as final successes.

This only detects complete checkpoint reversions. It does not claim to detect
all overlapping or partially conflicting edits.
"""
from __future__ import annotations

from collections.abc import Callable


def mark_reverted_actions(
    snapshots: list[str],
    results: list[dict],
    *,
    normalize: Callable[[str], str],
) -> int:
    """Mutate ``results`` statuses for complete intermediate reversions.

    ``snapshots[0]`` is the original code, and ``snapshots[i+1]`` is the
    output of attempt ``results[i]``. The caller records a snapshot even for
    skipped actions. Unknown/malformed rows do not cancel other actions.

    Returns the number of actions newly marked as cancelled. Does not touch
    source code or verification outcomes.
    """
    if len(snapshots) != len(results) + 1:
        raise ValueError('Action ledger and code snapshots must align.')

    # (normalized code, index of action that created it); the original has no
    # creating action. The active stack represents steps still visible after
    # complete checkpoint reversions.
    stack: list[tuple[str, int | None]] = [(normalize(snapshots[0]), None)]
    cancelled = 0
    for index, result in enumerate(results):
        if not isinstance(result, dict) or result.get('status') != 'applied':
            continue
        signature = normalize(snapshots[index + 1])
        previous = next(
            (position for position in range(len(stack) - 1, -1, -1)
             if stack[position][0] == signature), None,
        )
        if previous is None:
            stack.append((signature, index))
            continue

        for _, prior_index in stack[previous + 1:]:
            if prior_index is not None and results[prior_index].get('status') == 'applied':
                results[prior_index]['status'] = 'cancelled_net_zero'
                cancelled += 1
        result['status'] = 'cancelled_net_zero'
        cancelled += 1
        del stack[previous + 1:]
    return cancelled
