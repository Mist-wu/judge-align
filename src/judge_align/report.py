"""Agreement report with explicit missing-human-label and missing-run boundaries."""
import html
import json
from collections import defaultdict
from pathlib import Path
from .data import DIMENSIONS,validate_annotations
from .io import atomic_json,digest,now,write_jsonl
from .metrics import canonical_winner,cluster_ci,mean,partial_spearman,qwk,spearman
from .selection import select_on_development
from .prompts import prompt_for


def heatmap_svg(pointwise,path):
    providers=sorted({r["provider"] for r in pointwise})
    columns=[(style,d) for style in ["direct","rationale","anchored"] for d in DIMENSIONS]
    width,height=230+110*len(columns),100+50*len(providers)
    nodes=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<text x="12" y="22" font-family="sans-serif" font-size="16">Quadratic weighted kappa (blank = missing human labels / undefined)</text>']
    index={(r['provider'],r['style'],r['dimension']):r for r in pointwise}
    for i,(style,dimension) in enumerate(columns):
        nodes.append(f'<text x="{230+110*i}" y="55" font-size="10">{style}</text><text x="{230+110*i}" y="70" font-size="10">{dimension}</text>')
    for j,provider in enumerate(providers):
        y=90+50*j
        nodes.append(f'<text x="12" y="{y+23}" font-family="sans-serif" font-size="13">{html.escape(provider)}</text>')
        for i,(style,dimension) in enumerate(columns):
            row=index.get((provider,style,dimension),{})
            value=row.get('qwk',{}).get('value')
            label='N/A' if value is None else f'{value:.3f}'
            color='#eeeeee' if value is None else f'rgb({int(220-130*max(0,value))},{int(230-40*max(0,value))},240)'
            nodes.append(f'<rect x="{225+110*i}" y="{y}" width="105" height="40" fill="{color}"/><text x="{235+110*i}" y="{y+25}" font-family="sans-serif" font-size="13">{label}</text>')
    nodes.append('</svg>')
    Path(path).write_text('\n'.join(nodes))


def build_report(cases,pairs,judgments,annotations,config,outdir):
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    if annotations:
        validate_annotations(annotations,cases,pairs)
    index={c['id']:c for c in cases};pair_index={p['id']:p for p in pairs}
    references={c['id']:dict(c['human_scores']) for c in cases}
    pair_references={p['id']:dict(p['human_winners']) for p in pairs}
    manual=defaultdict(list);retest=defaultdict(dict)
    for annotation in annotations:
        if annotation['kind']=='pointwise':
            retest[(annotation['id'],annotation['annotator'])][annotation['round']]=annotation['scores']
        if annotation['round']=='initial':
            manual[(annotation['kind'],annotation['id'])].append(annotation)
    # Do not silently average ordinal human votes or resolve reviewer disagreement.
    for (kind,item),rows in manual.items():
        if len(rows)>1:
            raise ValueError('Multiple initial annotators require an explicitly adjudicated reference file')
        field='scores' if kind=='pointwise' else 'winners'
        (references if kind=='pointwise' else pair_references)[item].update(rows[0][field])
    successful={}
    failed=set()
    provider_configs=defaultdict(set)
    for row in judgments:
        if row.get('status')=='success' and row.get('provider_config_sha256'):
            provider_configs[row['provider']].add(row['provider_config_sha256'])
    for row in judgments:
        if row.get('status')=='success':
            key=(row['provider'],row['style'],row['item_id'],row.get('swapped',False))
            if key in successful and successful[key]['result'] != row['result']:
                raise ValueError('Conflicting repeated judgments; select one preregistered run/config before reporting')
            successful[key]=row
        elif row.get('status')=='failed':
            failed.add(row.get('run_key'))
    pointwise,pairwise,badcases=[],[],[]
    rounds=config.get('bootstrap_rounds',1000);seed=config.get('seed',42)
    for provider in config['providers']:
        for style in ['direct','rationale','anchored']:
            for dimension in DIMENSIONS:
                matched=[]
                for c in cases:
                    if not c['primary']:continue
                    row=successful.get((provider,style,c['id'],False))
                    gold=references[c['id']].get(dimension)
                    if row is None or gold is None:continue
                    entry={'context_id':c['context_id'],'human':gold,'judge':row['result']['scores'][dimension],
                           'length':len(c['response']),'quality':references[c['id']].get('quality')}
                    matched.append(entry)
                    badcases.append({'provider':provider,'style':style,'dimension':dimension,'case_id':c['id'],
                                     'human':gold,'judge':entry['judge'],'absolute_error':abs(gold-entry['judge'])})
                q=cluster_ci(matched,lambda r:qwk([x['human'] for x in r],[x['judge'] for x in r]),rounds=rounds,seed=seed)
                s=cluster_ci(matched,lambda r:spearman([x['human'] for x in r],[x['judge'] for x in r]),rounds=rounds,seed=seed)
                quality_matched=[r for r in matched if r['quality'] is not None]
                length=cluster_ci(quality_matched,lambda r:partial_spearman([x['judge'] for x in r],[x['length'] for x in r],[x['quality'] for x in r]),rounds=rounds,seed=seed)
                pointwise.append({'provider':provider,'style':style,'dimension':dimension,'qwk':q,'spearman':s,
                                  'length_partial_spearman':length,'length_definition':'Unicode character count; control = independently human-rated quality',
                                  'status':'measured' if matched else 'human_or_judgment_pending'})
        for dimension in DIMENSIONS:
            complete=[]
            for pair in pairs:
                front=successful.get((provider,'pairwise',pair['id'],False))
                back=successful.get((provider,'pairwise',pair['id'],True))
                if not front or not back:continue
                a=canonical_winner(front['result']['winners'][dimension],False)
                b=canonical_winner(back['result']['winners'][dimension],True)
                gold=pair_references[pair['id']].get(dimension)
                complete.append({'context_id':pair['context_id'],'inconsistent':int(a!=b),'decisive_flip':int(a!=b),
                                 'decisive':a!='tie' and b!='tie','accuracy':None if gold is None else (int(a==gold)+int(b==gold))/2})
            labelled=[r for r in complete if r['accuracy'] is not None]
            decisive=[r for r in complete if r['decisive']]
            pairwise.append({'provider':provider,'dimension':dimension,
                'position_inconsistency':cluster_ci(complete,lambda r:mean([x['inconsistent'] for x in r]),rounds=rounds,seed=seed),
                'decisive_flip_rate':cluster_ci(decisive,lambda r:mean([x['decisive_flip'] for x in r]),rounds=rounds,seed=seed),
                'human_pair_accuracy':cluster_ci(labelled,lambda r:mean([x['accuracy'] for x in r]),rounds=rounds,seed=seed)})
    reliability=[]
    for dimension in DIMENSIONS:
        matched=[{'context_id':index[cid]['context_id'],'initial':r['initial'][dimension],'retest':r['retest'][dimension]}
                 for (cid,annotator),r in retest.items() if 'initial' in r and 'retest' in r]
        reliability.append({'dimension':dimension,'qwk':cluster_ci(matched,lambda r:qwk([x['initial'] for x in r],[x['retest'] for x in r]),rounds=rounds,seed=seed)})
    primary=[c for c in cases if c['primary']]
    expected=len(config['providers'])*(len(primary)*3+len(pairs)*2)
    pending={d:sum(d not in references[c['id']] for c in primary) for d in DIMENSIONS}
    report={'run_kind':'formal','created_at':now(),'source_commit':primary[0].get('source_commit') if primary else None,
        'population':config.get('data_population'),'primary_count':len(primary),'pair_count':len(pairs),
        'successful_requests':len(successful),'expected_requests':expected,
        'failed_attempts':sum(row.get('status')=='failed' for row in judgments),
        'failed_request_configs':len(failed),
        'automated_status':'complete' if len(successful)==expected and len(primary)==config['sample_count'] and len(pairs)==config['sample_count'] else 'partial',
        'human_pending':pending,'pairwise_human_pending':{d:sum(d not in pair_references[p['id']] for p in pairs) for d in DIMENSIONS},
        'retest_pending':50-sum('initial' in r and 'retest' in r for r in retest.values()),
        'pointwise':pointwise,'pairwise':pairwise,'human_reliability':reliability,
        'config_sha256':digest(config),'data_sha256':digest(cases),'judgments_sha256':digest(judgments),
        'observed_provider_config_hashes':{k:sorted(v) for k,v in provider_configs.items()},
        'execution_changes':['DeepSeek output capacity increased from 1536 to 8192 after truncated reasoning responses; prior complete outputs are retained.'],
        'cost':{'known_estimated_usd':sum(r.get('estimated_cost_usd') or 0 for r in judgments if r.get('status') in {'success','failed'}),
                'unknown_pricing_terminal_attempts':sum(r.get('estimated_cost_usd') is None for r in judgments if r.get('status') in {'success','failed'}),
                'ambiguous_inflight_attempts':sum(status=='started' for status in {r.get('run_key'):r.get('status') for r in judgments}.values())},
        'limitations':['Empathy-only source population; other custom dimensions require new human annotation.',
                       'Frozen custom empathy anchors differ from the upstream annotation examples; disagreement does not establish which judgment is correct.',
                       'Released reward-model training data are public and potentially contaminated.',
                       'Published candidate alternatives include Qwen/Baichuan; Qwen judge self-preference is a possible confound.',
                       'Length partial correlation controls observed human quality only; it is not causal.',
                       'Pairwise choices are not ordinal 1–5 scores and are not entered in the QWK heatmap.',
                       'Human retest reliability is not a mathematical upper bound on judge agreement.']}
    report['prompt_selection']=select_on_development(cases,successful,config['providers'],references,rounds)
    atomic_json(out/'split-manifest.json',report['prompt_selection']['manifest'])
    atomic_json(out/'formal-summary.json',report)
    by_case=defaultdict(list)
    for row in badcases:by_case[row['case_id']].append(row)
    worst=sorted(by_case,key=lambda cid:(-max(r['absolute_error'] for r in by_case[cid]),
                                        -mean([r['absolute_error'] for r in by_case[cid]]),cid))[:20]
    write_jsonl(out/'disagreements.jsonl',[
        {'case_id':cid,'role':index[cid]['role'],'context':index[cid]['context'],
         'response':index[cid]['response'],'source_rows':index[cid]['source_rows'],
         'human_scores':references[cid],'judgments':by_case[cid],
         'review_status':'awaiting_qualitative_analysis_not_new_human_annotation'} for cid in worst])
    heatmap_svg(pointwise,out/'kappa.svg')
    bias_svg([(r['provider']+'/'+r['dimension'],r['position_inconsistency']) for r in pairwise],out/'position-bias.svg','Canonical outcome inconsistency after swapping A/B; 95% cluster bootstrap CI')
    bias_svg([(r['provider']+'/'+r['style']+'/'+r['dimension'],r['length_partial_spearman']) for r in pointwise],out/'length-bias.svg','Length association after control for independent human quality; not causal')
    lines=['# Judge alignment report','',f"Automated status: **{report['automated_status']}**; {len(successful)}/{expected} requests.",'',
           'All statistics use matched human/judge records; missing labels remain missing.','',
           '| Provider | Style | Dimension | N | QWK [95% CI] | Spearman [95% CI] |','|---|---|---|---:|---:|---:|']
    fmt=lambda x:'N/A' if x is None else f'{x:.4f}'
    def interval(stat):
        ci=stat.get('ci95')
        return fmt(stat['value']) + (f" [{fmt(ci[0])}, {fmt(ci[1])}]" if ci else '')
    for r in pointwise:lines.append(f"| {r['provider']} | {r['style']} | {r['dimension']} | {r['qwk']['n']} | {interval(r['qwk'])} | {interval(r['spearman'])} |")
    lines+=['','## Position swaps','',
            '| Provider | Dimension | Complete pairs | Inconsistency [95% CI] | Decisive A/B flip [95% CI] |',
            '|---|---|---:|---:|---:|']
    for r in pairwise:lines.append(f"| {r['provider']} | {r['dimension']} | {r['position_inconsistency']['n']} | {interval(r['position_inconsistency'])} | {interval(r['decisive_flip_rate'])} |")
    selection=report['prompt_selection']
    lines+=['','## Development / held-out test split','',
            'Contexts, including all styles and pair orientations, are kept together. The split was frozen after generation began but before inspecting aggregate rankings; this is exploratory, not preregistered.']
    if selection['state']=='complete':
        picked=selection['selected'];held=selection['held_out_test']
        atomic_json(out/'selected-prompt.json',{
            'provider':picked['provider'],'model':config['providers'][picked['provider']]['model'],
            'style':picked['style'],'selection_metric':'Development Empathy QWK',
            'held_out_test':held,'scope':selection['scope'],
            'messages_template':prompt_for({'role':'{{role}}','profile':'{{profile}}',
                'context':'{{context}}','response':'{{response}}'},picked['style'])})
        lines += ['',f"Selected only on development Empathy QWK: **{picked['provider']} / {picked['style']}** (development n={picked['n']}).",
                  f"Held-out test n={held['qwk']['n']}; QWK {interval(held['qwk'])}; Spearman {interval(held['spearman'])}.",
                  'This selection does not establish superiority on other dimensions or populations.']
    else:
        lines += ['', 'Prompt selection waits for all pointwise requests.']
    lines+=['','![QWK](kappa.svg)','','![Position bias](position-bias.svg)','','![Length bias](length-bias.svg)','','## Human work remaining','',json.dumps(pending,ensure_ascii=False),
            '',f"Delayed retest remaining: {max(0,report['retest_pending'])}",'','## Limitations','']+[f'- {s}' for s in report['limitations']]
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return report


def bias_svg(rows,path,title):
    """Render comparable -1..1 scale with explicit N/A for unavailable estimates."""
    width,height=960,90+28*len(rows)
    start,scale=610,230
    nodes=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           f'<text x="12" y="25" font-family="sans-serif" font-size="16">{html.escape(title)}</text>',
           f'<line x1="{start}" x2="{start}" y1="50" y2="{height-20}" stroke="#777"/>']
    for value in [-1,-.5,0,.5,1]:
        x=start+scale*value
        nodes.append(f'<text x="{x-10}" y="48" font-family="sans-serif" font-size="11">{value:g}</text>')
    for i,(label,stat) in enumerate(rows):
        y=60+28*i;value=stat.get('value');n=stat.get('n',0)
        nodes.append(f'<text x="12" y="{y+15}" font-family="sans-serif" font-size="11">{html.escape(label)} (n={n})</text>')
        if value is None:
            nodes.append(f'<text x="{start+8}" y="{y+15}" font-family="sans-serif" font-size="11" fill="#777">N/A — pending or undefined</text>')
            continue
        left=min(start,start+scale*value);bar=abs(scale*value)
        nodes.append(f'<rect x="{left}" y="{y}" width="{bar}" height="18" fill="#5a85b5"/>')
        ci=stat.get('ci95')
        if ci and None not in ci:
            nodes.append(f'<line x1="{start+scale*ci[0]}" x2="{start+scale*ci[1]}" y1="{y+9}" y2="{y+9}" stroke="#111" stroke-width="2"/>')
        nodes.append(f'<text x="855" y="{y+15}" font-family="sans-serif" font-size="11">{value:.3f}</text>')
    nodes.append('</svg>');Path(path).write_text('\n'.join(nodes))
