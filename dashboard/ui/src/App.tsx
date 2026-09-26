import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { Action } from '@/routes/Action'
import { Block } from '@/routes/Block'
import { Actions } from '@/routes/Actions'
import { ActionType } from '@/routes/ActionType'
import { Entities } from '@/routes/Entities'
import { Entity } from '@/routes/Entity'
import { Live } from '@/routes/Live'
import { Run } from '@/routes/Run'
import { Runs } from '@/routes/Runs'
import { Schema } from '@/routes/Schema'
import { Snapshot } from '@/routes/Snapshot'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Live />} />
        <Route path="/runs" element={<Runs />} />
        <Route path="/runs/:run" element={<Run />} />
        <Route path="/runs/:run/actions/:n" element={<Action />} />
        <Route path="/runs/:run/snapshots/:seq" element={<Snapshot />} />
        <Route path="/runs/:run/blocks/:seq" element={<Block />} />
        <Route path="/runs/:run/entities/:kind" element={<Entities />} />
        <Route path="/runs/:run/entities/:kind/:id" element={<Entity />} />
        <Route path="/actions" element={<Actions />} />
        <Route path="/actions/:name" element={<ActionType />} />
        <Route path="/schema" element={<Schema />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
