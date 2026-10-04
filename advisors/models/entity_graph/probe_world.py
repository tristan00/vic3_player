import json
from pathlib import Path
import time

import torch

from interface.common import timed
from interface.timing import RECORDER
from .encoding import Encoder, Survey
from .model import Configuration, Network, collate
from .source import load
from .world import build_world
from .world_data import action_graph


@timed
def main():
    root=Path('artifacts/entity_graph_20261001')
    started=time.monotonic()
    data=load(root/'full_world/source.pkl.gz')
    actions=json.loads((root/'full_world/candidates.json').read_text())['blocks'][0]
    graph,summary=build_world(data)
    survey=Survey()
    survey.add(graph)
    delta=action_graph(graph,data,actions)
    survey.add(delta)
    encoder=Encoder([survey.mapping()])
    packed=encoder.graph(graph)
    torch.set_num_threads(4)
    configuration=Configuration()
    model=Network(len(encoder.tokens),len(encoder.kinds)+1,len(encoder.relations)+1,configuration).cuda()
    optimizer=torch.optim.AdamW(model.parameters())
    batch=collate([packed],'cuda')
    proposal=encoder.graph(delta)
    memory=None
    elapsed=[]
    torch.cuda.reset_peak_memory_stats()
    for step in range(4):
        tick=time.monotonic()
        optimizer.zero_grad(set_to_none=True)
        prediction,memory=model(batch,proposal,memory,float(step))
        loss=prediction.square().mean()
        loss.backward()
        optimizer.step()
        memory=memory.detach()
        torch.cuda.synchronize()
        elapsed.append(time.monotonic()-tick)
    result={'nodes':len(graph.nodes),'edges':len(graph.edges),'tokens':len(encoder.tokens),
            'packed_bytes':sum(v.nbytes for v in packed.values() if hasattr(v,'nbytes')),
            'gpu_peak_bytes':torch.cuda.max_memory_allocated(),'step_seconds':elapsed,
            'seconds':time.monotonic()-started,'configuration':configuration.mapping(),
            'timings':sorted(RECORDER.totals(),key=lambda row:-row[4])[:20]}
    (root/'full_world/probe.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    main()
