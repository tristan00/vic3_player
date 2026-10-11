from datetime import datetime, timezone
import json
import logging
from zipfile import ZipFile, ZIP_STORED

from interface.common import evidence, progress, timed

LOG=logging.getLogger('loop')
TAIL_BYTES=1<<20


@timed
def clock_failure(game,run_id,error):
    captured=datetime.now(timezone.utc)
    directory=game.data_dir/'incidents'
    directory.mkdir(parents=True,exist_ok=True)
    output=directory/f'run_{run_id}_clock_{captured.strftime("%Y%m%dT%H%M%S%f")}.zip'
    paths=[game.profile/'debug_store.log',game.session_file]
    paths+=sorted(path for path in (game.profile/'logs').glob('*.log') if path.name.split('.')[0] in ('debug','error','game'))
    files=[]
    with ZipFile(output,'x',compression=ZIP_STORED) as archive:
        for path in paths:
            progress('preserve clock-stall evidence')
            name=path.relative_to(game.profile).as_posix()
            try:
                with path.open('rb') as source:
                    size=source.seek(0,2)
                    offset=max(0,size-TAIL_BYTES)
                    source.seek(offset)
                    content=source.read(TAIL_BYTES)
            except OSError as failure:
                files.append({'name':name,'error':str(failure)})
                continue
            archive.writestr(name,content)
            files.append({'name':name,'size':size,'offset':offset,'saved':len(content)})
        archive.writestr('incident.json',json.dumps({'run':run_id,'captured_at':captured.isoformat(),
                                                   'error':str(error),'files':files},indent=2))
    LOG.error(evidence(output=str(output)))
    return output
