"""Pair provider attempts without letting an older terminal row close a later try."""


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
    groups = {}
    order = []
    for index, row in enumerate(rows):
        if row.get('record_type') == 'format_recovery':
            continue
        status = row.get('status')
        if status not in {'started', 'success', 'failed'}:
            continue
        attempt = row.get('attempt_id')
        if attempt:
            key = ('attempt', attempt)
        elif row.get('run_key') is not None:
            key = ('legacy', row.get('run_key'))
        else:
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((index, row))
    return sum(_open_count(key, groups[key]) for key in order)


def _open_count(key, items):
    if key[0] == 'attempt':
        started = any(row.get('status') == 'started' for _, row in items)
        terminal = any(row.get('status') in {'success', 'failed'} for _, row in items)
        return int(started and not terminal)
    timed = []
    untimed_started = untimed_terminal = 0
    for index, row in items:
        stamp = _event_time(row)
        if stamp is None:
            if row.get('status') == 'started':
                untimed_started += 1
            else:
                untimed_terminal += 1
        else:
            timed.append((stamp, index, row))
    open_starts = []
    for stamp, _index, row in sorted(timed, key=lambda item: (item[0], item[1])):
        if row.get('status') == 'started':
            open_starts.append(stamp)
            continue
        close_at = None
        for position in range(len(open_starts) - 1, -1, -1):
            if open_starts[position] <= stamp:
                close_at = position
                break
        if close_at is not None:
            open_starts.pop(close_at)
    return len(open_starts) + max(0, untimed_started - untimed_terminal)
