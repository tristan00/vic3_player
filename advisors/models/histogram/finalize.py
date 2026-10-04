import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pickle
import subprocess
import sys

import numpy as np

from interface.common import timed
from .tune import run_trial
from .validation import METRIC, Validation

PARAMETERS=Path(__file__).with_name('parameters.json')


@timed
def finalize(output):
    if (output/'cancelled.json').exists():
        raise RuntimeError('A cancelled search cannot be installed')
    config=json.loads((output/'search.json').read_text())
    status=json.loads((output/'status.json').read_text())
    source=Path(config['data'])
    if config['validation']['name']!=METRIC['name'] or hashlib.sha256(source.read_bytes()).hexdigest()!=config['data_sha256']:
        raise RuntimeError('The search metric or frozen data changed')
    if status['finished']!=status['requested']:
        raise RuntimeError('The search is unfinished')
    trials=[json.loads(path.read_text()) for path in output.glob('trial_*.json')]
    if len(trials)!=status['requested'] or sorted(row['trial'] for row in trials)!=list(range(status['requested'])):
        raise RuntimeError('The search is missing trial results')
    completed=[row for row in trials if row['stop'] is None and np.isfinite(row['score'])]
    if not completed:
        raise RuntimeError('No completed trial can be installed')
    selected=min(completed,key=lambda row:row['score'])
    if selected!=status['best']:
        raise RuntimeError('The selected winner disagrees with search status')
    with source.open('rb') as stream:
        data=pickle.load(stream)
    metric=Validation(data)
    if metric.configuration()!=config['validation'] or selected['trees']!=[selected['params']['iterations']]*len(data.folds):
        raise RuntimeError('The winner has inconsistent validation data or tree counts')
    verified=run_trial(-2,selected['params'],selected['sizes'],source,output,config['seconds_per_trial'],config['threads'])
    if verified['stop'] is not None:
        raise RuntimeError('Winner verification exceeded the hard limit')
    for name in metric.configuration()['constant']:
        if not np.isclose(verified[name],selected[name],rtol=1e-6,atol=1e-7):
            raise RuntimeError(f'Winner verification did not reproduce {name}')
    request=output/'fit_request.json'
    result=output/'fit.json'
    request.write_text(json.dumps({'params':selected['params'],'sizes':selected['sizes'],'data':str(source.resolve()),
                                   'threads':config['threads'],'output':str(result.resolve())},indent=2))
    subprocess.run([sys.executable,'-m','advisors.models.histogram.worker','--request',str(request.resolve()),'--fit'],
                   check=True,timeout=config['seconds_per_trial'])
    fit=json.loads(result.read_text())
    installed={'params':{**selected['params'],'thread_count':config['threads']},'sizes':selected['sizes']}
    previous=json.loads(PARAMETERS.read_text())
    (output/'previous_parameters.json').write_text(json.dumps(previous,indent=2)+'\n')
    temporary=PARAMETERS.with_suffix('.tmp')
    temporary.write_text(json.dumps(installed,indent=2)+'\n')
    temporary.replace(PARAMETERS)
    report={'installed_at':datetime.now(timezone.utc).isoformat(),'winner':selected,'installed':installed,'fit':fit,
            'previous':previous,'validation':config['validation']}
    (output/'deployment.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args()
    report=finalize(args.directory)
    print(json.dumps({'installed_trial':report['winner']['trial'],'score':report['winner']['score'],
                      'params':report['installed']['params']}),flush=True)


if __name__=='__main__':
    main()
