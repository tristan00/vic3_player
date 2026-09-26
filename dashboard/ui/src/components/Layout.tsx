import { BarChart3, Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { StateChip } from '@/components/primitives'
import { useApi, useConnected, type S } from '@/lib/api'
import { cn } from '@/lib/format'

const NAV = [
  { to: '/', label: 'Live', end: true },
  { to: '/runs', label: 'Runs', end: false },
  { to: '/actions', label: 'Actions', end: false },
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
  const [theme, setTheme] = useState(readTheme)
  const connected = useConnected()
  const open = useApi<S['RunsPage']>('/api/runs?end_reason=open&limit=5', { live: true })
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
        <div className="mx-auto flex min-h-14 max-w-[1800px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2 sm:px-7">
          <Link to="/" className="text-accent flex items-center gap-2 font-semibold" aria-label="Live">
            <BarChart3 size={18} />
            <span className="text-fg">vic3 runs</span>
          </Link>
          <nav className="flex items-center gap-5" aria-label="Main">
            {NAV.map((i) => (
              <NavLink key={i.to} to={i.to} end={i.end} className={({ isActive }) => cn('py-1 text-sm', isActive ? 'text-fg border-fg border-b-2 font-semibold' : 'text-dim hover:text-fg')}>
                {i.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-2xs">
            {open.data?.rows.map((r) => (
              <Link key={r.run_id} to={`/runs/${r.run_id}`} className="hover:bg-raised flex items-center gap-1.5 rounded px-1.5 py-0.5">
                <StateChip state={r.state} />
                <span className="num">run {r.run_id}</span>
                <span className="text-dim">{r.tag}</span>
              </Link>
            ))}
            {open.data && !open.data.rows.length && <span className="text-dim">no run open</span>}
            <span title={connected ? 'receiving live updates' : 'live updates disconnected; retrying'} className="flex items-center gap-1">
              <span className="inline-block size-1.5 rounded-full" style={{ background: connected ? 'var(--done)' : 'var(--invalid)' }} />
              <span className="text-dim">{connected ? 'live' : 'offline'}</span>
            </span>
            <button className="text-dim hover:text-fg p-1" aria-label="Switch theme" onClick={() => setTheme(dark ? 'light' : 'dark')}>
              {dark ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1800px] px-4 pt-6 pb-16 sm:px-7">
        <Outlet />
      </main>
    </div>
  )
}
