let accessToken: string | null = null
export function setAccessToken(token: string | null) { accessToken = token }
export type Environment = 'production' | 'staging' | 'development'
export type Flag = { id: string; key: string; name: string; description: string; environment: Environment; owner: string; enabled: boolean; rollout: number; version: number; created_at: string; updated_at: string }
export type Daily = { date: string; evaluations: number; conversions: number }
export type Metrics = { total_flags: number; active_flags: number; evaluations: number; unique_users: number; conversions: number; conversion_rate: number; daily: Daily[]; flags: { id: string; key: string; evaluations: number; conversions: number }[] }
export type Audit = { id: string; flag_key: string; actor: string; action: string; before: Record<string, unknown>; after: Record<string, unknown>; created_at: string }
export type Experiment = {flag_key: string; environment: string; method: string; control: {users: number; conversions: number; rate: number; ci95: number[]}; treatment: {users: number; conversions: number; rate: number; ci95: number[]}; p_value: number | null; absolute_lift: number | null; relative_lift: number | null; warnings: string[]}
export type Evaluation = { key: string; enabled: boolean; reason: string; bucket: number; rollout: number; flag_version: number; environment: string }

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}), ...options?.headers } })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}
export const api = {
  me: () => request<{subject: string; roles: string[]}>('/me'),
  experiment: (key: string, environment: Environment) => request<Experiment>(`/experiments/${encodeURIComponent(key)}?environment=${environment}`),
  pipeline: () => request<{transport: string; pending: number; published: number; ingested: number}>('/events/pipeline'),
  flags: (environment: Environment) => request<Flag[]>(`/flags?environment=${environment}`),
  metrics: (environment: Environment) => request<Metrics>(`/analytics?environment=${environment}`),
  audit: () => request<Audit[]>('/audit'),
  update: (id: string, data: Partial<Flag> & { version: number }) => request<Flag>(`/flags/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  create: (data: Record<string, unknown>) => request<Flag>('/flags', { method: 'POST', body: JSON.stringify(data) }),
  evaluate: (key: string, environment: Environment, user_id: string) => request<Evaluation>('/evaluate', { method: 'POST', body: JSON.stringify({ key, environment, user_id }) }),
  convert: (key: string, environment: Environment, user_id: string) => request<{ recorded: boolean; reason?: string }>('/events/conversion', { method: 'POST', body: JSON.stringify({ key, environment, user_id }) }),
  simulate: (environment: Environment) => request<{ generated: number; conversions: number; synthetic: boolean }>(`/demo/simulate?environment=${environment}&count=150`, { method: 'POST' }),
}
