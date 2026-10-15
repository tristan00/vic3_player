import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useApi } from './api'
import { Legend } from './charts'
import { colors, heading, num } from './format'
import { Facts, Grid, Panel, Waiting, columnsOf } from './Grid'
import { runColumns } from './Runs'

function WorldMap({ world, map }: { world: number; map: any }) {
  const canvas = useRef<HTMLCanvasElement | null>(null)
  const source = useRef<ImageData | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  const owners = [...new Set(Object.values(map.owners) as string[])]
  const palette = colors(owners)
  useEffect(() => {
    const image = new Image()
    image.onload = () => {
      const element = canvas.current
      if (!element) return
      element.width = image.width
      element.height = image.height
      const context = element.getContext('2d', { willReadFrequently: true })!
      context.drawImage(image, 0, 0)
      const pixels = context.getImageData(0, 0, image.width, image.height)
      source.current = new ImageData(new Uint8ClampedArray(pixels.data), image.width, image.height)
      const fill = new Map<number, [number, number, number]>()
      for (const [color, state] of Object.entries(map.provinces) as [string, string][]) {
        const paint = palette[map.owners[state]]
        fill.set(parseInt(color.slice(1), 16), [parseInt(paint.slice(1, 3), 16), parseInt(paint.slice(3, 5), 16), parseInt(paint.slice(5, 7), 16)])
      }
      const data = pixels.data
      for (let index = 0; index < data.length; index += 4) {
        const found = fill.get((data[index] << 16) | (data[index + 1] << 8) | data[index + 2])
        data[index] = found ? found[0] : 228
        data[index + 1] = found ? found[1] : 233
        data[index + 2] = found ? found[2] : 240
      }
      context.putImageData(pixels, 0, 0)
    }
    image.src = `/api/worlds/${world}/image/provinces.png`
  }, [world])
  const point = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const pixels = source.current
    const element = canvas.current
    if (!pixels || !element) return
    const box = element.getBoundingClientRect()
    const x = Math.floor(((event.clientX - box.left) / box.width) * pixels.width)
    const y = Math.floor(((event.clientY - box.top) / box.height) * pixels.height)
    const at = (y * pixels.width + x) * 4
    const key = 'x' + [pixels.data[at], pixels.data[at + 1], pixels.data[at + 2]].map((part) => part.toString(16).padStart(2, '0')).join('').toUpperCase()
    const state = map.provinces[key]
    setHover(state ? `${map.names[state]} · ${map.owners[state]}` : null)
  }
  return (
    <Panel title="Map" extra={hover ?? 'by owner'}>
      <Legend palette={palette} keys={owners.sort()} />
      <canvas ref={canvas} className="map" onMouseMove={point} onMouseLeave={() => setHover(null)} />
    </Panel>
  )
}

export function Worlds() {
  const [all, setAll] = useState(false)
  const worlds = useApi('/api/worlds')
  const bank = useApi('/api/bank')
  return (
    <div className="page">
      <h1>Worlds</h1>
      <Waiting loaded={bank}>
        {() =>
          bank.data.banks.map((found: any) => (
            <Panel key={found.directory} title="World bank" extra={found.directory}>
              <Facts items={[['worlds', num(found.worlds)], ['seed', String(found.seed)], ['created', found.created], ['build seconds', num(found.seconds)], ['workers', num(found.workers)], ...Object.entries(found.knobs).map(([name, range]: [string, any]) => [`${name} min / median / max`, `${num(range.min)} / ${num(range.median)} / ${num(range.max)}`] as [string, string])]} />
            </Panel>
          ))
        }
      </Waiting>
      <Waiting loaded={worlds}>
        {() => {
          const played = worlds.data.rows.filter((row: any) => row.runs > 0)
          const rows = all ? worlds.data.rows : played
          return (
            <>
              <div className="lead">
                <span className="choice">
                  <a className={all ? '' : 'on'} onClick={() => setAll(false)}>
                    with runs {played.length}
                  </a>
                  <a className={all ? 'on' : ''} onClick={() => setAll(true)}>
                    all {worlds.data.rows.length}
                  </a>
                </span>
              </div>
              <Grid key={String(all)} sync fold rows={rows} sort={{ name: 'world', desc: true }} columns={columnsOf(rows, [{ name: 'world', kind: 'world' }, { name: 'world_file', label: 'world file', kind: 'text' }, { name: 'runs', kind: 'int' }, { name: 'last_run', label: 'last run', kind: 'run' }, { name: 'seed', kind: 'text' }])} />
            </>
          )
        }}
      </Waiting>
    </div>
  )
}

export function World() {
  const world = Number(useParams().world)
  const detail = useApi(Number.isInteger(world) ? `/api/worlds/${world}` : null)
  const runs = useApi('/api/runs')
  if (!Number.isInteger(world))
    return (
      <div className="page">
        <div className="problem">no world</div>
      </div>
    )
  return (
    <div className="page">
      <h1>
        World {world}
        <span className="extra">
          <Link to="/worlds">all worlds</Link>
        </span>
      </h1>
      <Waiting loaded={detail}>
        {() => {
          const found = detail.data
          return (
            <>
              <Facts items={Object.entries(found.settings).map(([name, value]) => [name, typeof value === 'number' && name !== 'seed' ? num(value) : String(value)])} />
              {found.map && <WorldMap world={world} map={found.map} />}
              <div className="columns two">
                <Panel title="Relations">
                  <Grid rows={found.relations} search={false} page={20} sort={{ name: 'relations', desc: true }} columns={[{ name: 'country' }, { name: 'with' }, { name: 'relations', kind: 'int' }]} />
                </Panel>
                <Panel title="Pacts">
                  <Grid rows={found.pacts} search={false} page={20} columns={[{ name: 'country' }, { name: 'with' }, { name: 'pact', kind: 'name' }]} />
                </Panel>
              </div>
              {['countries', 'blocs', 'states']
                .filter((name) => found.lists[name])
                .map((name) => (
                  <Panel key={name} title={heading(name)}>
                    <Grid fold rows={found.lists[name]} search={found.lists[name].length > 12} page={20} columns={columnsOf(found.lists[name])} />
                  </Panel>
                ))}
              <Panel title="Runs">
                <Waiting loaded={runs}>{() => <Grid rows={runs.data.rows.filter((row: any) => row.world === world)} search={false} sort={{ name: 'run', desc: true }} columns={runColumns(runs.data).filter((column) => column.name !== 'world')} />}</Waiting>
              </Panel>
            </>
          )
        }}
      </Waiting>
    </div>
  )
}
