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


def select_on_development(cases, successful, providers, references, rounds=1000, attempted=None, seed=42):
    primary = [case for case in cases if case['primary']]
    groups=conversation_groups(cases)
    contexts = sorted({groups[case['id']] for case in primary},
                      key=lambda value: hashlib.sha256(('E4-context-split-42:' + value).encode()).hexdigest())
    dev = set(contexts[:max(1, len(contexts)//5)])
    partition = {case['id']: 'development' if groups[case['id']] in dev else 'test' for case in primary}
    prefix_pairs=[(left,right) for i,left in enumerate(primary) for right in primary[i+1:]
                  if left['context'].startswith(right['context']) or right['context'].startswith(left['context'])]
    original_contexts=sorted({case['context_id'] for case in primary},
                            key=lambda value:hashlib.sha256(('E4-context-split-42:'+value).encode()).hexdigest())
    original_dev=set(original_contexts[:max(1,len(original_contexts)//5)])
    manifest = {'method': 'Connect contexts across roles when one is a prefix of the other; hash the minimum context_id in each group with E4-context-split-42:, lowest 20% of groups = development',
                'fixed_at': '2026-11-04T13:19:53Z',
                'timing': 'Revised to remove 10 cross-split dialogue-prefix pairs after case inspection, before inspecting model/prompt aggregate rankings; not a preregistration.',
                'overlap_audit': {
                    'same_role_prefix_pairs':sum(a['role']==b['role'] for a,b in prefix_pairs),
                    'cross_role_prefix_pairs':sum(a['role']!=b['role'] for a,b in prefix_pairs),
                    'initial_cross_split_pairs':sum((a['context_id'] in original_dev)!=(b['context_id'] in original_dev) for a,b in prefix_pairs),
                    'final_cross_split_pairs':sum(partition[a['id']]!=partition[b['id']] for a,b in prefix_pairs)},
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
