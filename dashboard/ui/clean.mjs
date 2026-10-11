import { existsSync, readdirSync, unlinkSync } from 'node:fs'

if (existsSync('dist/assets')) for (const name of readdirSync('dist/assets')) unlinkSync(`dist/assets/${name}`)
