import { Component, useEffect, useRef, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { Act, Actions, Levers } from './Actions'
import { useApi, useReachable } from './api'
import { phaseTone, time } from './format'
import { Pill } from './Grid'
import { Overview } from './Overview'
import { Run, Runs } from './Runs'
import { Scores } from './Scores'
import { Entity, Table, Tables } from './Tables'
import { Search, Tuning } from './Tuning'
import { World, Worlds } from './Worlds'
import './styles.css'

const SECTIONS: [string, string][] = [
  ['Overview', '/'],
  ['Runs', '/runs'],
  ['Actions', '/actions'],
  ['Levers', '/levers'],
  ['Scores', '/scores'],
  ['Worlds', '/worlds'],
  ['Tuning', '/tuning'],
  ['Tables', '/tables'],
]

class Boundary extends Component<{ at: string; children: ReactNode }, { at: string; failed: boolean; message: string }> {
  state = { at: this.props.at, failed: false, message: '' }

  static getDerivedStateFromError(error: unknown) {
    return { failed: true, message: error instanceof Error ? error.message : String(error) }
  }

  static getDerivedStateFromProps(props: { at: string }, state: { at: string }) {
    return props.at === state.at ? null : { at: props.at, failed: false, message: '' }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="page">
        <h1>Page error</h1>
        <div className="problem">{this.state.message}</div>
      </div>
    )
  }
}

function Status({ collection, up }: { collection: { data?: any; error?: string }; up: boolean }) {
  const found = collection.data
  if (!up)
    return (
      <div className="status">
        <Pill value="server down" tone="bad" />
      </div>
    )
  return (
    <div className="status">
      {collection.error && <Pill value={`state: ${collection.error}`} tone="bad" />}
      {found && Date.now() / 1000 - found.read > 20 && <Pill value={`state read ${time(found.read)}`} tone="bad" />}
      {found && <Pill value={found.phase} tone={phaseTone(found.phase)} />}
      {found?.run_id && <Link to={`/runs/${found.run_id}`}>run {found.run_id}</Link>}
      {found?.run_id && found.date && <span>{found.date}</span>}
      {found?.settings && (
        <span>
          {found.completed} of {found.settings.runs}
        </span>
      )}
    </div>
  )
}

function Shell() {
  const collection = useApi('/api/collection', 2000)
  const up = useReachable()
  const location = useLocation()
  const first = useRef<number | null>(null)
  const started: number | undefined = collection.data?.server_started
  useEffect(() => {
    if (started === undefined) return
    if (first.current === null) first.current = started
    else if (first.current !== started) window.location.reload()
  }, [started])
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [location.pathname])
  return (
    <>
      <header>
        <Link to="/" className="mark">
          vic3
        </Link>
        <nav>
          {SECTIONS.map(([name, to]) => (
            <NavLink key={to} to={to} end={to === '/'}>
              {name}
            </NavLink>
          ))}
        </nav>
        <Status collection={collection} up={up} />
      </header>
      <main>
        <Boundary at={location.pathname + location.search}>
          <Outlet key={location.pathname} context={collection.data} />
        </Boundary>
      </main>
    </>
  )
}

function Missing() {
  const location = useLocation()
  return (
    <div className="page">
      <h1>No page here</h1>
      <div className="problem">no page {location.pathname}</div>
      <div className="lead">
        {SECTIONS.map(([name, to]) => (
          <Link key={to} to={to}>
            {name}
          </Link>
        ))}
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Overview />} />
        <Route path="runs" element={<Runs />} />
        <Route path="runs/:run" element={<Run />} />
        <Route path="runs/:run/tables/:table" element={<Table />} />
        <Route path="runs/:run/e/:kind/:id" element={<Entity />} />
        <Route path="tables" element={<Tables />} />
        <Route path="tables/:table" element={<Table />} />
        <Route path="actions" element={<Actions />} />
        <Route path="actions/:name" element={<Act />} />
        <Route path="levers" element={<Levers />} />
        <Route path="scores" element={<Scores />} />
        <Route path="worlds" element={<Worlds />} />
        <Route path="worlds/:world" element={<World />} />
        <Route path="tuning" element={<Tuning />} />
        <Route path="tuning/:search/:model" element={<Search />} />
        <Route path="*" element={<Missing />} />
      </Route>
    </Routes>
  </BrowserRouter>,
)
