"""Frozen context split for exploratory prompt selection, fixed before rankings."""
import hashlib
from collections import Counter
from .metrics import cluster_ci, qwk, spearman


def conversation_groups(cases):
    """Keep repeated contexts and dialogue prefixes in one group across roles."""
    contexts={case['context_id']:case['context'] for case in cases}
    # In lexical order a prefix precedes all its descendants in one contiguous block.
    ordered = sorted(contexts, key=contexts.__getitem__)
    groups = {}
    start = 0
    while start < len(ordered):
        prefix = contexts[ordered[start]]
        end = start + 1
        while end < len(ordered) and contexts[ordered[end]].startswith(prefix):
            end += 1
        block = ordered[start:end]
        groups.update(dict.fromkeys(block, min(block)))
        start = end
    return {case['id']: groups[case['context_id']] for case in cases}


def select_on_development(cases, successful, providers, references, rounds=1000, attempted=None, seed=42, *, groups=None):
    primary = [case for case in cases if case['primary']]
    if groups is None:
        groups = conversation_groups(cases)
    contexts = sorted({groups[case['id']] for case in primary},
                      key=lambda value: hashlib.sha256(('E4-context-split-42:' + value).encode()).hexdigest())
    dev = set(contexts[:max(1, len(contexts)//5)])
    partition = {case['id']: 'development' if groups[case['id']] in dev else 'test' for case in primary}
    original_contexts=sorted({case['context_id'] for case in primary},
                            key=lambda value:hashlib.sha256(('E4-context-split-42:'+value).encode()).hexdigest())
    original_dev=set(original_contexts[:max(1,len(original_contexts)//5)])
    audit = dict.fromkeys(('same_role_prefix_pairs', 'cross_role_prefix_pairs',
                           'initial_cross_split_pairs', 'final_cross_split_pairs'), 0)
    ancestors = []
    for case in sorted(primary, key=lambda c: c['context']):
        while ancestors and not case['context'].startswith(ancestors[-1]['context']):
            ancestors.pop()
        for other in ancestors:
            audit['same_role_prefix_pairs' if case['role'] == other['role'] else 'cross_role_prefix_pairs'] += 1
            audit['initial_cross_split_pairs'] += (case['context_id'] in original_dev) != (other['context_id'] in original_dev)
            audit['final_cross_split_pairs'] += partition[case['id']] != partition[other['id']]
        ancestors.append(case)
    manifest = {'method': 'Connect contexts across roles when one is a prefix of the other; hash the minimum context_id in each group with E4-context-split-42:, lowest 20% of groups = development',
                'fixed_at': '2026-11-04T13:19:53Z',
                'timing': 'Revised to remove 10 cross-split dialogue-prefix pairs after case inspection, before inspecting model/prompt aggregate rankings; not a preregistration.',
                'overlap_audit': audit,
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
    attempted=successful if attempted is None else attempted
    attempted_count=sum((provider,style,case['id'],False) in attempted
                        for provider in providers for style in styles for case in primary)
    if attempted_count != expected:
        return {'state': 'waiting_for_all_pointwise_attempts', 'completed': present,
                'attempted':attempted_count,'expected': expected,
                'manifest': manifest}
    common={case['id'] for case in primary if all((provider,style,case['id'],False) in successful
             for provider in providers for style in styles)}
    def matched(provider, style, split):
        return [{'context_id': groups[case['id']], 'human': references[case['id']]['empathy'],
                 'judge': successful[(provider, style, case['id'], False)]['result']['scores']['empathy']}
                for case in primary if case['id'] in common and partition[case['id']] == split
                and 'empathy' in references[case['id']]]
    def agreement(rows, metric):
        return metric([row['human'] for row in rows], [row['judge'] for row in rows])
    development = []
    for provider in providers:
        for style in styles:
            rows = matched(provider, style, 'development')
            development.append({'provider': provider, 'style': style, 'n': len(rows),
                                'qwk': agreement(rows, qwk)})
    eligible = [row for row in development if row['qwk'] is not None]
    scope = 'Exploratory Empathy prompt choice on cases valid under every judge/style. Format failures may make this subset unrepresentative; no universal or causal superiority claim.'
    excluded = sorted(case['id'] for case in primary if case['id'] not in common)
    if not eligible:
        return {'state': 'no_valid_development_qwk', 'manifest': manifest, 'development': development,
                'common_valid_case_count': len(common),
                'excluded_cases_for_incomplete_judgments': excluded,
                'selected': None, 'held_out_test': None, 'scope': scope}
    chosen = sorted(eligible, key=lambda row: (-row['qwk'], row['provider'], row['style']))[0]
    test_rows = matched(chosen['provider'], chosen['style'], 'test')
    return {'state': 'complete', 'manifest': manifest, 'development': development,
            'common_valid_case_count': len(common),
            'excluded_cases_for_incomplete_judgments': excluded,
            'selected': chosen, 'held_out_test': {
                'qwk': cluster_ci(test_rows, lambda rows: agreement(rows, qwk), rounds=rounds, seed=seed),
                'spearman': cluster_ci(test_rows, lambda rows: agreement(rows, spearman), rounds=rounds, seed=seed)},
            'scope': scope}
