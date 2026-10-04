import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { Action } from '@/routes/Action'
import { Actions } from '@/routes/Actions'
import { ActionType } from '@/routes/ActionType'
import { Entities } from '@/routes/Entities'
import { Entity } from '@/routes/Entity'
import { Policy } from '@/routes/Policy'
import { PolicyRun } from '@/routes/PolicyRun'
import { Run } from '@/routes/Run'
import { Runs } from '@/routes/Runs'
import { Schema } from '@/routes/Schema'
import { Snapshot } from '@/routes/Snapshot'
import { Table } from '@/routes/Table'
import { Worlds, WorldDetail } from '@/routes/Worlds'
import { Tuning } from '@/routes/Tuning'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Runs />} />
        <Route path="/worlds" element={<Worlds />} />
        <Route path="/worlds/:world" element={<WorldDetail />} />
        <Route path="/runs/:run" element={<Run />} />
        <Route path="/runs/:run/actions/:n" element={<Action />} />
        <Route path="/runs/:run/snapshots/:seq" element={<Snapshot />} />
        <Route path="/runs/:run/tables/:table" element={<Table />} />
        <Route path="/runs/:run/entities/:kind" element={<Entities />} />
        <Route path="/runs/:run/entities/:kind/:id" element={<Entity />} />
        <Route path="/actions" element={<Actions />} />
        <Route path="/actions/:name" element={<ActionType />} />
        <Route path="/policy" element={<Policy />} />
        <Route path="/tuning" element={<Tuning />} />
        <Route path="/policy/runs/:run" element={<PolicyRun />} />
        <Route path="/schema" element={<Schema />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
