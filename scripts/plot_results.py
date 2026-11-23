#!/usr/bin/env python3
"""Render actual E4 estimates and bootstrap intervals as standalone figures."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--summary',default='results/formal-summary.json')
parser.add_argument('--outdir',default='figures')
args=parser.parse_args()
report=json.loads(Path(args.summary).read_text())
out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
providers=list(dict.fromkeys(r['provider'] for r in report['pointwise']));styles=['direct','rationale','anchored']
point={(r['provider'],r['style']):r for r in report['pointwise'] if r['dimension']=='empathy'}
grid=np.array([[np.nan if point[(provider,style)]['qwk']['value'] is None else point[(provider,style)]['qwk']['value'] for style in styles] for provider in providers],dtype=float)
plt.rcParams.update({'font.size':10,'svg.fonttype':'none','savefig.facecolor':'white'})
fig,(left,right)=plt.subplots(1,2,figsize=(12,4.8),gridspec_kw={'width_ratios':[1,1.25]},layout='constrained')
heat=left.imshow(grid,cmap='RdBu',vmin=-1,vmax=1,aspect='auto')
left.set_xticks(range(len(styles)),styles);left.set_yticks(range(len(providers)),providers)
left.set_title('Empathy agreement with released human ratings\nQuadratic weighted kappa; actual n in each cell',fontsize=11)
for i,provider in enumerate(providers):
    for j,style in enumerate(styles):
        stat=point[(provider,style)]['qwk'];value=stat['value'];ci=stat.get('ci95')
        if value is None:
            label='N/A'
        elif ci and None not in ci:
            label=f"{value:.3f}\n[{ci[0]:.3f}, {ci[1]:.3f}]\nn={stat['n']}"
        else:
            label=f"{value:.3f}\nn={stat['n']}"
        left.text(j,i,label,ha='center',va='center',fontsize=9,color='white' if value is not None and abs(value)>.6 else '#172026')
fig.colorbar(heat,ax=left,shrink=.75,label='QWK (95% CI in cells)')
dimensions=['persona','empathy','quality','safety'];colors=['#1B6CA8','#D17627','#328A67','#7B5EA7','#B53A3A']
pair={(r['provider'],r['dimension']):r['position_inconsistency'] for r in report['pairwise']}
centers=np.arange(len(dimensions))
offset_mid=(len(providers)-1)/2
bar_width=min(.23,.7/max(1,len(providers)))
for k,provider in enumerate(providers):
    stats=[pair[(provider,d)] for d in dimensions]
    ys=centers+(k-offset_mid)*bar_width
    present=[idx for idx,r in enumerate(stats) if r['value'] is not None]
    if present:
        right.barh(ys[present],np.array([stats[idx]['value'] for idx in present],dtype=float),height=bar_width*.91,color=colors[k%len(colors)],label=f"{provider} (n={stats[0]['n']})")
    valid=[idx for idx,r in enumerate(stats) if r['value'] is not None and r.get('ci95') and None not in r['ci95']]
    if valid:
        v_vals=np.array([stats[idx]['value'] for idx in valid],dtype=float)
        v_lo=np.array([stats[idx]['ci95'][0] for idx in valid],dtype=float)
        v_hi=np.array([stats[idx]['ci95'][1] for idx in valid],dtype=float)
        right.errorbar(v_vals,ys[valid],xerr=[np.maximum(0.0,v_vals-v_lo),np.maximum(0.0,v_hi-v_vals)],fmt='none',ecolor='#202020',capsize=2,linewidth=1)
right.set_yticks(centers,dimensions);right.invert_yaxis();right.set_xlim(0,1)
right.set_xlabel('Fraction of canonical outcomes changed (including ties)')
right.set_title('Position sensitivity after A/B swap\nOnly complete A/B swaps; 95% conversation-group CI',fontsize=11)
right.grid(axis='x',alpha=.2);right.set_axisbelow(True);right.legend(loc='lower right',frameon=False)
fig.suptitle(f"E4 judge alignment — {report['attempted_requests']:,} requests executed, {report['successful_requests']:,} analyzable outputs",fontsize=14)
for suffix in ['png','svg','pdf']:
    fig.savefig(out/f'formal-comparison.{suffix}',dpi=200)
print(json.dumps({'figures':[str(out/f'formal-comparison.{suffix}') for suffix in ['png','svg','pdf']]}))
