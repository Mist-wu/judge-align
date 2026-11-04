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
providers=['deepseek','gemini','qwen'];styles=['direct','rationale','anchored']
point={(r['provider'],r['style']):r for r in report['pointwise'] if r['dimension']=='empathy'}
grid=np.array([[point[(provider,style)]['qwk']['value'] for style in styles] for provider in providers],dtype=float)
plt.rcParams.update({'font.size':10,'svg.fonttype':'none','savefig.facecolor':'white'})
fig,(left,right)=plt.subplots(1,2,figsize=(12,4.8),gridspec_kw={'width_ratios':[1,1.25]},layout='constrained')
heat=left.imshow(grid,cmap='RdBu',vmin=-1,vmax=1,aspect='auto')
left.set_xticks(range(3),styles);left.set_yticks(range(3),providers)
left.set_title('Empathy agreement with released human ratings\nQuadratic weighted kappa; n=200 each',fontsize=11)
for i,provider in enumerate(providers):
    for j,style in enumerate(styles):
        stat=point[(provider,style)]['qwk'];value=stat['value'];ci=stat['ci95']
        label='N/A' if value is None else f'{value:.3f}\n[{ci[0]:.3f}, {ci[1]:.3f}]'
        left.text(j,i,label,ha='center',va='center',fontsize=9,color='white' if value is not None and abs(value)>.6 else '#172026')
fig.colorbar(heat,ax=left,shrink=.75,label='QWK (95% CI in cells)')
dimensions=['persona','empathy','quality','safety'];colors=['#1B6CA8','#D17627','#328A67']
pair={(r['provider'],r['dimension']):r['position_inconsistency'] for r in report['pairwise']}
centers=np.arange(4)
for k,provider in enumerate(providers):
    stats=[pair[(provider,d)] for d in dimensions]
    values=np.array([r['value'] for r in stats]);lower=np.array([r['ci95'][0] for r in stats]);upper=np.array([r['ci95'][1] for r in stats])
    right.barh(centers+(k-1)*.23,values,height=.21,color=colors[k],label=provider)
    right.errorbar(values,centers+(k-1)*.23,xerr=[values-lower,upper-values],fmt='none',ecolor='#202020',capsize=2,linewidth=1)
right.set_yticks(centers,dimensions);right.invert_yaxis();right.set_xlim(0,1)
right.set_xlabel('Fraction of canonical outcomes changed (including ties)')
right.set_title('Position sensitivity after A/B swap\n200 paired comparisons per provider; 95% cluster CI',fontsize=11)
right.grid(axis='x',alpha=.2);right.set_axisbelow(True);right.legend(loc='lower right',frameon=False)
fig.suptitle(f"E4 judge alignment — {report['successful_requests']:,}/{report['expected_requests']:,} requests",fontsize=15)
for suffix in ['png','svg','pdf']:
    fig.savefig(out/f'formal-comparison.{suffix}',dpi=200)
print(json.dumps({'figures':[str(out/f'formal-comparison.{suffix}') for suffix in ['png','svg','pdf']]}))
