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

const VIEWS = ["config", "initializer", "picker", "outcomes"];

function Meta({
  table,
  title,
  run,
  fixed = [],
  initial,
  onRow,
}: {
  table: string;
  title?: string;
  run: number;
  fixed?: string[];
  initial?: { sort: string; desc: boolean };
  onRow?: (row: Cell[], grid: Grid) => void;
}) {
  return (
    <Section title={title ?? table}>
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
  const view = useTab(["decisions", "model", "importance"], "picker_view");
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
      <Tabs views={["decisions", "model", "importance"]} param="picker_view" />
      {view === "model" && <Meta title="CatBoost model" table="pick_model" run={run} />}
      {view === "importance" && <Meta
        title="CatBoost feature importance"
        table="pick_importance"
        run={run}
        initial={{ sort: "importance", desc: true }}
      />}
      {view === "decisions" && pause === null && <Section title="Decision snapshots">
        <p className="text-dim mb-3 text-xs">Inspect a decision snapshot to compare every action block CatBoost scored, ranked best first.</p>
        <DataGrid
          id="pauses"
          url={`/api/policy/runs/${run}/pauses`}
          onRow={(row) =>
            row[0].ref && set({ pause: String(row[0].ref.id), candidate: null })
          }
          live
        />
      </Section>}
      {view === "decisions" && pause !== null && <nav className="flex flex-wrap items-center gap-4 text-sm" aria-label="Policy decision">
        <button className="linka" onClick={() => set({ pause: null, candidate: null })}>All decision snapshots</button>
        <Link className="linka" to={`/runs/${run}/snapshots/${pause}`}>Snapshot {pause}</Link>
        {candidate !== null && <><button className="linka" onClick={() => set({ candidate: null })}>All candidates</button><span>Candidate {candidate}</span></>}
      </nav>}
      {view === "decisions" && pause !== null && (
        <Section title="Ranked action blocks">
        <p className="text-dim mb-3 text-xs">Higher predicted scores rank first. Chosen marks the block selected for execution; tied scores share a rank. Arrows show action order, including repeats. Saved alternatives contain action names only, without target parameters.</p>
        <DataGrid
          key={`c${pause}`}
          id={`candidate_blocks.${pause}`}
          url={`/api/policy/runs/${run}/pauses/${pause}/candidates`}
          initial={{ sort: "rank", desc: false }}
          onRow={(row, grid) =>
            set({
              candidate: String(
                row[grid.columns.findIndex((c) => c.name === "candidate")].num,
              ),
            })
          }
        />
        </Section>
      )}
      {view === "decisions" && pause !== null && candidate !== null && (
        <Meta
          key={`a${pause}.${candidate}`}
          title={`Actions in block ${candidate}`}
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
  const initializerView = useTab(["weights", "proposals", "candidates", "importance", "observations"], "initializer_view");
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
      <Tabs views={VIEWS} labels={{ config: "Overview", initializer: "Action weights", picker: "Block selection", outcomes: "Objectives & outcomes" }} />
      <Loading state={record}>
        {(g) => (
          <div className="space-y-4">
            {view === "config" && <Section title="How this run chooses actions">
              <div className="space-y-4 text-sm">
                <div><Link className="linka font-semibold" to={`?view=initializer`}>1. Initialize action weights</Link><p className="text-dim">{text(g, "initializer")} sets the weights used to sample actions into candidate blocks.</p></div>
                <div><Link className="linka font-semibold" to={`?view=picker`}>2. Select an action block</Link><p className="text-dim">{text(g, "picker")} chooses which generated block to execute at each decision.</p></div>
                <div><Link className="linka font-semibold" to={`?view=outcomes`}>3. Score the outcome</Link><p className="text-dim">The objective combines economic and population gains into a reward.</p></div>
              </div>
            </Section>}
            {view === "outcomes" && <>
              <Section title="Objective weights"><Record grid={only(g, "config")} /></Section>
              <Section title="Measured reward"><Loading state={reward}>{(r) => <Reward reward={r} />}</Loading></Section>
            </>}
            {view === "initializer" && <>
              <Section title="Weight initializer"><Record grid={only(g, "initializer")} /></Section>
              <p className="text-dim text-sm">These are the action sampling weights used by this run. Higher weights make eligible actions more likely to be proposed; zero disables an action.</p>
              {text(g, "initializer") === "random" && <p className="text-dim text-sm">The table shows this run’s recorded weights, including uniform or disabled weights in older runs.</p>}
              {text(g, "initializer") === "random_smac_weighting" && <Tabs views={["weights", "proposals", "candidates", "importance", "observations"]} param="initializer_view" labels={{ weights: "Run weights", proposals: "SMAC proposal", candidates: "SMAC alternatives", importance: "SMAC importance", observations: "SMAC observations" }} />}
              {(text(g, "initializer") !== "random_smac_weighting" || initializerView === "weights") && <Section title="Run action weights"><DataGrid id="run_weights" url="/api/policy/weights" fixed={[`run:${run}`]} columns={text(g, "initializer") === "random_smac_weighting" ? ['action', 'weight', 'method'] : ['action', 'weight']} initial={{ sort: "weight", desc: true }} live /></Section>}
              {text(g, "initializer") === "random_smac_weighting" && initializerView === "proposals" && <Meta title="How SMAC selected these weights" table="smac_proposal" run={run} />}
              {text(g, "initializer") === "random_smac_weighting" && initializerView === "candidates" && <Meta title="Alternative weight proposals" table="smac_candidate" run={run} initial={{ sort: "rank", desc: false }} />}
              {text(g, "initializer") === "random_smac_weighting" && initializerView === "importance" && <Meta title="Action weight importance" table="smac_importance" run={run} initial={{ sort: "importance", desc: true }} />}
              {text(g, "initializer") === "random_smac_weighting" && initializerView === "observations" && <Meta title="Runs observed by SMAC" table="smac_observation" run={run} />}
            </>}
            {view === "picker" && (
              <>
                <Section title="Block picker"><Record grid={only(g, "picker")} /></Section>
                <p className="text-dim text-sm">The picker selects a block after the initializer’s weighted sampling generates the alternatives.</p>
                {text(g, "picker") === "first" && <p className="text-dim text-sm">This picker executes the first generated block without model scoring.</p>}
                {text(g, "picker") === "catboost" && <Picker run={run} />}
              </>
            )}
          </div>
        )}
      </Loading>
    </div>
  );
}
