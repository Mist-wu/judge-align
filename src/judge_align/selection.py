"""Frozen context split for exploratory prompt selection, fixed before rankings."""
import hashlib
from collections import Counter
from .metrics import cluster_ci, qwk, spearman


def conversation_groups(cases):
    """Keep repeated contexts and dialogue prefixes in one group across roles."""
    contexts={case['context_id']:case['context'] for case in cases}
    parent={key:key for key in contexts}
    def find(key):
        while parent[key]!=key:
            parent[key]=parent[parent[key]];key=parent[key]
        return key
    keys=sorted(contexts)
    for i,left in enumerate(keys):
        text_a=contexts[left]
        for right in keys[i+1:]:
            text_b=contexts[right]
            if text_a.startswith(text_b) or text_b.startswith(text_a):
                a,b=find(left),find(right);parent[max(a,b)]=min(a,b)
    return {case['id']:find(case['context_id']) for case in cases}


def select_on_development(cases, successful, providers, references, rounds=1000):
    primary = [case for case in cases if case['primary']]
    groups=conversation_groups(cases)
    contexts = sorted({groups[case['id']] for case in primary},
                      key=lambda value: hashlib.sha256(('E4-context-split-42:' + value).encode()).hexdigest())
    dev = set(contexts[:max(1, len(contexts)//5)])
    partition = {case['id']: 'development' if groups[case['id']] in dev else 'test' for case in primary}
    manifest = {'method': 'Connect contexts across roles when one is a prefix of the other; hash the minimum context_id in each group with E4-context-split-42:, lowest 20% of groups = development',
                'fixed_at': '2026-11-04T13:19:53Z',
                'timing': 'Revised to remove 10 cross-split dialogue-prefix pairs after case inspection, before inspecting model/prompt aggregate rankings; not a preregistration.',
                'overlap_audit': {'same_role_prefix_pairs':17,'cross_role_prefix_pairs':13,'initial_cross_split_pairs':10},
                'selection_rule': 'Highest development Empathy QWK; lexicographic provider/style breaks ties.',
                'case_split': partition, 'context_counts': {'development': len(dev), 'test': len(contexts)-len(dev)},
                'conversation_group_by_case':{case['id']:groups[case['id']] for case in primary},
                'case_counts': {split: sum(value == split for value in partition.values()) for split in ('development', 'test')},
                'source_empathy_distribution': {
                    split:dict(sorted(Counter(references[case['id']]['empathy'] for case in primary
                          if partition[case['id']]==split and 'empathy' in references[case['id']]).items()))
                    for split in ('development','test')}}
    styles = ('direct', 'rationale', 'anchored')
    expected = len(primary)*len(providers)*len(styles)
    present = sum((provider, style, case['id'], False) in successful
                  for provider in providers for style in styles for case in primary)
    if present != expected:
        return {'state': 'waiting_for_all_pointwise_requests', 'completed': present, 'expected': expected,
                'manifest': manifest}
    def matched(provider, style, split):
        return [{'context_id': groups[case['id']], 'human': references[case['id']]['empathy'],
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
