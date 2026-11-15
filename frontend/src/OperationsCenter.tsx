import type { OperationsOverview } from './api'

type Props = {
  overview: OperationsOverview | null
  canEdit: boolean
  busy: boolean
  onRefresh: () => void
  onRollback: (flag: OperationsOverview['flags'][number]) => void
  onTargeting: (flag: OperationsOverview['flags'][number]) => void
  onGuardrail: (flag: OperationsOverview['flags'][number]) => void
}

export default function OperationsCenter({ overview, canEdit, busy, onRefresh, onRollback, onTargeting, onGuardrail }: Props) {
  if (!overview) return <div className="empty">Operational status is not available. Try refreshing.</div>
  const { pipeline, flags } = overview
  const stale = pipeline.oldest_pending_seconds !== null && pipeline.oldest_pending_seconds > 60
  return <section className="ops-center" aria-label="Release operations center">
    <div className="panel ops-overview">
      <div className="panel-head">
        <div><h3>Release operations center</h3><p>Inspect release controls and the persisted event pipeline.</p></div>
        <button className="btn btn-outline" onClick={onRefresh} disabled={busy}>Refresh status</button>
      </div>
      <div className="ops-metrics" aria-label="Global event pipeline statistics">
        <div><span>Pending outbox</span><strong>{pipeline.pending}</strong></div>
        <div><span>Published events</span><strong>{pipeline.published}</strong></div>
        <div><span>Consumer receipts</span><strong>{pipeline.ingested}</strong></div>
        <div><span>Dead letters awaiting review</span><strong>{overview.dead_letters}</strong></div>
      </div>
      <p className="ops-note">{stale ? 'Warning: a queued event has exceeded the age alert threshold. ' : ''}
        Queue age status: {pipeline.oldest_pending_seconds === null ? "no pending events" : stale ? "delayed" : "within alert threshold"}. Event totals are global across environments. Transport: {pipeline.transport}.
        Broker and worker health are not probed by this endpoint. Eventual delivery is not guaranteed solely by these counts.
      </p>
    </div>
    <div className="panel ops-flags">
      <div className="panel-head">
        <div><h3>{overview.environment} releases</h3><p>Rollback disables a feature and sets rollout to 0%, without redeploying.</p></div>
      </div>
      {flags.length === 0 && <div className="empty">No flags in this environment.</div>}
      {flags.map(flag => <div className="ops-row" key={flag.id}>
        <div className="ops-flag"><strong>{flag.name}</strong><code>{flag.key}</code><span>Version {flag.version} · Rollout {flag.rollout}%</span><span>Country: {flag.targeting?.countries?.join(', ') || 'any'} · Plan: {flag.targeting?.plans?.join(', ') || 'any'} · SLO guard: {flag.guardrail_enabled ? 'enabled' : 'off'}</span></div>
        <span className={flag.enabled ? 'pill pill-live' : 'pill pill-muted'}>{flag.enabled ? 'Active' : 'Paused'}</span>
        {canEdit && <button className="btn btn-outline" disabled={busy} onClick={() => onTargeting(flag)}>Targeting</button>}
        {canEdit && <button className="btn btn-outline" disabled={busy} onClick={() => onGuardrail(flag)}>{flag.guardrail_enabled ? 'Disable SLO' : 'Enable SLO'}</button>}
        {canEdit && <button className="btn btn-outline" disabled={busy || (!flag.enabled && flag.rollout === 0)}
          onClick={() => onRollback(flag)} aria-label={`Rollback ${flag.key}`}>Rollback</button>}
      </div>)}
      {canEdit && <p className="ops-note">SLO policies start disabled. Enable only after configuring trusted health reporting and checking thresholds. Dead letters are read-only here; replay requires administrator API validation and correction in /docs.</p>}
      {!canEdit && <p className="ops-note">Viewer access: changes and emergency rollbacks require the administrator role.</p>}
    </div>
  </section>
}
