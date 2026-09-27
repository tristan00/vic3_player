import { Link, useParams, useSearchParams } from "react-router-dom";
import { DataGrid, Record } from "@/components/DataGrid";
import { Neighbors } from "@/components/Neighbors";
import { Card, Loading, Section, Tabs, useTab } from "@/components/primitives";
import {
  useApi,
  type Cell,
  type Grid,
  type GridColumn,
  type S,
} from "@/lib/api";
import { num } from "@/lib/format";

const PARTS: [keyof S["RewardPart"], string][] = [
  ["weight", "weight"],
  ["gain", "gain"],
  ["years_alpha", "years^alpha"],
  ["gain_per_years_alpha", "gain / years^alpha"],
  ["scale", "scale"],
  ["normalized", "normalized"],
  ["contribution", "weighted"],
];

export function policyLink(col: GridColumn, cell: Cell) {
  return col.kind === "run" && cell.ref
    ? `/policy/runs/${cell.ref.id}`
    : undefined;
}

function only(grid: Grid, group: string): Grid {
  const keep = grid.columns
    .map((c, i) => ({ c, i }))
    .filter(({ c }) => c.group === group);
  return {
    ...grid,
    columns: keep.map(({ c }) => ({ ...c, group: null })),
    rows: grid.rows.map((row) => keep.map(({ i }) => row[i])),
  };
}

function text(grid: Grid, name: string): string | null | undefined {
  return grid.rows[0]?.[grid.columns.findIndex((c) => c.name === name)]?.text;
}

function Reward({ reward }: { reward: S["RunReward"] }) {
  if (!reward.parts.length)
    return <Card className="text-dim w-fit px-3 py-2 text-xs">not scored</Card>;
  const total = reward.parts.reduce((a, p) => a + p.contribution, 0);
  return (
    <Card className="w-fit max-w-full overflow-hidden">
      <table className="text-xs">
        <thead>
          <tr className="border-line text-dim border-b">
            <th className="px-2 py-1 text-left font-medium">component</th>
            <th className="px-2 py-1 text-right font-medium">years</th>
            {PARTS.map(([k, label]) => (
              <th key={k} className="px-2 py-1 text-right font-medium">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {reward.parts.map((p) => (
            <tr key={p.component} className="border-line/60 border-b">
              <td className="px-2 py-0.5">{p.component}</td>
              <td className="num px-2 py-0.5 text-right">
                {num(reward.years as number)}
              </td>
              {PARTS.map(([k]) => (
                <td key={k} className="num px-2 py-0.5 text-right">
                  {num(p[k] as number)}
                </td>
              ))}
            </tr>
          ))}
          <tr>
            <td className="px-2 py-0.5">reward</td>
            <td colSpan={PARTS.length} />
            <td className="num px-2 py-0.5 text-right font-semibold">
              {num(total)}
            </td>
          </tr>
        </tbody>
      </table>
    </Card>
  );
}

const VIEWS = ["config", "initializer", "picker"];

function Meta({
  table,
  run,
  fixed = [],
  initial,
  onRow,
}: {
  table: string;
  run: number;
  fixed?: string[];
  initial?: { sort: string; desc: boolean };
  onRow?: (row: Cell[], grid: Grid) => void;
}) {
  return (
    <Section title={<span className="num">{table}</span>}>
      <DataGrid
        id={table}
        url={`/api/meta/${table}`}
        fixed={[`run_id:${run}`, ...fixed]}
        link={policyLink}
        initial={initial}
        onRow={onRow}
        live
      />
    </Section>
  );
}

function Picker({ run }: { run: number }) {
  const [params, setParams] = useSearchParams();
  const pause = params.get("pause");
  const candidate = params.get("candidate");
  const set = (changes: { [key: string]: string | null }) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    setParams(next, { replace: true });
  };
  return (
    <>
      <Meta table="pick_model" run={run} />
      <Meta
        table="pick_importance"
        run={run}
        initial={{ sort: "importance", desc: true }}
      />
      <Section title="pauses">
        <DataGrid
          id="pauses"
          url={`/api/policy/runs/${run}/pauses`}
          onRow={(row) =>
            row[0].ref && set({ pause: String(row[0].ref.id), candidate: null })
          }
          live
        />
      </Section>
      {pause !== null && (
        <Meta
          key={`c${pause}`}
          table="pick_candidate"
          run={run}
          fixed={[`seq:${pause}`]}
          initial={{ sort: "predicted_change", desc: true }}
          onRow={(row, grid) =>
            set({
              candidate: String(
                row[grid.columns.findIndex((c) => c.name === "candidate")].num,
              ),
            })
          }
        />
      )}
      {pause !== null && candidate !== null && (
        <Meta
          key={`a${pause}.${candidate}`}
          table="pick_candidate_action"
          run={run}
          fixed={[`seq:${pause}`, `candidate:${candidate}`]}
        />
      )}
    </>
  );
}

export function PolicyRun() {
  const run = Number(useParams().run);
  const reward = useApi<S["RunReward"]>(`/api/policy/runs/${run}/reward`, {
    live: true,
  });
  const info = useApi<S["RunInfo"]>(`/api/runs/${run}`, { live: true });
  const record = useApi<Grid>(`/api/policy/runs/${run}`, { live: true });
  const view = useTab(VIEWS);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline gap-3 text-sm">
        <Link className="linka text-xs" to="/policy">
          policy
        </Link>
        {info.data && (
          <Neighbors
            previous={info.data.previous}
            next={info.data.next}
            to={(n) => `/policy/runs/${n}`}
          >
            <h1 className="num font-semibold">run {run}</h1>
          </Neighbors>
        )}
        <Link className="linka text-xs" to={`/runs/${run}`}>
          run page
        </Link>
      </div>
      <Tabs views={VIEWS} />
      <Loading state={record}>
        {(g) => (
          <div className="space-y-4">
            {view === "config" && (
              <>
                <Record grid={only(g, "config")} />
                <Section title="reward">
                  <Loading state={reward}>
                    {(r) => <Reward reward={r} />}
                  </Loading>
                </Section>
              </>
            )}
            {view === "initializer" && (
              <>
                <Record grid={only(g, "initializer")} />
                <Meta
                  table="run_weight"
                  run={run}
                  initial={{ sort: "weight", desc: true }}
                />
                {text(g, "initializer") === "random_smac_weighting" && (
                  <>
                    <Meta table="smac_proposal" run={run} />
                    <Meta
                      table="smac_importance"
                      run={run}
                      initial={{ sort: "importance", desc: true }}
                    />
                    <Meta table="smac_candidate" run={run} />
                    <Meta table="smac_observation" run={run} />
                  </>
                )}
              </>
            )}
            {view === "picker" && (
              <>
                <Record grid={only(g, "picker")} />
                {text(g, "picker") === "catboost" && <Picker run={run} />}
              </>
            )}
          </div>
        )}
      </Loading>
    </div>
  );
}
