import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useParams } from 'react-router-dom'
import { useApi, useConnected, type S } from '@/lib/api'
import { cn } from '@/lib/format'

const NAV = [
  { to: '/worlds', label: 'Worlds', end: false },
  { to: '/', label: 'Runs', end: true },
  { to: '/actions', label: 'Actions', end: false },
  { to: '/policy', label: 'Policy', end: false },
  { to: '/tuning', label: 'Tuning', end: false },
  { to: '/schema', label: 'Schema', end: false },
]

function readTheme(): string {
  try {
    return localStorage.getItem('theme') ?? ''
  } catch {
    return ''
  }
}

export function Layout() {
  const { run } = useParams()
  const location = useLocation()
  useEffect(() => {
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView()
    else window.scrollTo(0, 0)
  }, [location.pathname, location.hash])
  const [theme, setTheme] = useState(readTheme)
  const connected = useConnected()
  const open = useApi<S['OpenRun'][]>('/api/open', { live: true })
  useEffect(() => {
    if (theme) document.documentElement.setAttribute('data-theme', theme)
    else document.documentElement.removeAttribute('data-theme')
    try {
      localStorage.setItem('theme', theme)
    } catch {
      return
    }
  }, [theme])
  const dark = theme ? theme === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
  return (
    <div className="min-h-full">
      <header className="bg-surface border-line border-b">
        <div className="flex min-h-11 flex-wrap items-center gap-x-5 gap-y-1 px-4 py-1.5">
          <span className="text-sm font-semibold">vic3</span>
          <nav className="flex items-center gap-4" aria-label="Main">
            {NAV.map((i) => (
              <NavLink key={i.to} to={i.to} end={i.end} className={({ isActive }) => cn('text-sm', isActive ? 'text-fg font-semibold' : 'text-dim hover:text-fg')}>
                {i.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-2xs">
            {open.data?.map((r) => (
              <Link key={r.run} to={`/runs/${r.run}`} className="hover:bg-raised num rounded px-1.5 py-0.5">
                run {r.run} · {r.country} · {r.state}
              </Link>
            ))}
            <span className="inline-block size-1.5 rounded-full" style={{ background: connected ? 'var(--done)' : 'var(--invalid)' }} aria-label={connected ? 'live' : 'offline'} />
            <button className="text-dim hover:text-fg p-1" aria-label="Switch theme" onClick={() => setTheme(dark ? 'light' : 'dark')}>
              {dark ? <Sun size={14} /> : <Moon size={14} />}
            </button>
          </div>
        </div>
      </header>
      <main className="px-4 pt-4 pb-16">
        {run && location.pathname !== `/runs/${run}` && <nav aria-label="Run navigation" className="border-line mb-5 flex flex-wrap items-center gap-x-5 gap-y-2 border-b pb-3 text-xs"><Link className="linka font-semibold" to={`/runs/${run}`}>Run {run}</Link>{['actions', 'snapshots', 'entities', 'tables'].map((v) => <Link key={v} className="linka capitalize" to={`/runs/${run}?view=${v}`}>{v}</Link>)}<Link className="linka" to={`/policy/runs/${run}`}>Policy</Link></nav>}
        <Outlet key={location.pathname} />
      </main>
    </div>
  )
}
