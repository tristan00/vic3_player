import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

export function Neighbors({ previous, next, to, children }: { previous: number | null; next: number | null; to: (n: number) => string; children: ReactNode }) {
  return (
    <>
      {previous !== null && (
        <Link className="linka num text-xs" to={to(previous)}>
          {previous}
        </Link>
      )}
      {children}
      {next !== null && (
        <Link className="linka num text-xs" to={to(next)}>
          {next}
        </Link>
      )}
    </>
  )
}
