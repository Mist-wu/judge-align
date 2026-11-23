"""Pair provider attempts without letting an older terminal row close a later try."""
from collections import defaultdict


def inference_identity(config):
    """Fields that change the model call. Price and output limits are excluded."""
    return {
        'type': config.get('type'),
        'model': config.get('model'),
        'revision': config.get('revision'),
        'base_url': config.get('base_url'),
        'request_options': config.get('request_options') or {},
        'response_json_schema': config.get('response_json_schema'),
    }


def _event_time(row):
    if row.get('status') == 'started':
        raw = row.get('started_at')
    else:
        raw = row.get('ended_at')
        if not isinstance(raw, str):
            raw = row.get('started_at')
    return raw if isinstance(raw, str) and raw else None


def ambiguous_inflight_attempts(rows):
    """Started attempts that still have no matching terminal outcome.

    Rows with attempt_id pair only with that id. Older rows pair by run_key.
    A timestamped terminal closes one earlier open start; it does not cancel
    a start recorded after it. Rows without timestamps pair by count so the
    result does not depend on file order.
    """
    starts, terminals = set(), set()
    legacy = defaultdict(list)
    for row in rows:
        status = row.get('status')
        if row.get('record_type') == 'format_recovery' or status not in {'started', 'success', 'failed'}:
            continue
        started = status == 'started'
        if attempt := row.get('attempt_id'):
            (starts if started else terminals).add(attempt)
        elif row.get('run_key') is not None:
            legacy[row['run_key']].append((_event_time(row), started))

    unresolved = len(starts - terminals)
    for events in legacy.values():
        untimed = sum(1 if started else -1 for stamp, started in events if stamp is None)
        open_count = 0
        # Stable ordering preserves ledger order when timestamps are equal.
        for stamp, started in sorted((e for e in events if e[0] is not None), key=lambda e: e[0]):
            open_count = open_count + 1 if started else max(0, open_count - 1)
        unresolved += open_count + max(0, untimed)
    return unresolved
