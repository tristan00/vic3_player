import argparse
import copy
import hashlib
import html
import json
from pathlib import Path
import time

import numpy as np
import psycopg
import torch

from interface.common import timed
from interface.recording.store import DSN
from .encoding import Encoder, Survey
from .model import Configuration, Network, collate
from .schema import GRAPH_VERSION
from .source import candidates, save
from .world import build_world, read_world
from .world_catalog import catalog
from .world_data import Identities, action_graph


TUNING=[
    ('Message operator','Relation-gated mean; relation-basis transforms; sparse typed attention','Preserve every recorded and spatial relation'),
    ('Hidden width','32, 48, 64, 96, 128','Measure full-graph memory before admitting a configuration'),
    ('Message rounds','2, 3, 4, 5, 6','Spatial pair nodes make one pair interaction a two-edge path'),
    ('Relation bases','4, 8, 16, 32','Only with basis transforms; retain individual relation identities'),
    ('Attention heads','1, 2, 4, 8','Only with attention; heads divide total hidden width'),
    ('Relation aggregation','Joint mean; per-relation normalization and learned mixing','Keep geography, military, economic and spatial channels distinguishable'),
    ('Spatial numeric encoder','Current weighted features; joint MLP of displacement, distance and direction','Every geometric feature remains available'),
    ('World readout','Equal type means; learned type weights; action-conditioned pooling','Keep full graph processing before the prediction summary'),
    ('Action block','Current pooling; ordered GRU; ordered attention','Encode each historical block and the proposed block separately, preserving order and parameters'),
    ('Recurrent state','Per-entity GRU and global observation/action GRUs','Process every observation in order; commit only the recorded or selected block'),
    ('Backpropagation length','2, 4, 8 observations after memory checks','Carry state across the entire run; detach gradients between chunks'),
    ('Learning rate','0.0001 to 0.003, logarithmic','AdamW'),
    ('Weight decay','0, or 0.000001 to 0.01, logarithmic','AdamW'),
    ('Dropout','0 to 0.4','Hidden activations'),
    ('Schedule','Constant; cosine decay; validation plateau','Optional 0%, 5% or 10% initial warmup'),
    ('Sequence chunks','Chronological observations within each run','Shuffle runs only; reset memory between runs'),
    ('Gradient clipping','0.5, 1, 2, 5','Shared stopping budget across comparable trials')
]


@timed
def map_plot(root,data,graph):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    geometry=data['geography']['map']
    width,height=geometry['width'],geometry['height']
    colors=np.full((*geometry['raster'].shape,3),.88,np.float32)
    terrain={p:t for p,r,t,a,x,y in data['geography']['provinces']}
    for province,kind in terrain.items():
        if kind in ('ocean','lakes'):
            colors[geometry['raster']==province]=(.73,.85,.91)
    fig,ax=plt.subplots(figsize=(12,6),layout='constrained')
    ax.imshow(np.flipud(colors),origin='lower',extent=(0,width,0,height))
    formations=[n for n in graph.nodes if n['seq']==data['seq'] and n['kind']=='formation' and 'position' in n]
    owners={r['formation']:r['country'] for r in data['states'][data['seq']]['formation_history']}
    for domestic,label,color in ((True,'Player formations','#146b41'),(False,'Foreign formations','#a8324a')):
        nodes=[n for n in formations if (owners[n['key']]==data['player'])==domestic]
        ax.scatter([n['position']['x'] for n in nodes],[n['position']['y'] for n in nodes],s=22,c=color,label=label,edgecolors='white',linewidths=.4)
    fronts=[n for n in graph.nodes if n['seq']==data['seq'] and n['kind']=='front' and 'position' in n]
    if fronts:
        ax.scatter([n['position']['x'] for n in fronts],[n['position']['y'] for n in fronts],s=45,c='#422b8f',marker='x',label='Front positions')
    ax.set(xlim=(0,width),ylim=(0,height),xlabel='Game map x',ylabel='Game map y',title=f'Run {data["run"]}, snapshot {data["seq"]}: positions on the recorded province raster')
    ax.legend(loc='upper right')
    fig.savefig(root/f'map_{data["run"]}_{data["seq"]}.png',dpi=130)
    plt.close(fig)


@timed
def accessibility(data,actions):
    moved=copy.deepcopy(data)
    row=next(r for r in moved['states'][moved['seq']]['formation_status'] if r['x'] is not None and r['y'] is not None)
    width=moved['geography']['map']['width']
    original=row['x']
    row['x']=original+min(20.,width/20) if original<width/2 else original-min(20.,width/20)
    worlds=[build_world(source)[0] for source in (data,moved)]
    changed_actions=[('raise_taxes',{'level':'very_high'})] if actions!=[('raise_taxes',{'level':'very_high'})] else [('lower_taxes',{'level':'very_low'})]
    proposals=[action_graph(graph,source,actions) for graph,source in zip(worlds,(data,moved))]
    proposals.append(action_graph(worlds[0],data,changed_actions))
    survey=Survey()
    for graph in worlds+proposals:
        survey.add(graph)
    encoder=Encoder([survey.mapping()])
    identities=Identities()
    packed=[]
    for graph in worlds:
        encoded=encoder.graph(graph)
        encoded['identity']=identities.graph(graph)
        packed.append(collate([encoded],'cuda'))
    deltas=[encoder.graph(graph) for graph in proposals]
    torch.manual_seed(41)
    torch.cuda.manual_seed_all(41)
    torch.backends.cuda.matmul.allow_tf32=False
    model=Network(len(encoder.tokens),len(encoder.kinds)+1,len(encoder.relations)+1,Configuration()).cuda().eval()
    torch.cuda.reset_peak_memory_stats()
    def predict(world,prior):
        observation=model.observe(packed[0],None,0)
        memory=model.commit(observation,model.propose(observation,deltas[prior]))
        following=model.observe(packed[world],memory,1)
        return model.propose(following,deltas[world]).prediction,memory
    output,memory=predict(0,0)
    memory.global_state.retain_grad()
    output.square().sum().backward()
    gradient=float(model.feature.weight.grad[encoder.tokens['number','distance_pixels']].abs().sum())
    history_gradient=float(memory.global_state.grad.abs().sum())
    first_prediction=output.detach().cpu().numpy()
    model.zero_grad(set_to_none=True)
    del output,memory
    with torch.inference_mode():
        repeated_prediction=predict(0,0)[0].cpu().numpy()
        second_prediction=predict(1,0)[0].cpu().numpy()
        third_prediction=predict(0,2)[0].cpu().numpy()
    difference=float(abs(second_prediction-first_prediction).max())
    history_difference=float(abs(third_prediction-first_prediction).max())
    repeat_difference=float(abs(repeated_prediction-first_prediction).max())
    if not min(gradient,history_gradient)>0 or not min(difference,history_difference)>max(1e-8,repeat_difference*4) or not np.isfinite([second_prediction,third_prediction]).all():
        raise ValueError('Spatial or prior action change did not reach the recurrent model')
    result={'probe':'untrained fixed-seed network; two synthetic consecutive observations of one recorded world; input accessibility, not forecast accuracy',
            'formation':row['formation'],'x_before':original,'x_after':row['x'],'distance_embedding_gradient':gradient,
            'max_output_change':difference,'gpu_peak_bytes':torch.cuda.max_memory_allocated(),
            'historical_actions_before':actions,'historical_actions_after':changed_actions,
            'prior_action_state_gradient':history_gradient,'history_max_output_change':history_difference,
            'identical_input_repeat_max_change':repeat_difference,
            'nodes':len(worlds[0].nodes),'edges':len(worlds[0].edges),'graph_version':GRAPH_VERSION}
    del model
    torch.cuda.empty_cache()
    return result


@timed
def review(root,cases):
    root.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(4)
    results=[]
    probe=None
    for index,(run,seq) in enumerate(cases):
        started=time.monotonic()
        with psycopg.connect(DSN) as connection:
            connection.execute('set transaction isolation level repeatable read read only')
            data=read_world(connection,run,seq)
            seed=20261001+run*1009+seq
            blocks=candidates(connection,run,seq,30,seed)
        graph,audit=build_world(data,blocks[0])
        (root/f'audit_{run}_{seq}.json').write_text(json.dumps(audit,indent=2))
        map_plot(root,data,graph)
        if index==0:
            output=root/'full_world'
            output.mkdir(exist_ok=True)
            save(output/'source.pkl.gz',data)
            (output/'candidates.json').write_text(json.dumps({'seed':seed,'generator':'loop.run.redraw','blocks':blocks},indent=2))
            catalog(root,data,blocks[0])
            probe=accessibility(data,blocks[0])
            (root/'accessibility.json').write_text(json.dumps(probe,indent=2))
        result={'run':run,'seq':seq,'nodes':len(graph.nodes),'edges':len(graph.edges),
                'map':audit['map'],'spatial':audit['spatial'],'history':data['history'],
                'action_history':audit['action_history'],'seconds':time.monotonic()-started}
        results.append(result)
        print(json.dumps(result),flush=True)
        del data,graph
    result={'graph_version':GRAPH_VERSION,'cases':results,'accessibility':probe,'tuning_proposal':TUNING,
            'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')}}
    (root/'review.json').write_text(json.dumps(result,indent=2))
    rows=''
    figures=''
    sequences=''
    for case in results:
        last=case['spatial'][-1]
        rows+='<tr>'+''.join(f'<td>{value}</td>' for value in (f'<a href="audit_{case["run"]}_{case["seq"]}.json">{case["run"]} / {case["seq"]}</a>',
              f'{case["nodes"]:,}',f'{case["edges"]:,}',f'{last["located_formations"]} / {last["formations"]}',last['located_fronts'],
              last['pairs'].get('formation',0),last['pairs'].get('state',0),last['pairs'].get('front',0),last['crossings'],
              sum(last['nearest_borders'].values()),len(last['recorded_province_disagreements'])))+'</tr>'
        figures+=f'<img src="map_{case["run"]}_{case["seq"]}.png" alt="Recorded geography and military positions for run {case["run"]}">'
        action_counts={row['seq']:row['actions'] for row in case['action_history']}
        sequence=[]
        for seq in case['history']:
            sequence.append(f'State {seq}')
            if seq in action_counts:
                sequence.append(f'Recorded block ({action_counts[seq]} actions)')
        sequence.append('Current candidate')
        sequences+=f'<p><strong>Run {case["run"]}:</strong> '+ ' → '.join(sequence)+'</p>'
    ranges=''.join('<tr>'+''.join(f'<td>{html.escape(value)}</td>' for value in row)+'</tr>' for row in TUNING)
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Full world with spatial structure</title><style>body{{font:16px/1.55 system-ui;max-width:1350px;margin:32px auto;padding:0 24px;background:#f7f8f6;color:#182822}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #cbd6cf}}th{{background:#e0eae3}}img{{max-width:100%}}a{{color:#146b41}}.scroll{{overflow:auto}}</style>
<h1>Full world with spatial structure and action history</h1><p>Graph version {GRAPH_VERSION}. All previous world entities and included facts remain. Positions participate in explicit geographic and interformation relationships. History is carried in recurrent entity and world states. Each graph contains one observation and no temporal edges. This revision has been structurally checked and probed for model access; it has not been fitted or tuned.</p>
<p><a href="graphs/full_world.html">Inspect the full graph</a> · <a href="graphs/full_world.json.gz">Download the full graph</a> · <a href="review.json">Complete review data</a></p>
<h2>What the graph contains</h2><ul><li>Formation and front coordinate-point containment in the actual recorded province raster, with direct state links when the province has a state.</li><li>Common game coordinates for provinces, state centroids, formations and fronts; the image y axis is reversed explicitly.</li><li>Directed pair facts for every positioned formation to every other positioned formation, every positioned state and every front: relative x/y, distance, direction and coincidence. No nearest-neighbor cutoff or country filter.</li><li>Distinct land borders, coasts, water borders, horizontal wrap seams and recorded crossings, including their endpoint provinces.</li><li>Exact straight-line distance and direction from every positioned formation to its nearest coastline, land state border and land country border. All tied nearest points remain, linked to both bordering provinces.</li><li>Current entity and spatial facts with persistent identities for recurrent memory.</li></ul>
<p>Pair facts have origin and target edges so relative geometry stays associated with both entities. Same-country is recorded when known; foreign does not mean hostile. Coordinates and straight-line map distances do not assert access, travel time, combat range or an executed movement path.</p>
<h2>World and action sequence</h2><p>Every observation is processed once in snapshot order, including observations at the same game time. Entity and global GRUs carry memory across the run. The chosen block updates memory after forecasting; all alternatives read the same observation state. Training detaches gradients between bounded sequence chunks without resetting the carried state.</p>{sequences}<p>Recorded blocks retain order and parameters. No execution status, validation, verification or outcome flags become inputs or select examples. The current recorded decision and future blocks are never replayed before candidate scoring.</p>
<h2>Observed coverage</h2><p>All node, edge and spatial counts describe the current snapshot.</p><div class="scroll"><table><tr><th>Run / snapshot and audit</th><th>Nodes</th><th>Edges</th><th>Located formations</th><th>Located fronts</th><th>Formation pairs</th><th>Formation/state pairs</th><th>Formation/front pairs</th><th>Crossings</th><th>Nearest-border facts</th><th>Province disagreements</th></tr>{rows}</table></div>
{figures}<h2>Model access check</h2><p>Moving one formation changed the encoded geometry and the output of a fixed-seed untrained network. Maximum output change: {probe['max_output_change']:.7f}; distance-feature embedding gradient magnitude: {probe['distance_embedding_gradient']:.7f}. In a synthetic two-observation probe, changing the preceding block's duration while holding the world and current candidate fixed changed output by {probe['history_max_output_change']:.7f}; prior-action recurrent-state gradient magnitude: {probe['prior_action_state_gradient']:.7f}. Peak allocated GPU memory: {probe['gpu_peak_bytes']/1e9:.2f} GB. <a href="accessibility.json">Probe details</a>. These checks establish information flow, not useful predictions.</p>
<h2>Recording limits</h2><p>Missing or invalid positions and disagreements with recorded province IDs are audited. Recorded province links and coordinate-derived links both remain when they differ; an agreement flag reaches the model. A formation's map position is not silently treated as an authoritative replacement for its recorded province. Raw polymorphic current/target location codes remain metadata because the recording lacks their type discriminator; coordinate containment supplies geographic context independently. A destination is not guessed from a bare ID. State centroids summarize geometry and need not lie within a state's polygon. Full means the included recorded world plus these explicitly derived relationships, not unobserved game state.</p>
<h2>Revised tuning proposal</h2><p>Freeze this complete spatial graph. Tune processing, aggregation and readout. The ranges are a proposal; most architectural branches require an independent implementation. Existing checkpoints and packed data predate this revision and are rejected for current live inference or fitting. Rebuild the encoder and dataset before any tuning.</p><table><tr><th>Parameter</th><th>Range or choices</th><th>Condition or purpose</th></tr>{ranges}</table>
<p>Use a common epoch budget and stopping rule, compare architecture families on the same decisions and generated candidates, and repeat finalists across seeds. Report forecast accuracy separately from candidate differentiation. Preserve a fresh held-out set for final confirmation. No fitting or tuning was launched for this revision.</p></html>'''
    path=root/'report.html'
    if path.exists():
        path.unlink()
    path.write_text(page,encoding='utf-8')


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--cases',nargs='+',default=['1:48','101:26','207:88'])
    args=parser.parse_args()
    review(args.root,[tuple(map(int,item.split(':'))) for item in args.cases])


if __name__=='__main__':
    main()
