/** Demo-only credentials come from generated, ignored .env or CI job environment. */
import { existsSync } from 'node:fs'
import { loadEnvFile } from 'node:process'

const localEnv = new URL('../.env', import.meta.url)
if (existsSync(localEnv)) loadEnvFile(localEnv)

export function demoPassword(role: 'admin' | 'viewer'): string {
  const key = role === 'admin' ? 'DEMO_ADMIN_PASSWORD' : 'DEMO_VIEWER_PASSWORD'
  const value = process.env[key]
  if (!value) {
    throw new Error(`Missing ${key}. From the repository root, run: python3 scripts/setup_local_credentials.py`)
  }
  return value
}
