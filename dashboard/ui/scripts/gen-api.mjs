import { execFileSync } from 'node:child_process'
import path from 'node:path'

const ui = path.resolve(import.meta.dirname, '..')
const root = path.resolve(ui, '../..')
const spec = path.join(ui, 'openapi.json')
execFileSync(path.join(root, '.venv', 'Scripts', 'python.exe'), ['-m', 'dashboard.server', '--openapi', spec], { cwd: root, stdio: 'inherit' })
execFileSync(process.execPath, [path.join(ui, 'node_modules', 'openapi-typescript', 'bin', 'cli.js'), spec, '-o', path.join(ui, 'src', 'api', 'schema.d.ts')], { stdio: 'inherit' })
