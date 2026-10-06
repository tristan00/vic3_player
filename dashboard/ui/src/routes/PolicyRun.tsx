import { Link, useParams, useSearchParams } from "react-router-dom";
import { DataGrid, Record } from "@/components/DataGrid";
import { Neighbors } from "@/components/Neighbors";
import { Pickers, PICKERS } from "@/components/Pickers";
import { Reward, RewardFormula } from "@/components/Reward";
import { Card, Loading, Section, Tabs, useTab } from "@/components/primitives";
import {
  useApi,
  type Cell,
  type Grid,
  type GridColumn,
  type S,
} from "@/lib/api";

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

const VIEWS = ["config", "initializer", "picker", "outcomes"];
const INITIALIZER_VIEWS: Record<string, Record<string, string>> = {
  random_smac_weighting: { weights: "Run weights", proposals: "SMAC proposal", candidates: "SMAC alternatives", importance: "SMAC importance", observations: "SMAC observations" },
  random_svr_weighting: { weights: "Run weights", proposals: "SVR proposal", coefficients: "SVR effects", observations: "SVR observations" },
};
const INITIALIZER_TABLES: Record<string, Record<string, { table: string; title: string; initial?: { sort: string; desc: boolean } }>> = {
  random_smac_weighting: {
    proposals: { table: "smac_proposal", title: "How SMAC selected these weights" },
    candidates: { table: "smac_candidate", title: "Alternative weight proposals", initial: { sort: "rank", desc: false } },
    importance: { table: "smac_importance", title: "Action weight importance", initial: { sort: "importance", desc: true } },
    observations: { table: "smac_observation", title: "Runs observed by SMAC" },
  },
  random_svr_weighting: {
    proposals: { table: "svr_proposal", title: "SVR proposal" },
    coefficients: { table: "svr_coefficient", title: "SVR effects", initial: { sort: "linear", desc: true } },
    observations: { table: "svr_observation", title: "Runs observed by SVR" },
  },
};
const WEIGHT_COLUMNS: Record<string, string[]> = {
  random: ["action", "weight", "centre"],
  random_smac_weighting: ["action", "weight", "method"],
  random_svr_weighting: ["action", "weight", "method", "svr_linear", "svr_squared"],
};

export function Initializers({ only }: { only?: string | null }) {
  const found = useApi<S["InitializerInfo"][]>("/api/policy/initializers");
  return (
    <Loading state={found}>
      {(list) => (
        <div className="grid gap-3 lg:grid-cols-3">
          {list.filter((i) => !only || i.name === only).map((i) => (
            <Card key={i.name} className="space-y-2 px-3 py-2 text-sm">
              <div className="font-semibold">{i.title} <span className="text-dim font-mono text-xs">{i.name}</span></div>
              <table className="text-xs">
                <tbody>
                  {i.settings.map((s) => (
                    <tr key={s.name}>
                      <td className="text-dim pr-3">{s.name}</td>
                      <td className="num">{s.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          ))}
        </div>
      )}
    </Loading>
  );
}

function Initializer({ run, name }: { run: number; name: string | null | undefined }) {
  const labels = name ? INITIALIZER_VIEWS[name] : undefined;
  const view = useTab(labels ? Object.keys(labels) : ["weights"], "initializer_view");
  const shown = name ? INITIALIZER_TABLES[name]?.[view] : undefined;
  return (
    <>
      <Initializers only={name} />
      {labels && <Tabs views={Object.keys(labels)} param="initializer_view" labels={labels} />}
      {shown
        ? <Meta key={shown.table} title={shown.title} table={shown.table} run={run} initial={shown.initial} />
        : <Section title="Run action weights"><DataGrid id="run_weights" url="/api/policy/weights" fixed={[`run:${run}`]} columns={(name && WEIGHT_COLUMNS[name]) || ["action", "weight"]} initial={{ sort: "weight", desc: true }} live /></Section>}
    </>
  );
}

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

function Picker({ run, name }: { run: number; name: 'catboost' | 'catboost_piecewise' }) {
  const picker = PICKERS[name];
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
      <p className="text-dim text-sm">{picker.score}. Saved predictions, model settings and importance remain as recorded for this run.</p>
      {view === "model" && <Meta title={`${picker.title} model`} table="pick_model" run={run} />}
      {view === "importance" && <Meta
        title={`${picker.title} feature importance`}
        table="pick_importance"
        run={run}
        initial={{ sort: "importance", desc: true }}
      />}
      {view === "decisions" && pause === null && <Section title="Decision snapshots">
        <p className="text-dim mb-3 text-xs">Inspect a decision snapshot to compare the blocks scored by {picker.title}, ranked best first.</p>
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
        <div className="space-y-5">
        <Section title="Current reward from this pause">
          <p className="text-dim mb-3 text-xs">Recalculated from the pause’s first snapshot through the run’s end. Earlier models may have used a different reward; their saved predictions are preserved below.</p>
          <Reward run={run} seq={Number(pause)} />
        </Section>
        <Section title="Ranked action blocks">
        <p className="text-dim mb-3 text-xs">{name === 'catboost_piecewise' ? 'The current picker averages action predictions, including repeated actions and event answers. Historical runs before the averaging change recorded sums. Individual action scores were not recorded.' : 'Each score is a prediction for the whole block. Decisions occur quarterly, with at most sixteen actions.'} Higher scores rank first; tied scores share a rank. Chosen marks the selected block. Arrows show action order, including repeats. Saved alternatives contain action names only, without target parameters.</p>
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
        </div>
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
      <Tabs views={VIEWS} labels={{ config: "Overview", initializer: "Action weights", picker: "Block selection", outcomes: "Rewards & outcomes" }} />
      <Loading state={record}>
        {(g) => (
          <div className="space-y-4">
            {view === "config" && <Section title="How this run chooses actions">
              <div className="space-y-4 text-sm">
                <div><Link className="linka font-semibold" to={`?view=initializer`}>1. Initialize action weights</Link><p className="text-dim">{text(g, "initializer")} sets the weights used to sample actions into candidate blocks.</p></div>
                <div><Link className="linka font-semibold" to={`?view=picker`}>2. Select an action block</Link><p className="text-dim">{text(g, "picker")} chooses which generated block to execute at each decision.</p></div>
                <div><Link className="linka font-semibold" to={`?view=outcomes`}>3. Score the outcome</Link><p className="text-dim">The current reward combines building stock, population and GDP. Initializers start at the run opening; pickers start at the pause’s first snapshot.</p></div>
              </div>
            </Section>}
            {view === "outcomes" && <>
              <Section title="Three-metric reward"><RewardFormula /></Section>
              <Section title="Current reward from the run opening"><Reward run={run} /></Section>
              <details className="text-dim text-xs"><summary className="cursor-pointer">Legacy recorded objective</summary><p className="my-2">These historical four-component weights are retained in the run record. They do not control the current learned-model reward.</p><Record grid={only(g, "legacy")} /></details>
            </>}
            {view === "initializer" && <>
              <Section title="Weight initializer"><Record grid={only(g, "initializer")} /></Section>
              <Initializer run={run} name={text(g, "initializer")} />
            </>}
            {view === "picker" && (
              <>
                <Section title="Block picker"><Record grid={only(g, "picker")} /></Section>
                <Pickers only={text(g, "picker")} />
                {text(g, "picker") === "first" && <Section title="Executed blocks">
                  <p className="text-dim mb-3 text-sm">Each decision executes the first sampled block. There are no model predictions or ranked alternatives. Open a snapshot to inspect the recorded actions.</p>
                  <DataGrid id="first_picker_blocks" url={`/api/runs/${run}/blocks`} live />
                </Section>}
                {text(g, "picker") === "catboost" && <Picker run={run} name="catboost" />}
                {text(g, "picker") === "catboost_piecewise" && <Picker run={run} name="catboost_piecewise" />}
              </>
            )}
          </div>
        )}
      </Loading>
    </div>
  );
}
