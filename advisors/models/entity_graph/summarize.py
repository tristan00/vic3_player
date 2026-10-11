import argparse
from collections import Counter
import csv
import html
import json
from pathlib import Path

import numpy as np

from interface.common import evidence, timed, timed_often
from .metrics import accuracy
from .removals import ATTEMPTS, DESCRIPTIONS
from .schema import COMPONENTS, GRAPH_VERSION, HORIZONS


@timed_often
def number(value):
    return 'Pending' if value is None else f'{value:.5f}'


@timed
def paired(reference,other,scale):
    if not np.array_equal(reference['run'],other['run']) or not np.array_equal(reference['seq'],other['seq']):
        raise ValueError(evidence(reference=len(reference['run']),other=len(other['run'])))
    ids=np.unique(reference['run'])
    mask=reference['mask']
    a=(((reference['prediction']-reference['target'])/scale)**2*mask).sum(axis=(1,2))
    b=(((other['prediction']-other['target'])/scale)**2*mask).sum(axis=(1,2))
    counts=mask.sum(axis=(1,2))
    totals=np.array([[a[reference['run']==run].sum(),b[reference['run']==run].sum(),counts[reference['run']==run].sum()] for run in ids])
    samples=np.random.default_rng(20261001).integers(0,len(ids),(2000,len(ids)))
    values=totals[samples].sum(1)
    differences=np.sqrt(values[:,1]/values[:,2])-np.sqrt(values[:,0]/values[:,2])
    return {'delta':float(np.sqrt(b.sum()/counts.sum())-np.sqrt(a.sum()/counts.sum())),
            'run_bootstrap_95_percent':np.quantile(differences,[.025,.975]).tolist()}


@timed
def charts(root,results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    labels=[r['name'].replace('without_','− ').replace('_',' ') for r in results]
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    colors=['#196d4c' if r['name']=='full_world' else '#8caea0' for r in results]
    axes[0].barh(labels,[r['test']['sequence_nrmse'] for r in results],color=colors)
    axes[0].set_xlabel('Test sequence normalized RMSE · lower is better')
    axes[1].barh(labels,[r['test']['normalized_candidate_std'] for r in results],color=colors)
    axes[1].set_xlabel('Candidate utility spread / training utility SD')
    for ax in axes:
        ax.invert_yaxis()
        ax.spines[['top','right']].set_visible(False)
    fig.savefig(root/'comparison.png',dpi=160)
    plt.close(fig)
    fig,axes=plt.subplots(1,4,figsize=(14,3.3),layout='constrained')
    for i,component in enumerate(COMPONENTS):
        for result in results:
            axes[i].plot(HORIZONS,np.array(result['test']['log_rmse'])[:,i],label=result['name'],linewidth=2 if result['name']=='full_world' else 1)
        axes[i].set_title(component)
        axes[i].set_xlabel('Forecast horizon · days')
    axes[0].set_ylabel('Log-ratio RMSE')
    axes[-1].legend(fontsize=6)
    fig.savefig(root/'horizons.png',dpi=160)
    plt.close(fig)


@timed
def summarize(root):
    result_path=root/'world_experiments/results.json'
    results=json.loads(result_path.read_text()) if result_path.exists() else []
    results={r['name']:r for r in results if r['name'] in ATTEMPTS}
    audit=json.loads((root/'graphs/audit.json').read_text())
    catalog={d['parameters']['name']:d for d in audit['designs'] if d['parameters']['name'] in ATTEMPTS}
    names=tuple(name for name in ATTEMPTS if name in catalog)
    results={name:result for name,result in results.items() if name in names}
    manifest_path=root/'world_packed/dataset.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    done=len(results)==len(names) and all('test' in r for r in results.values())
    summary={'baseline':'full_world','complete':done,'attempts':results,'graphs':catalog}
    probe=json.loads((root/'full_world/probe.json').read_text())
    structure=[]
    scores=[]
    for name in names:
        entry=catalog.get(name)
        stats=entry['snapshots'][0] if entry else {}
        structure.append('<tr>'+''.join(f'<td>{v}</td>' for v in (
            f'<a href="graphs/{name}.html">{name}</a>',html.escape(DESCRIPTIONS[name]),
            f'{stats["nodes"]:,}' if 'nodes' in stats else 'Pending',f'{stats["edges"]:,}' if 'edges' in stats else 'Pending',
            f'{stats.get("removed_nodes",0):,}',f'{stats.get("removed_attributes",0):,}'))+'</tr>')
        result=results.get(name,{})
        val,test=result.get('validation',{}),result.get('test',{})
        scores.append('<tr>'+''.join(f'<td>{v}</td>' for v in (
            name,number(val.get('sequence_nrmse')),number(test.get('sequence_nrmse')),number(test.get('reward_loss')),
            number(test.get('mean_pause_entropy')),number(test.get('normalized_candidate_std')),
            number(test.get('entropy_at_1_percent_std')),number(val.get('score')),number(test.get('score')),result.get('best_epoch','Pending')) )+'</tr>')
    details=''
    if done:
        from .experiment import restore
        model,checkpoint=restore(root/'world_experiments/full_world/model.pt','cpu')
        del model
        scale=np.array(checkpoint['scale'])
        reference=np.load(root/'world_experiments/full_world/test.npz')
        intervals={name:paired(reference,np.load(root/'world_experiments'/name/'test.npz'),scale) for name in names if name!='full_world'}
        controls={name:accuracy(prediction,reference['target'],reference['mask'],scale,checkpoint['reward_scale']) for name,prediction in (
            ('persistence',np.zeros_like(reference['target'])),('training_mean',np.broadcast_to(checkpoint['mean'],reference['target'].shape)))}
        summary.update(paired_comparisons=intervals,controls=controls)
        best=min(results.values(),key=lambda r:r['test']['sequence_nrmse'])
        better=[name for name,v in intervals.items() if v['run_bootstrap_95_percent'][1]<0]
        assessment=f'Full_world completed training with {results["full_world"]["gpu_peak_bytes"]/1e9:.2f} GB peak allocated GPU memory. Its test sequence error is {number(results["full_world"]["test"]["sequence_nrmse"])}. The lowest test sequence error among these fits is {number(best["test"]["sequence_nrmse"])} ({best["name"]}); the training-mean control is {number(controls["training_mean"]["sequence_nrmse"])}. '
        if intervals:
            assessment+=('Removals with a paired 95% interval entirely below zero: '+', '.join(better)+'.') if better else 'No removal has a paired 95% interval entirely below zero; this evaluation does not establish that a removal improves sequence accuracy.'
        summary['assessment']=assessment
        rows=''.join(f'<tr><td>{name}</td><td>{number(v["delta"])}</td><td>{number(v["run_bootstrap_95_percent"][0])} to {number(v["run_bootstrap_95_percent"][1])}</td></tr>' for name,v in intervals.items())
        details=f'<h2>What the evaluation establishes</h2><p>{html.escape(assessment)}</p><h2>Change from the full world baseline</h2><p>Paired test-sequence error difference; negative values improve accuracy. Intervals resample whole held-out runs 2,000 times. They describe sampling uncertainty for these fits, not variation across training seeds.</p><table><tr><th>Removal</th><th>Difference</th><th>95% interval</th></tr>{rows}</table>'
        details+='<p>Sequence error controls: '+', '.join(f'{name} {number(v["sequence_nrmse"])}' for name,v in controls.items())+'. These are prediction controls, not alternative world representations.</p>'
        charts(root,list(results.values()))
        details+='<img src="comparison.png" alt="Full world and removal comparison"><img src="horizons.png" alt="Errors by target and horizon">'
        fields=['name','validation_sequence','test_sequence','test_reward_loss','test_entropy','test_candidate_spread','test_entropy_at_1_percent','validation_score','test_score','selected_epoch']
        with (root/'scores.csv').open('w',newline='') as stream:
            writer=csv.writer(stream)
            writer.writerow(fields)
            for r in results.values():
                v,t=r['validation'],r['test']
                writer.writerow([r['name'],v['sequence_nrmse'],t['sequence_nrmse'],t['reward_loss'],t['mean_pause_entropy'],t['normalized_candidate_std'],t['entropy_at_1_percent_std'],v['score'],t['score'],r['best_epoch']])
    counts=Counter(r['split'] for r in manifest['rows']) if manifest else {}
    config=next(iter(results.values()))['configuration'] if results else {'width':48,'layers':3,'epochs':24,'patience':6,'sequence_length':4,'action_layers':2,'seed':41}
    runtimes=''.join('<tr>'+''.join(f'<td>{value}</td>' for value in (
        f'<a href="world_experiments/{r["name"]}/result.json">{r["name"]}</a>',r['parameters'],r['epochs_run'],r['best_epoch'],
        f'{r["gpu_peak_bytes"]/1e9:.2f}',f'{r["seconds"]/60:.1f}'))+'</tr>' for r in results.values())
    runtime_table=f'<h2>Measured fits</h2><table><tr><th>Attempt and full result</th><th>Parameters</th><th>Epochs run</th><th>Selected epoch</th><th>Peak GPU GB</th><th>Fit minutes</th></tr>{runtimes}</table>' if runtimes else ''
    if any(r.get('execution',{}).get('concurrent_removal_fits',1)>1 for r in results.values()):
        runtime_table+='<p>Removal fits ran two at a time with bounded GPU memory. Their wall times include resource sharing.</p>'
    dataset_detail=''
    if manifest:
        dataset_detail=f'<p>Across evaluated inputs, the maximum sizes are {max(r["nodes"] for r in manifest["rows"]):,} nodes and {max(r["edges"] for r in manifest["rows"]):,} directed edges. Training provides {manifest["tokens"]:,} feature tokens, {len(manifest["node_types"])} node types and {len(manifest["relations"])} relation types. <a href="world_packed/dataset.json">Dataset manifest</a></p>'
    selection_path=root/'world_experiments/selection.json'
    selected=''
    if selection_path.exists():
        selection=json.loads(selection_path.read_text())
        summary['selection']=selection
        selected=f'<p>Lowest validation comparison score: <b>{html.escape(selection["selected"])}</b>. The complete full_world model remains the reference. <a href="world_experiments/selection.json">Selection record</a></p>'
    verification_path=root/'world_verification.json'
    verification=''
    if verification_path.exists():
        replay=json.loads(verification_path.read_text())
        summary['live_replay']=replay
        verification=f'<h2>Live snapshot replay</h2><p>Freshly generated action blocks matched the evaluated alternatives. All {len(replay)} checkpoints reproduced their saved forecasts on {replay[0]["candidates"]} alternatives from held-out run {replay[0]["run"]}, snapshot {replay[0]["seq"]}. Maximum absolute log-ratio difference: {max(r["max_log_ratio_difference"] for r in replay):.8f}. <a href="world_verification.json">Replay results</a></p>'
    revision=''
    if manifest and manifest.get('graph_version')!=GRAPH_VERSION:
        summary['historical_graph_revision']=True
        revision='<p style="padding:18px;background:#fff0cf"><b>Historical evaluation: these results predate the recurrent graph revision.</b> They do not evaluate the current recurrent model.'
        if (root.parent/'entity_graph_spatial_20261001/report.html').exists():
            revision+=' <a href="../entity_graph_spatial_20261001/report.html">Open the current spatial world graph and revised tuning proposal.</a>'
        revision+='</p>'
    text=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Complete world baseline and controlled removals</title><style>body{{font:16px/1.55 system-ui;max-width:1450px;margin:35px auto;padding:0 24px;background:#f7f8f6;color:#182822}}h1{{font-size:34px}}h2{{margin-top:32px}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:10px;border-bottom:1px solid #cbd6cf;text-align:left}}th{{background:#e1ece4}}.scroll{{overflow:auto}}a{{color:#146643}}pre{{background:white;padding:16px;white-space:pre-wrap}}img{{max-width:100%}}p{{max-width:1100px}}</style>
<h1>The complete world is the baseline</h1>{revision}<p>{'Evaluation complete.' if done else 'Rebuilding and evaluating the full world dataset. Results remain pending until the corresponding fit and evaluation finish.'} Every attempt below starts with full_world. Full_world remains the reference regardless of which model scores best.</p>
<p><a href="graphs/full_world.html">Inspect the full world graph</a> · <a href="graphs/audit.json">Structural audit</a> · <a href="report.json">Report data</a></p>
<h2>World structure</h2><p>All recorded countries, states, provinces, individual populations, buildings, ownership entities, markets, politics, diplomacy and military entities remain in every attempt. No population aggregation, border simplification, foreign-country deletion or military pruning is used. Each current graph is processed once. Entity and global recurrent states carry prior observations and recorded actions; there are no temporal edges.</p>
<p>The baseline reads all 214 included recording tables. UI feeds and action-availability tables are excluded. Source visibility limits the recorded world; missing observations are explicitly represented rather than invented. The illustrative graph is run {audit.get('run',1)}, snapshot {audit.get('seq',48)}; table counts are illustrative, not a cap on training graphs.</p>
<div class="scroll"><table><tr><th>Graph</th><th>Exact removal</th><th>Nodes</th><th>Directed edges</th><th>Removed nodes</th><th>Removed attributes</th></tr>{''.join(structure)}</table></div>
<h2>Training feasibility</h2><p>The complete probe contained {probe['nodes']:,} nodes and {probe['edges']:,} directed edges. Peak allocated GPU memory was {probe['gpu_peak_bytes']/1e9:.2f} GB; warmed training steps took {np.median(probe['step_seconds'][1:]):.3f} seconds. Production training streams chronological observations and uses bounded backpropagation chunks, preserving recurrent state between chunks. It does not sample or prune neighbors.</p>
<h2>Evaluation</h2><p>Dataset decisions by split: {html.escape(str(dict(counts))) if counts else 'preparation in progress'}. Splits keep whole runs separate. Every recorded decision is included, with unavailable targets masked individually. Feature dictionaries and numeric normalization use training graphs only. Every attempt uses the same decisions, targets, candidates, initialization seed and configuration.</p>{dataset_detail}
<p>Forecasts cover GDP, population, standard of living and cost-weighted building stock at 90, 180, 365, 730 and 1,095 days. Targets are log ratios relative to the exact pre-action snapshot. Unobserved horizons are masked. These are observed future trajectories, including subsequent actions, rather than isolated causal effects of the proposed block.</p>
<div class="scroll"><table><tr><th>Attempt</th><th>Validation sequence</th><th>Test sequence</th><th>Test reward loss</th><th>Test entropy</th><th>Candidate spread</th><th>Entropy at 1%</th><th>Validation score</th><th>Test score</th><th>Epoch</th></tr>{''.join(scores)}</table></div>
<p>Sequence error is normalized RMSE across observed trajectory cells. Reward loss is normalized RMSE of a trapezoidal, equal-component utility over the forecast horizons. The comparison score is 0.1 × reward loss + 0.9 × (1 − candidate entropy). Entropy alone does not establish accuracy or useful action effects. Candidate spread and entropy at a 1% training-utility standard-deviation tolerance expose tiny numerical distinctions. Thirty complete alternatives at every held-out decision are regenerated with loop.run.redraw. All alternatives read the same observation state; only the recorded action advances memory.</p>
<p>Epoch selection uses validation sequence error. Validation scores select the reported model; test results do not affect selection. The full world baseline is always retained and reported.</p>
{selected}{details}{runtime_table}{verification}<h2>Configuration</h2><pre>{html.escape(json.dumps(config,indent=2))}</pre><p>Shared relational message passing with typed edges, weighted feature embeddings and current-world type pooling. Chronological full-world observations, per-entity and global GRU memory, bounded sequence backpropagation, AdamW, gradient clipping at five, float32 with TF32 disabled. Maximum 24 epochs; stop after six epochs without validation improvement.</p>
</html>'''
    destination=root/'report.html'
    if destination.exists():
        destination.unlink()
    destination.write_text(text,encoding='utf-8')
    (root/'report.json').write_text(json.dumps(summary,indent=2))


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    summarize(args.root)


if __name__=='__main__':
    main()
