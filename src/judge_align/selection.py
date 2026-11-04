"""Frozen context split for exploratory prompt selection, fixed before rankings."""
import hashlib
from .metrics import cluster_ci, qwk, spearman


def select_on_development(cases, successful, providers, references, rounds=1000):
    primary = [case for case in cases if case['primary']]
    contexts = sorted({case['context_id'] for case in primary},
                      key=lambda value: hashlib.sha256(('E4-context-split-42:' + value).encode()).hexdigest())
    dev = set(contexts[:max(1, len(contexts)//5)])
    partition = {case['id']: 'development' if case['context_id'] in dev else 'test' for case in primary}
    manifest = {'method': 'SHA256(E4-context-split-42:context_id), lowest 20% of contexts = development',
                'fixed_at': '2026-11-04T12:48:00Z',
                'timing': 'Fixed after requests started, before inspecting aggregate rankings; not a preregistration.',
                'selection_rule': 'Highest development Empathy QWK; lexicographic provider/style breaks ties.',
                'case_split': partition, 'context_counts': {'development': len(dev), 'test': len(contexts)-len(dev)},
                'case_counts': {split: sum(value == split for value in partition.values()) for split in ('development', 'test')}}
    styles = ('direct', 'rationale', 'anchored')
    expected = len(primary)*len(providers)*len(styles)
    present = sum((provider, style, case['id'], False) in successful
                  for provider in providers for style in styles for case in primary)
    if present != expected:
        return {'state': 'waiting_for_all_pointwise_requests', 'completed': present, 'expected': expected,
                'manifest': manifest}
    def matched(provider, style, split):
        return [{'context_id': case['context_id'], 'human': references[case['id']]['empathy'],
                 'judge': successful[(provider, style, case['id'], False)]['result']['scores']['empathy']}
                for case in primary if partition[case['id']] == split and 'empathy' in references[case['id']]]
    def agreement(rows, metric):
        return metric([row['human'] for row in rows], [row['judge'] for row in rows])
    development = []
    for provider in providers:
        for style in styles:
            rows = matched(provider, style, 'development')
            development.append({'provider': provider, 'style': style, 'n': len(rows),
                                'qwk': agreement(rows, qwk)})
    eligible = [row for row in development if row['qwk'] is not None]
    chosen = sorted(eligible, key=lambda row: (-row['qwk'], row['provider'], row['style']))[0]
    test_rows = matched(chosen['provider'], chosen['style'], 'test')
    return {'state': 'complete', 'manifest': manifest, 'development': development,
            'selected': chosen, 'held_out_test': {
                'qwk': cluster_ci(test_rows, lambda rows: agreement(rows, qwk), rounds=rounds, seed=42),
                'spearman': cluster_ci(test_rows, lambda rows: agreement(rows, spearman), rounds=rounds, seed=42)},
            'scope': 'Exploratory Empathy prompt choice on this released subset; no universal or causal superiority claim.'}
