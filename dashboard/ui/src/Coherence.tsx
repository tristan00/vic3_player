import { useApi } from './api'
import { num, time } from './format'
import { Facts, Grid, Panel, Pill, Waiting, type Col } from './Grid'

const TONES: Record<string, string> = { 'in range': 'good', similar: 'good', 'in band': 'good', below: 'bad', above: 'bad', differs: 'bad', outside: 'bad' }

const flag: Col = { name: 'flag', render: (row) => <Pill value={row.flag} tone={TONES[row.flag] ?? 'plain'} /> }

const range: Col[] = [
  { name: 'value', kind: 'num' },
  { name: 'low', label: 'vanilla low', kind: 'num', group: 'vanilla recognized' },
  { name: 'median', label: 'vanilla median', kind: 'num', group: 'vanilla recognized' },
  { name: 'high', label: 'vanilla high', kind: 'num', group: 'vanilla recognized' },
  flag,
]

export function Coherence({ run }: { run: number }) {
  const found = useApi(`/api/runs/${run}/coherence`)
  return (
    <Waiting loaded={found}>
      {() => {
        const data = found.data
        return (
          <>
            <Facts
              items={[
                ['measured in', `${num(data.measured_ms)} ms`],
                ['game build', data.build],
                ['vanilla measured', time(data.reference_measured)],
                ['country measures out of range', num(data.flagged.countries)],
                ['state measures out of range', num(data.flagged.states)],
                ['map objects differing', num(data.flagged.objects)],
                ['map ratios and checks outside', num(data.flagged.shares)],
              ]}
            />
            <Panel title="Countries" extra="measures outside the range of vanilla recognized countries">
              <Grid
                search={false}
                rows={data.overview}
                sort={{ name: 'out', desc: true }}
                columns={[
                  { name: 'country', kind: 'text' },
                  { name: 'type', kind: 'name' },
                  { name: 'measures', kind: 'int' },
                  { name: 'out', label: 'out of range', kind: 'int' },
                  { name: 'in_range', label: 'in range', kind: 'share' },
                  ...data.domains.map((name: string) => ({ name, kind: 'int', group: 'out of range by domain' })),
                ]}
              />
            </Panel>
            <Panel title="Country measures">
              <Grid rows={data.countries} facets={['flag', 'domain', 'country']} picked={{ flag: ['below', 'above'] }} sort={{ name: 'measure' }}
                columns={[{ name: 'country', kind: 'text' }, { name: 'domain', kind: 'name' }, { name: 'measure', kind: 'name' }, ...range]} />
            </Panel>
            <Panel title="State measures">
              <Grid rows={data.states} facets={['flag', 'domain', 'country']} picked={{ flag: ['below', 'above'] }} sort={{ name: 'measure' }}
                columns={[{ name: 'state', kind: 'text' }, { name: 'country', kind: 'text' }, { name: 'domain', kind: 'name' }, { name: 'measure', kind: 'name' }, ...range]} />
            </Panel>
            <Panel title="Map objects" extra="distribution distance from vanilla against the sample size limit">
              <Grid rows={data.objects} facets={['flag', 'level']} sort={{ name: 'distance', desc: true }}
                columns={[
                  { name: 'level', kind: 'name' },
                  { name: 'measure', kind: 'name' },
                  { name: 'objects', kind: 'int' },
                  { name: 'undefined', kind: 'int' },
                  { name: 'median', kind: 'num' },
                  { name: 'vanilla_objects', label: 'vanilla objects', kind: 'int' },
                  { name: 'vanilla_median', label: 'vanilla median', kind: 'num' },
                  { name: 'distance', kind: 'num' },
                  { name: 'limit', kind: 'num' },
                  flag,
                ]} />
            </Panel>
            <Panel title="Map ratios and checks" extra="share against vanilla's band">
              <Grid rows={data.shares} facets={['flag', 'kind']} sort={{ name: 'measure' }}
                columns={[
                  { name: 'kind', kind: 'name' },
                  { name: 'measure', kind: 'name' },
                  { name: 'value', kind: 'num' },
                  { name: 'cases', kind: 'int' },
                  { name: 'vanilla', kind: 'num' },
                  { name: 'low', label: 'band low', kind: 'num' },
                  { name: 'high', label: 'band high', kind: 'num' },
                  flag,
                ]} />
            </Panel>
          </>
        )
      }}
    </Waiting>
  )
}
