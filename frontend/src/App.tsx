import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Activity, ArrowDownRight, ArrowRight, ArrowUpRight, Check, CheckCheck, ChevronDown, CircleHelp, Code2, Cpu, ExternalLink, FileClock, Flag as FlagIcon, FlaskConical, Gauge, GitBranch, Layers3, LockKeyhole, Menu, MoreHorizontal, Plus, Radio, RefreshCw, Rocket, Search, Settings2, ShieldCheck, Sparkles, TrendingUp, Users, X, Zap } from 'lucide-react'
import { api, type Audit, type Environment, type Evaluation, type Experiment, type Flag, type Metrics } from './api'

type Page = 'overview' | 'flags' | 'playground' | 'audit' | 'experiments'
const nav: { page: Page; title: string; icon: typeof Activity }[] = [
  { page: 'overview', title: 'Overview', icon: Gauge },
  { page: 'flags', title: 'Feature flags', icon: FlagIcon },
  { page: 'playground', title: 'Evaluation lab', icon: FlaskConical },
  { page: 'audit', title: 'Audit trail', icon: FileClock },
  { page: 'experiments', title: 'Experiments', icon: TrendingUp },
]
const labelDate = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-US', { weekday: 'short' })
const timeAgo = (iso: string) => {
  const ms = Date.now() - new Date(iso).getTime()
  if (ms < 60000) return 'Just now'
  if (ms < 3600000) return `${Math.floor(ms / 60000)}m ago`
  if (ms < 86400000) return `${Math.floor(ms / 3600000)}h ago`
  return `${Math.floor(ms / 86400000)}d ago`
}
const number = (n: number) => new Intl.NumberFormat('en-US').format(n)
const colors = ['#8b7bff', '#00d6b6', '#f9b564', '#8db4ff', '#e38fff', '#ffd17c']

function Mark({ size = 36 }: { size?: number }) {
  return <div className="mark" style={{ width: size, height: size }}><Rocket size={size * .53} strokeWidth={2.4} /></div>
}
function TinyLine({ points }: { points: number[] }) {
  const max = Math.max(1, ...points)
  const coords = points.map((n, i) => `${i * (110 / Math.max(1, points.length - 1))},${35 - n / max * 27}`).join(' ')
  return <svg viewBox="0 0 110 42" className="spark" aria-hidden="true"><polyline points={coords} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
}
function Stat({ label, value, detail, icon: Icon, accent, points }: { label: string; value: string; detail: string; icon: typeof Activity; accent: string; points: number[] }) {
  return <div className="stat-card">
    <div className="stat-top"><span>{label}</span><span className="stat-icon" style={{ color: accent }}><Icon size={18} /></span></div>
    <div className="stat-main"><strong>{value}</strong><TinyLine points={points} /></div>
    <span className="stat-detail"><span className="dot" style={{ backgroundColor: accent }} />{detail}</span>
  </div>
}
function Toggle({ checked, disabled, onChange, label }: { checked: boolean; disabled?: boolean; onChange: () => void; label: string }) {
  return <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} className={`toggle ${checked ? 'checked' : ''}`} onClick={onChange}><span /></button>
}
function FlagRow({ flag, idx, onSave, busy }: { flag: Flag; idx: number; onSave: (flag: Flag, patch: Partial<Flag>) => Promise<void>; busy: boolean }) {
  const [rollout, setRollout] = useState(flag.rollout)
  useEffect(() => setRollout(flag.rollout), [flag.rollout])
  const edited = rollout !== flag.rollout
  return <div className="flag-row">
    <div className="flag-icon" style={{ backgroundColor: `${colors[idx % colors.length]}20`, color: colors[idx % colors.length] }}><Layers3 size={18} /></div>
    <div className="flag-desc"><div className="flag-title">{flag.name} <span className={`pill ${flag.enabled ? 'pill-live' : 'pill-muted'}`}>{flag.enabled ? 'Active' : 'Paused'}</span></div><div className="flag-key">{flag.key}</div><p>{flag.description}</p><div className="flag-meta"><Users size={12} /> {flag.owner}<span>·</span><span>v{flag.version}</span></div></div>
    <div className="flag-controls"><div className="flag-control-top"><span>Rollout</span><b>{rollout}%</b></div><input type="range" aria-label={`Rollout percentage for ${flag.name}`} min="0" max="100" step="5" value={rollout} onChange={e => setRollout(Number(e.target.value))} disabled={busy} style={{ background: `linear-gradient(90deg,#806dff 0%,#806dff ${rollout}%,#292b43 ${rollout}%,#292b43 100%)` }} /><div className="flag-control-bottom">{edited ? <button type="button" onClick={() => void onSave(flag, { rollout })} disabled={busy} className="save-inline"><Check size={12}/> Save changes</button> : <span>Consistent hashing</span>}<Toggle checked={flag.enabled} disabled={busy} onChange={() => void onSave(flag, { enabled: !flag.enabled })} label={`Toggle ${flag.name}`} /></div></div>
  </div>
}
function NewFlagModal({ onClose, onCreate, environment }: { onClose: () => void; onCreate: (data: Record<string, unknown>) => Promise<void>; environment: Environment }) {
  const [name, setName] = useState('')
  const [key, setKey] = useState('')
  const [description, setDescription] = useState('')
  const [owner, setOwner] = useState('Platform team')
  const [loading, setLoading] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setLoading(true)
    try { await onCreate({ key, name, description, environment, owner, enabled: false, rollout: 0 }); onClose() }
    catch { /* Parent already surfaced the API error in a toast. */ }
    finally { setLoading(false) }
  }
  return <div className="modal-layer" onClick={onClose}><div className="modal" role="dialog" aria-modal="true" aria-label="Create feature flag" onClick={e => e.stopPropagation()}><div className="modal-head"><div><span className="eyebrow">PROGRESSIVE DELIVERY</span><h2>Create a feature flag</h2></div><button className="icon-button" onClick={onClose} aria-label="Close"><X size={18}/></button></div><p>Ship behind a safety switch. New flags start paused with 0% rollout.</p><form onSubmit={e => void submit(e)}><label>Display name<input required minLength={3} maxLength={120} placeholder="e.g. Instant notifications" value={name} onChange={e => { setName(e.target.value); setKey(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')) }} /></label><label>Flag key<input required minLength={3} maxLength={72} pattern="[a-z][a-z0-9_]{2,71}" placeholder="instant_notifications" value={key} onChange={e => setKey(e.target.value)} /></label><label>Owner<input required minLength={2} maxLength={80} value={owner} onChange={e => setOwner(e.target.value)} /></label><label>Description<textarea maxLength={500} placeholder="What change does this gate?" rows={3} value={description} onChange={e => setDescription(e.target.value)} /></label><div className="modal-bottom"><span><LockKeyhole size={14} /> {environment} · Starts disabled</span><button className="btn btn-primary" disabled={loading}><Plus size={16}/>{loading ? 'Creating...' : 'Create flag'}</button></div></form></div></div>
}
function App({ canEdit = true, authMode = 'demo', onLogout }: { canEdit?: boolean; authMode?: 'demo' | 'oidc'; onLogout?: () => void }) {
  const [page, setPage] = useState<Page>('overview')
  const [environment, setEnvironment] = useState<Environment>('production')
  const [flags, setFlags] = useState<Flag[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [audits, setAudits] = useState<Audit[]>([])
  const [loading, setLoading] = useState(true)
  const [online, setOnline] = useState(false)
  const [busy, setBusy] = useState(false)
  const [showNew, setShowNew] = useState(false)
  const [search, setSearch] = useState('')
  const [notice, setNotice] = useState<{ text: string; error?: boolean } | null>(null)
  const [selected, setSelected] = useState('')
  const [userId, setUserId] = useState('user_alex_42')
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [experiment, setExperiment] = useState<Experiment | null>(null)
  const [experimentLoading, setExperimentLoading] = useState(false)

  const notify = useCallback((text: string, error = false) => setNotice({ text, error }), [])
  const refresh = useCallback(async () => {
    try {
      const [f, m, a] = await Promise.all([api.flags(environment), api.metrics(environment), api.audit()])
      setFlags(f); setMetrics(m); setAudits(a); setOnline(true)
      setSelected(prev => f.some(x => x.key === prev) ? prev : (f[0]?.key ?? ''))
    } catch (err) { setOnline(false); notify(err instanceof Error ? err.message : 'Unable to reach the API', true) }
    finally { setLoading(false) }
  }, [environment, notify])
  useEffect(() => { setLoading(true); void refresh() }, [refresh])
  useEffect(() => { setEvaluation(null); setExperiment(null) }, [environment, selected])
  const loadExperiment = async () => {
    if (!selected) return
    setExperimentLoading(true)
    try { setExperiment(await api.experiment(selected, environment)) }
    catch (e) { notify(e instanceof Error ? e.message : 'Experiment calculation failed', true) }
    finally { setExperimentLoading(false) }
  }

  const onSave = async (flag: Flag, patch: Partial<Flag>) => {
    if (!canEdit) { notify("Viewer role cannot modify flags", true); return }
    setBusy(true)
    try { await api.update(flag.id, { version: flag.version, ...patch }); await refresh(); notify(`${flag.name} updated`) }
    catch (err) { notify(err instanceof Error ? err.message : 'Unable to save flag', true); await refresh() }
    finally { setBusy(false) }
  }
  const onCreate = async (data: Record<string, unknown>) => {
    if (!canEdit) throw new Error("Viewer role cannot create flags")
    try { await api.create(data); await refresh(); notify('Feature flag created') }
    catch (err) { notify(err instanceof Error ? err.message : 'Unable to create flag', true); throw err }
  }
  const simulate = async () => {
    if (!canEdit) { notify("Viewer role cannot simulate traffic", true); return }
    setBusy(true)
    try { const r = await api.simulate(environment); await refresh(); notify(`Generated ${number(r.generated)} synthetic evaluations and ${r.conversions} conversions`) }
    catch (err) { notify(err instanceof Error ? err.message : 'Unable to simulate traffic', true) }
    finally { setBusy(false) }
  }
  const doEvaluate = async () => {
    setBusy(true)
    try { const result = await api.evaluate(selected, environment, userId); setEvaluation(result); await refresh() }
    catch (err) { notify(err instanceof Error ? err.message : 'Evaluation failed', true) }
    finally { setBusy(false) }
  }
  const doConvert = async () => {
    setBusy(true)
    try { const result = await api.convert(selected, environment, userId); await refresh(); notify(result.recorded ? 'Conversion recorded' : 'Conversion already recorded for this user') }
    catch (err) { notify(err instanceof Error ? err.message : 'Conversion failed', true) }
    finally { setBusy(false) }
  }
  const displayed = useMemo(() => flags.filter(f => `${f.name} ${f.key} ${f.owner}`.toLowerCase().includes(search.toLowerCase())), [flags, search])
  const maxExposure = Math.max(1, ...(metrics?.daily.map(x => x.evaluations) ?? [1]))
  const chartPoints = metrics?.daily.map(x => x.evaluations) ?? [0, 0, 0, 0, 0, 0, 0]
  const activePage = nav.find(x => x.page === page)?.title ?? 'Overview'
  const flagIndex = flags.findIndex(f => f.key === selected)
  const selectedFlag = flags[flagIndex]
  return <div className="app-shell">
    <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
      <button className="brand" onClick={() => { setPage('overview'); setMenuOpen(false) }}><Mark/><span>launch<span className="brand-accent">pilot</span><small>CONTROL PLANE</small></span></button>
      <div className="workspace-picker"><div className="workspace-avatar">N</div><div><strong>Nova workspace</strong><span>Developer sandbox</span></div><ChevronDown size={14}/></div>
      <span className="sidebar-label">WORKSPACE</span>
      <nav aria-label="Main navigation">{nav.map(n => <button key={n.page} className={`nav-item ${page === n.page ? 'nav-active' : ''}`} onClick={() => { setPage(n.page); setMenuOpen(false) }}><n.icon size={17}/><span>{n.title}</span>{n.page === 'flags' && <em>{flags.length}</em>}</button>)}</nav>
      <span className="sidebar-label sidebar-secondary">DEVELOPER TOOLS</span>
      <a className="nav-item nav-link" href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer"><Code2 size={17}/><span>API reference</span><ExternalLink size={13}/></a>
      <a className="nav-item nav-link" href="https://github.com/new" target="_blank" rel="noreferrer"><GitBranch size={17}/><span>Create on GitHub</span><ExternalLink size={13}/></a>
      <div className="sidebar-spacer"/>
      <div className="sidebar-guide"><div className="guide-icon"><Sparkles size={19}/></div><strong>Build with confidence</strong><p>Safer releases. Measurable impact. One control plane.</p><button onClick={() => setPage('playground')}>Try evaluation lab <ArrowRight size={14}/></button></div>
      <div className="sidebar-foot"><span className="online-dot"/> {authMode === "oidc" ? (canEdit ? "OIDC · Admin" : "OIDC · Viewer") : "Local demo mode"} <span className="app-version">v2.0.0</span></div>
    </aside>

    <div className="main-area">
      <header className="topbar"><div className="crumb"><button className="mobile-menu" aria-label="Open navigation" onClick={() => setMenuOpen(!menuOpen)}><Menu size={20}/></button><span>Workspace</span><span className="slash">/</span><strong>{activePage}</strong></div><div className="top-actions"><div className="live-status"><span className="online-dot" style={!online ? {background: '#f19e76', boxShadow: 'none'} : undefined}/>{online ? ' API connected' : ' API unavailable'}</div><div className="top-divider"/>{onLogout && <button className="btn btn-outline" type="button" onClick={onLogout}>Sign out</button>}<div className="avatar">{canEdit ? "AD" : "VI"}</div></div></header>
      <main>
        <div className="page-head"><div><div className="eyebrow"><span className="eyebrow-line"/> RELEASE INTELLIGENCE PLATFORM</div><h1>{page === 'overview' ? 'Good morning, developer' : activePage}<span className="heading-dot">.</span></h1><p>{page === 'overview' ? 'Ship faster, measure everything, and keep every release under control.' : page === 'flags' ? 'Manage releases with consistent targeting and real-time rollout control.' : page === 'playground' ? 'Explore the deterministic evaluation engine with real user identifiers.' : page === 'experiments' ? 'Statistical comparisons of exposed control and treatment cohorts.' : 'Every flag change has an accountable, append-only history.'}</p></div><div className="head-buttons"><label className="env-wrap"><Radio size={14}/><select aria-label="Environment" value={environment} onChange={e => setEnvironment(e.target.value as Environment)}><option value="production">Production</option><option value="staging">Staging</option><option value="development">Development</option></select><ChevronDown size={14}/></label><button className="btn btn-outline btn-icon" aria-label="Refresh data" disabled={busy} onClick={() => void refresh()}><RefreshCw size={16}/></button>{canEdit && page !== 'audit' && page !== 'experiments' && <button className="btn btn-primary" onClick={() => setShowNew(true)}><Plus size={17}/> New flag</button>}</div></div>

        {loading && <div className="loading"><RefreshCw size={22} className="spin"/> Connecting to LaunchPilot API...</div>}
        {!loading && page === 'overview' && <>
          <div className="hero"><div className="hero-copy"><span className="hero-label"><Sparkles size={13}/> PROGRESSIVE DELIVERY, SIMPLIFIED</span><h2>Control every release.<br/><span>Move with confidence.</span></h2><p>Gradually ship features, validate real user experience, and roll back instantly. Your releases, on your terms.</p><div className="hero-actions"><button className="btn btn-white" onClick={() => setPage('flags')}>Manage feature flags <ArrowRight size={16}/></button><button className="btn btn-hero-outline" disabled={busy || !canEdit} onClick={() => void simulate()}><Zap size={15}/> {busy ? 'Simulating...' : 'Generate demo traffic'}</button></div></div><div className="hero-visual" aria-hidden="true"><div className="orbit orbit-a"/><div className="orbit orbit-b"/><div className="orbit orbit-c"/><div className="planet planet-1"/><div className="planet planet-2"/><div className="planet planet-3"/><div className="visual-center"><Rocket size={41}/></div><div className="floating-status"><span className="online-dot"/> ALL SYSTEMS GO</div></div></div>
          <div className="section-heading"><div><h2>At a glance</h2><p>Operational pulse across your {environment} environment</p></div><span className="range-pill"><Activity size={14}/> Last 7 days</span></div>
          <div className="stats-grid"><Stat label="Total feature flags" value={number(metrics?.total_flags ?? 0)} detail={`${metrics?.active_flags ?? 0} currently active`} icon={FlagIcon} accent="#8b7bff" points={[1,1,2,2,3,4,metrics?.total_flags ?? 0]} /><Stat label="Total evaluations" value={number(metrics?.evaluations ?? 0)} detail="Events captured this week" icon={Activity} accent="#00dbb9" points={chartPoints}/><Stat label="Unique exposures" value={number(metrics?.unique_users ?? 0)} detail="Pseudonymous subjects" icon={Users} accent="#ffa965" points={chartPoints}/><Stat label="Conversion rate" value={`${metrics?.conversion_rate ?? 0}%`} detail={`${metrics?.conversions ?? 0} converted subjects`} icon={TrendingUp} accent="#88b5ff" points={metrics?.daily.map(x => x.conversions) ?? [0,0,0,0,0,0,0]}/></div>
          <div className="overview-grid"><section className="panel analytics-panel"><div className="panel-head"><div><h3>Evaluation activity</h3><p>Feature decisions over the last 7 days</p></div><span className="legend"><span className="legend-dot"/> Evaluations</span></div><div className="chart-wrap"><div className="y-axis"><span>{number(maxExposure)}</span><span>{number(Math.round(maxExposure * .66))}</span><span>{number(Math.round(maxExposure * .33))}</span><span>0</span></div><div className="chart-area"><div className="gridlines"><i/><i/><i/><i/></div><div className="bars">{metrics?.daily.map((d, i) => <div className="bar-col" key={d.date} title={`${d.date}: ${d.evaluations} evaluations`}><div className="bar" style={{ height: `${Math.max(2, d.evaluations / maxExposure * 100)}%`, opacity: .6 + (i / 6) * .4 }} /><span>{labelDate(d.date)}</span></div>)}</div></div></div><div className="chart-footer"><span><span className="online-dot"/> Event stream available</span><span>Data updates when evaluated</span></div></section><section className="panel health-panel"><div className="panel-head"><div><h3>Release health</h3><p>Current production readiness</p></div><button className="more" title="View flags" onClick={() => setPage('flags')}><MoreHorizontal size={20}/></button></div><div className="health-ring"><div className="ring-inner"><ShieldCheck size={25}/><strong>{metrics?.total_flags ? Math.round((metrics.active_flags / metrics.total_flags) * 100) : 0}%</strong><span>Active flags</span></div></div><div className="health-lines"><div><span><span className="status-square active"/> Enabled features</span><strong>{metrics?.active_flags ?? 0}</strong></div><div><span><span className="status-square paused"/> Paused features</span><strong>{(metrics?.total_flags ?? 0) - (metrics?.active_flags ?? 0)}</strong></div><div><span><span className="status-square neutral"/> Environments</span><strong>3</strong></div></div></section></div>
          <section className="panel recent-panel"><div className="panel-head"><div><h3>Feature flag overview</h3><p>Review your most important releases</p></div><button className="text-link" onClick={() => setPage('flags')}>View all flags <ArrowRight size={15}/></button></div>{flags.slice(0, 3).map((f, i) => <div key={f.id} className="recent-row"><div className="recent-logo" style={{ color: colors[i] }}><Layers3 size={17}/></div><div className="recent-name"><strong>{f.name}</strong><span>{f.key}</span></div><span className={`pill ${f.enabled ? 'pill-live' : 'pill-muted'}`}>{f.enabled ? 'Live' : 'Paused'}</span><div className="recent-rollout"><div className="progress"><span style={{ width: `${f.rollout}%`, background: colors[i] }}/></div><b>{f.rollout}%</b></div><button aria-label={`Edit ${f.name}`} className="go-icon" onClick={() => setPage('flags')}><ArrowUpRight size={17}/></button></div>)}{flags.length === 0 && <div className="empty">No flags here yet. Create your first one.</div>}</section>
          <div className="disclaimer"><CircleHelp size={15}/> {authMode === 'demo' ? 'Local demo auth bypass is enabled; seeded examples and generated traffic are synthetic.' : 'OIDC is enabled; rollout metrics are descriptive, not causal proof.'}</div>
        </>}
        {!loading && page === 'flags' && <><div className="summary-banner"><div className="banner-icon"><FlagIcon size={22}/></div><div><strong>{metrics?.active_flags ?? 0} active features</strong><span>Gradual rollouts use deterministic, SHA-256-based bucketing</span></div><span className="banner-trail">{metrics?.total_flags ?? 0} total <ArrowUpRight size={17}/></span></div><div className="panel flags-panel"><div className="panel-head"><div><h3>Release configuration</h3><p>Pause or adjust rollout percentages without redeploying</p></div><div className="search"><Search size={16}/><input placeholder="Search flags..." aria-label="Search flags" value={search} onChange={e => setSearch(e.target.value)}/></div></div><div className="flags-list">{displayed.map((f, i) => <FlagRow key={f.id} flag={f} idx={i} onSave={onSave} busy={busy || !canEdit}/>)}{displayed.length === 0 && <div className="empty">No matching flags. Try another search or create one.</div>}</div></div><div className="tip-strip"><ShieldCheck size={18}/><div><strong>Safe by design</strong><span>Version checks prevent stale writes. Every configuration update creates an audit event. RBAC is enforced by the API; flags are cached with bounded TTL.</span></div></div></>}
        {!loading && page === 'playground' && <div className="playground-grid"><section className="panel playground-panel"><div className="panel-head"><div><h3>Live evaluation</h3><p>Run the exact targeting function used by the API</p></div><div className="code-badge"><Code2 size={13}/> REST API</div></div><div className="form-grid"><label>Feature flag<select value={selected} onChange={e => setSelected(e.target.value)}>{flags.map(f => <option key={f.id} value={f.key}>{f.name}</option>)}</select></label><label>User identifier<input value={userId} maxLength={128} onChange={e => setUserId(e.target.value)} placeholder="user_123"/></label></div><div className="evaluation-context"><span><Radio size={13}/> {environment}</span><span><Gauge size={13}/> {selectedFlag?.rollout ?? 0}% rollout</span><span><ShieldCheck size={13}/> Stable assignment</span></div><button className="btn btn-primary eval-button" disabled={busy || !selected || !userId} onClick={() => void doEvaluate()}><Zap size={17}/> {busy ? 'Evaluating...' : 'Evaluate feature'} <ArrowRight size={16}/></button><div className="response-label"><span>DECISION RESPONSE</span><span>application/json</span></div><div className="response-box">{evaluation ? <><div className="response-status"><span className={evaluation.enabled ? 'result-on' : 'result-off'}>{evaluation.enabled ? <CheckCheck size={19}/> : <X size={19}/>} {evaluation.enabled ? 'FLAG ENABLED' : 'FLAG DISABLED'}</span><span>HTTP 200</span></div><pre>{JSON.stringify(evaluation, null, 2)}</pre></> : <div className="empty-response"><Cpu size={28}/><strong>Awaiting evaluation</strong><span>Choose a flag and user ID to see a deterministic decision.</span></div>}</div>{evaluation && <button className="btn btn-outline conversion-btn" disabled={busy} onClick={() => void doConvert()}><TrendingUp size={16}/> Record user conversion</button>}</section><section className="panel insight-panel"><div className="panel-head"><div><h3>Under the hood</h3><p>How one user gets a consistent decision</p></div></div><div className="engine-step"><div className="engine-index">01</div><div><strong>Hash identity with a secret salt</strong><p>SHA-256 combines flag salt, environment, flag key, and user ID.</p></div></div><div className="step-line"/><div className="engine-step"><div className="engine-index">02</div><div><strong>Assign a stable bucket</strong><p>Convert the digest into a deterministic number from 0 to 9,999.</p></div></div><div className="step-line"/><div className="engine-step"><div className="engine-index">03</div><div><strong>Apply rollout policy</strong><p>Serve the feature only if enabled and the bucket falls within the rollout.</p></div></div><div className="step-line"/><div className="engine-step"><div className="engine-index">04</div><div><strong>Log pseudonymous exposure</strong><p>Record the decision without storing the raw user identifier.</p></div></div><div className="example-code"><div><span className="code-light"/><span>Try with curl</span></div><pre>{`curl -X POST http://127.0.0.1:8000/api/evaluate \\\n  -H 'Content-Type: application/json' \\\n  -d '{"key":"${selected || 'ai_search'}",\n       "user_id":"user_42",\n       "environment":"${environment}"}'`}</pre></div></section></div>}
        {!loading && page === 'audit' && <section className="panel audit-panel"><div className="panel-head"><div><h3>Configuration change history</h3><p>An append-only record of feature-flag operations</p></div><span className="range-pill"><FileClock size={15}/> Latest {audits.length}</span></div><div className="audit-list">{audits.map((a, i) => <div className="audit-row" key={a.id}><div className={`audit-icon ${a.action === 'updated' ? 'audit-updated' : ''}`}>{a.action === 'updated' ? <Settings2 size={17}/> : a.action === 'seed' ? <Sparkles size={16}/> : <Plus size={17}/>}</div>{i !== audits.length - 1 && <span className="audit-connector"/>}<div className="audit-body"><div><strong>{a.flag_key}</strong><span className="audit-action">{a.action}</span></div><p><b>{a.actor}</b> {a.action === 'updated' ? 'updated feature configuration' : a.action === 'seed' ? 'initialized the demo flag' : 'created a new feature flag'}</p>{a.action === 'updated' && <div className="change-detail">{typeof a.before.rollout === 'number' && a.before.rollout !== a.after.rollout && <span>Rollout: {String(a.before.rollout)}% <ArrowRight size={11}/> {String(a.after.rollout)}%</span>}{a.before.enabled !== a.after.enabled && <span>Enabled: {String(a.before.enabled)} <ArrowRight size={11}/> {String(a.after.enabled)}</span>}</div>}</div><span className="audit-time">{timeAgo(a.created_at)}</span></div>)}{audits.length === 0 && <div className="empty">No audit entries yet.</div>}</div></section>}
        {!loading && page === 'experiments' && <section className="panel experiment-panel">
          <div className="panel-head"><div><h3>Experiment analysis</h3><p>Compare unique exposed users in control versus treatment</p></div><span className="code-badge">Two-proportion z-test</span></div>
          <div className="experiment-controls"><label htmlFor="experiment-flag">Feature flag</label><select id="experiment-flag" value={selected} onChange={e => setSelected(e.target.value)}>{flags.map(f => <option key={f.id} value={f.key}>{f.name}</option>)}</select><button className="btn btn-primary" disabled={experimentLoading || !selected} onClick={() => void loadExperiment()}>{experimentLoading ? 'Analyzing…' : 'Analyze cohorts'}</button></div>
          {experiment ? <><div className="experiment-cards">{(['control', 'treatment'] as const).map(arm => <div className="experiment-stat" key={arm}><span>{arm === 'control' ? 'Control / not served' : 'Treatment / served'}</span><strong>{(experiment[arm].rate * 100).toFixed(2)}%</strong><p>{experiment[arm].conversions} conversions / {experiment[arm].users} exposed users</p><small>95% Wilson CI: {(experiment[arm].ci95[0] * 100).toFixed(2)}–{(experiment[arm].ci95[1] * 100).toFixed(2)}%</small></div>)}</div><p>Absolute lift: {experiment.absolute_lift === null ? 'N/A' : `${(experiment.absolute_lift * 100).toFixed(2)} percentage points`} · P-value: {experiment.p_value ?? 'N/A'}</p><div className="experiment-warnings" role="note">{experiment.warnings.map(x => <p key={x}>• {x}</p>)}</div></> : <p className="experiment-intro">Choose a flag, generate synthetic evaluations on Overview, then click Analyze cohorts. Significance is not evidence of causal effect without randomization.</p>}
        </section>}
      </main>
      <footer className="footer"><div><Mark size={22}/><span>LaunchPilot</span><span className="footer-divider">·</span> Designed for developer demos</div><span>React · TypeScript · FastAPI · PostgreSQL · OIDC <ArrowDownRight size={14}/></span></footer>
    </div>
    {notice && <div className={`toast ${notice.error ? 'toast-error' : ''}`} role="status"><span>{notice.error ? <X size={17}/> : <Check size={17}/>}</span>{notice.text}<button aria-label="Close notification" onClick={() => setNotice(null)}><X size={15}/></button></div>}
    {showNew && canEdit && <NewFlagModal environment={environment} onCreate={onCreate} onClose={() => setShowNew(false)}/>}
  </div>
}
export default App
