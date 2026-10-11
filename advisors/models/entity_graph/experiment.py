import torch

from interface.common import evidence, timed
from .model import Configuration, Network
from .schema import GRAPH_VERSION


@timed
def restore(path,device='cuda'):
    checkpoint=torch.load(path,map_location=device,weights_only=True)
    if checkpoint.get('graph_version')!=GRAPH_VERSION:
        raise ValueError(evidence(path=path,found=checkpoint.get('graph_version'),expected=GRAPH_VERSION))
    configuration=Configuration(**checkpoint['configuration'])
    model=Network(checkpoint['tokens'],checkpoint['kinds'],checkpoint['relations'],configuration).to(device)
    model.load_state_dict(checkpoint['state'])
    model.eval()
    return model,checkpoint

