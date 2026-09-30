import { useEffect, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowDownToLine, ArrowRight, Bell, Bot, Check, ChevronDown,
  ClipboardList, Command, FileUp, Fingerprint, Gauge, KeyRound,
  LayoutDashboard, Link2, LoaderCircle, LogOut, Menu, Plus, Search, Shield, ShieldAlert,
  ShieldCheck, SlidersHorizontal, Users, X,
} from 'lucide-react'
import { Alert, api, clearToken, Incident, login, Role, User } from './api'

type Page = 'overview' | 'alerts' | 'incidents' | 'playbooks' | 'admin'
type Dashboard = { open_alerts: number; open_incidents: number; critical_alerts: number; events_24h: number; recent_alerts: Alert[]; system: Record<string, string> }
type Rule = { key: string; name: string; event_type: string; threshold: number; window_minutes: number; severity: string; enabled: boolean }
type AdminUser = { username: string; role: string; active: boolean }
type Integration = { key: string; name: string; kind: string; mode: string; enabled: boolean }
type AppNotification = { id: number; title: string; body: string; read: boolean; created_at: string }
const roleNames: Record<Role, string> = { admin: 'Administrateur', analyst: 'Analyste SOC', soc_manager: 'Responsable SOC' }
const severityNames: Record<string, string> = { critical: 'Critique', high: 'Élevée', medium: 'Modérée', low: 'Faible' }
const statusNames: Record<string, string> = { new: 'Nouvelle', incident: 'Incident', triage: 'Qualification', investigating: 'Investigation', contained: 'Contenu', resolved: 'Résolu', closed: 'Clôturé', awaiting_approval: 'En attente', completed_simulated: 'Simulation terminée', queued: 'En file' }
const formatDate = (value: string) => new Date(value).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' })

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [page, setPage] = useState<Page>('overview')
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [selected, setSelected] = useState<Incident | null>(null)
  const [search, setSearch] = useState('')
  const [severityFilter, setSeverityFilter] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [loginName, setLoginName] = useState('analyst')
  const [password, setPassword] = useState('DemoAnalyst!2026')
  const [mobileNav, setMobileNav] = useState(false)
  const [rules, setRules] = useState<Rule[]>([])
  const [users, setUsers] = useState<AdminUser[]>([])
  const [assignees, setAssignees] = useState<AdminUser[]>([])
  const [auditRows, setAuditRows] = useState<Record<string, any>[]>([])
  const [notifications, setNotifications] = useState<AppNotification[]>([])
  const [notificationOpen, setNotificationOpen] = useState(false)
  const [comment, setComment] = useState('')
  const [assistantQuestion, setAssistantQuestion] = useState('Résume cet incident et indique les prochaines vérifications.')
  const [assistantAnswer, setAssistantAnswer] = useState<Record<string, any> | null>(null)
  const [newUser, setNewUser] = useState({ username: '', password: '', role: 'analyst' })
  const [adminTab, setAdminTab] = useState<'rules' | 'users' | 'audit' | 'integrations'>('rules')
  const [integrations, setIntegrations] = useState<Integration[]>([])

  const notify = (message: string) => {
    setToast(message)
    window.setTimeout(() => setToast(''), 3200)
  }

  async function refresh() {
    setLoading(true)
    setError('')
    try {
      const [dash, alertRows, incidentRows, notificationRows, assigneeRows] = await Promise.all([
        api<Dashboard>('/dashboard'), api<Alert[]>('/alerts'), api<Incident[]>('/incidents'), api<AppNotification[]>('/notifications'), api<AdminUser[]>('/assignees'),
      ])
      setDashboard(dash)
      setAlerts(alertRows)
      setIncidents(incidentRows)
      setNotifications(notificationRows)
      setAssignees(assigneeRows)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Chargement impossible')
    } finally {
      setLoading(false)
    }
  }

  async function openIncident(id: number) {
    setBusy(true)
    setError('')
    try {
      const result = await api<Incident>(`/incidents/${id}`)
      setSelected(result)
      setAssistantAnswer(null)
      setPage('incidents')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Incident indisponible')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { if (user) void refresh() }, [user])

  useEffect(() => {
    if (!selected?.playbook_runs?.some(run => run.status === 'queued')) return
    const id = window.setInterval(() => {
      void api<Incident>(`/incidents/${selected.id}`).then(result => {
        setSelected(current => current?.id === result.id ? result : current)
      }).catch(caught => setError(caught instanceof Error ? caught.message : 'Actualisation impossible'))
    }, 2000)
    return () => window.clearInterval(id)
  }, [selected?.id, selected?.playbook_runs])

  async function handleLogin(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try { setUser(await login(loginName, password)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Connexion impossible') }
    finally { setBusy(false) }
  }

  async function loadAdmin() {
    try {
      const [ruleRows, userRows, auditData, integrationRows] = await Promise.all([api<Rule[]>('/rules'), api<AdminUser[]>('/users'), api<Record<string, any>[]>('/audit'), api<Integration[]>('/integrations')])
      setRules(ruleRows); setUsers(userRows); setAuditRows(auditData); setIntegrations(integrationRows)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Administration indisponible') }
  }

  useEffect(() => { if (page === 'admin' && user && (user.role === 'admin' || user.role === 'soc_manager')) void loadAdmin() }, [page, user])

  async function createIncident(alert: Alert) {
    setBusy(true)
    try {
      const incident = await api<Incident>(`/alerts/${alert.id}/incident`, { method: 'POST' })
      await refresh(); await openIncident(incident.id); notify('Incident créé et affecté')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Création impossible') }
    finally { setBusy(false) }
  }

  async function startScenario() {
    setBusy(true)
    setError('')
    try {
      const result = await api<{ accepted: number }>('/demo/scenario', { method: 'POST' })
      await refresh()
      setPage('alerts')
      notify(`Scénario lancé · ${result.accepted} événements synthétiques`)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Scénario indisponible') }
    finally { setBusy(false) }
  }

  async function patchIncident(patch: Record<string, string>) {
    if (!selected) return
    setBusy(true)
    try {
      await api(`/incidents/${selected.id}`, { method: 'PATCH', body: JSON.stringify(patch) })
      await refresh(); await openIncident(selected.id); notify('Incident mis à jour')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Mise à jour impossible') }
    finally { setBusy(false) }
  }

  async function addComment(event: React.FormEvent) {
    event.preventDefault()
    if (!selected || !comment.trim()) return
    try {
      await api(`/incidents/${selected.id}/comments`, { method: 'POST', body: JSON.stringify({ content: comment }) })
      setComment(''); await openIncident(selected.id); notify('Commentaire ajouté')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Commentaire impossible') }
  }

  async function uploadEvidence(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!selected || !file) return
    const form = new FormData(); form.set('file', file)
    try {
      await api(`/incidents/${selected.id}/evidence`, { method: 'POST', body: form })
      await openIncident(selected.id); notify('Preuve conservée avec empreinte SHA-256')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Envoi de preuve impossible') }
    event.target.value = ''
  }

  async function downloadEvidence(entryId: number) {
    if (!selected) return
    try {
      const response = await fetch(`/api/incidents/${selected.id}/evidence/${entryId}`, { headers: { Authorization: `Bearer ${localStorage.getItem('sentinel.access_token') || ''}` } })
      if (!response.ok) throw new Error('Téléchargement de la preuve impossible')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = 'evidence.bin'
      link.click()
      URL.revokeObjectURL(url)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Téléchargement impossible') }
  }

  async function analyze() {
    if (!selected) return
    setBusy(true); setError('')
    try { setAssistantAnswer(await api(`/incidents/${selected.id}/assistant`, { method: 'POST', body: JSON.stringify({ question: assistantQuestion }) })) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Analyse indisponible') }
    finally { setBusy(false) }
  }

  async function runPlaybook(key: string) {
    if (!selected) return
    setBusy(true)
    try {
      const run = await api<{ status: string }>(`/incidents/${selected.id}/playbooks`, { method: 'POST', body: JSON.stringify({ playbook_key: key }) })
      await openIncident(selected.id); notify(run.status === 'awaiting_approval' ? 'Approbation SOC requise' : 'Playbook simulé lancé')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Playbook impossible') }
    finally { setBusy(false) }
  }

  async function approveRun(id: number) {
    try { await api(`/playbook-runs/${id}/approve`, { method: 'POST' }); if (selected) await openIncident(selected.id); notify('Action sensible approuvée, simulation terminée') }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Approbation impossible') }
  }

  async function updateRule(rule: Rule, patch: Partial<Rule>) {
    try { await api(`/rules/${rule.key}`, { method: 'PATCH', body: JSON.stringify(patch) }); await loadAdmin(); notify('Règle mise à jour') }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Modification impossible'); await loadAdmin() }
  }

  async function toggleRule(rule: Rule) {
    try { await api(`/rules/${rule.key}`, { method: 'PATCH', body: JSON.stringify({ enabled: !rule.enabled }) }); await loadAdmin(); notify('Règle mise à jour') }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Modification impossible') }
  }

  async function toggleIntegration(integration: Integration) {
    try {
      await api(`/integrations/${integration.key}`, { method: 'PATCH', body: JSON.stringify({ enabled: !integration.enabled }) })
      await loadAdmin(); notify('Intégration mise à jour')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Modification impossible') }
  }

  async function addUser(event: React.FormEvent) {
    event.preventDefault()
    try {
      await api('/users', { method: 'POST', body: JSON.stringify(newUser) })
      setNewUser({ username: '', password: '', role: 'analyst' }); await loadAdmin(); notify('Utilisateur ajouté')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Création utilisateur impossible') }
  }

  async function readNotification(item: AppNotification) {
    try {
      await api(`/notifications/${item.id}/read`, { method: 'PATCH' })
      setNotifications(rows => rows.map(row => row.id === item.id ? { ...row, read: true } : row))
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Notification indisponible') }
  }

  function logout() { clearToken(); setUser(null); setSelected(null); setDashboard(null) }

  if (!user) return <main className="login-shell"><section className="login-card"><div className="brand-mark"><ShieldCheck size={23} /></div><p className="eyebrow">SENTINEL / LABORATOIRE SOC</p><h1>Centre des opérations<br />de sécurité</h1><p className="muted">Console d’investigation pour événements synthétiques.</p>
    <form onSubmit={handleLogin} className="login-form"><label>Identifiant<input value={loginName} onChange={event => setLoginName(event.target.value)} autoComplete="username" required /></label><label>Mot de passe<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" required /></label>{error && <div className="error-banner">{error}</div>}<button className="button button-primary wide" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <KeyRound size={16} />} Ouvrir la console <ArrowRight size={16} /></button></form>
    <div className="demo-hint"><span>ACCÈS DE DÉMONSTRATION</span><code>analyst / DemoAnalyst!2026</code><code>manager / DemoManager!2026</code></div></section><div className="login-side"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="login-signal"><span className="pulse-dot"/> SYSTÈMES OPÉRATIONNELS</div><div className="login-side-copy"><span>01 — DÉTECTION</span><span>02 — QUALIFICATION</span><span>03 — RÉPONSE CONTRÔLÉE</span></div></div></main>

  const navItems: { key: Page; label: string; icon: typeof Gauge }[] = [
    { key: 'overview', label: 'Vue générale', icon: LayoutDashboard }, { key: 'alerts', label: 'Alertes', icon: ShieldAlert },
    { key: 'incidents', label: 'Incidents', icon: ClipboardList }, { key: 'playbooks', label: 'Playbooks', icon: Activity },
    ...(user.role !== 'analyst' ? [{ key: 'admin' as Page, label: 'Administration', icon: SlidersHorizontal }] : []),
  ]
  const visibleAlerts = alerts.filter(alert => (!severityFilter || alert.severity === severityFilter) && alert.title.toLowerCase().includes(search.toLowerCase()))
  const visibleIncidents = incidents.filter(item => item.title.toLowerCase().includes(search.toLowerCase()))

  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}><div className="sidebar-brand"><div className="brand-mark"><ShieldCheck size={19} /></div><div><strong>SENTINEL</strong><span>SECURITY OPERATIONS</span></div><button className="icon-button nav-close" title="Fermer le menu" onClick={() => setMobileNav(false)}><X size={18} /></button></div>
      <div className="workspace-label">ESPACE DE TRAVAIL <span className="live-indicator"/></div><nav>{navItems.map(item => <button key={item.key} onClick={() => { setPage(item.key); setMobileNav(false); setError('') }} className={`nav-link ${page === item.key ? 'active' : ''}`}><item.icon size={17} /><span>{item.label}</span>{item.key === 'alerts' && dashboard?.open_alerts ? <b>{dashboard.open_alerts}</b> : null}</button>)}</nav>
      <div className="sidebar-bottom"><div className="env-box"><span className="env-icon"><Shield size={15} /></span><div><strong>LAB / SYNTHÉTIQUE</strong><small>Actions externes désactivées</small></div></div><button className="profile-row" onClick={logout}><span className="avatar">{user.username.slice(0, 1).toUpperCase()}</span><span className="profile-copy"><strong>{user.username}</strong><small>{roleNames[user.role]}</small></span><LogOut size={16} /></button></div>
    </aside>
    {mobileNav && <button className="scrim" aria-label="Fermer la navigation" onClick={() => setMobileNav(false)} />}
    <main className="main-area"><header className="topbar"><button className="icon-button menu-trigger" aria-label="Ouvrir la navigation" onClick={() => setMobileNav(true)}><Menu size={20} /></button><div className="crumb"><span>OPS</span><ArrowRight size={13} /><strong>{navItems.find(item => item.key === page)?.label.toUpperCase()}</strong></div><div className="topbar-right"><span className="api-state"><i/> API OPÉRATIONNELLE</span><div className="notification-wrap"><button className="icon-button notification-trigger" title="Notifications" aria-label="Notifications" aria-expanded={notificationOpen} onClick={() => setNotificationOpen(value => !value)}><Bell size={17}/>{notifications.some(item => !item.read) && <i className="notification-dot"/>}</button>{notificationOpen && <div className="notification-popover"><div className="notification-title"><strong>Notifications</strong><span>{notifications.filter(item => !item.read).length} non lues</span></div>{notifications.length ? notifications.map(item => <button className={`notification-item ${item.read ? 'read' : ''}`} key={item.id} onClick={() => void readNotification(item)}><span className="notification-marker"/><span><strong>{item.title}</strong><small>{item.body}</small><time>{formatDate(item.created_at)}</time></span></button>) : <p className="notification-empty">Aucune notification récente.</p>}</div>}</div><span className="top-avatar">{user.username.slice(0, 1).toUpperCase()}</span></div></header>
      <div className="page-content">{error && <div className="error-banner"><AlertTriangle size={16} />{error}<button onClick={() => setError('')}><X size={15}/></button></div>}
        {page === 'overview' && <><div className="page-heading"><div><p className="eyebrow">CENTRE DE SITUATION <span className="heading-date">/ {new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })}</span></p><h1>Vue générale</h1><p className="muted">État des détections et activité d’investigation.</p></div><div className="heading-actions"><button className="button button-secondary" disabled={busy} onClick={() => void startScenario()}><Command size={15}/> Lancer le scénario</button><button className="button button-secondary" onClick={() => void refresh()}><Activity size={15}/> Actualiser</button></div></div>
          {loading && !dashboard ? <div className="loading-panel"><LoaderCircle className="spin"/> Chargement des signaux...</div> : <><section className="metric-grid">{[{ label: 'Alertes ouvertes', value: dashboard?.open_alerts ?? 0, icon: ShieldAlert, note: 'À qualifier', tone: 'coral' }, { label: 'Incidents actifs', value: dashboard?.open_incidents ?? 0, icon: ClipboardList, note: 'En cours de traitement', tone: 'blue' }, { label: 'Critiques', value: dashboard?.critical_alerts ?? 0, icon: AlertTriangle, note: 'Priorité immédiate', tone: 'yellow' }, { label: 'Événements reçus', value: dashboard?.events_24h ?? 0, icon: Fingerprint, note: 'Tous les événements', tone: 'green' }].map(metric => <article className="metric-card" key={metric.label}><div className={`metric-icon ${metric.tone}`}><metric.icon size={17}/></div><div className="metric-label">{metric.label}</div><strong className="metric-value">{metric.value.toLocaleString('fr-FR')}</strong><span className="metric-note">{metric.note}</span></article>)}</section>
          <div className="overview-grid"><section className="panel recent-panel"><div className="panel-heading"><div><p className="eyebrow">FLUX DE DÉTECTION</p><h2>Alertes récentes</h2></div><button className="text-button" onClick={() => setPage('alerts')}>Toutes les alertes <ArrowRight size={14}/></button></div><AlertTable rows={dashboard?.recent_alerts ?? []} onIncident={createIncident} onOpen={id => void openIncident(id)} busy={busy}/></section>
            <section className="panel system-panel"><div className="panel-heading"><div><p className="eyebrow">PLATEFORME</p><h2>État des services</h2></div><span className="status-chip status-ok"><i/> Opérationnel</span></div><ServiceStatus name="API Gateway" detail="REST · Authentifié"/><ServiceStatus name="Ingestion & worker" detail={dashboard?.system.worker_mode === 'celery' ? 'Celery / Redis' : 'Mode local direct'} /><ServiceStatus name="Assistant IA" detail={dashboard?.system.ai_provider || 'mock'} /><div className="system-footnote"><ShieldCheck size={15}/> Réponses externes désactivées dans ce laboratoire.</div></section></div></> }</>}

        {page === 'alerts' && <><PageTitle eyebrow="DÉTECTION / TRIAGE" title="Alertes" description="Signaux corrélés par les règles de détection actives." action={<button className="button button-secondary" onClick={() => void refresh()}><Activity size={15}/> Actualiser</button>}/><div className="toolbar"><label className="search-field"><Search size={16}/><input placeholder="Rechercher une alerte..." value={search} onChange={event => setSearch(event.target.value)}/></label><label className="select-field"><SlidersHorizontal size={15}/><select value={severityFilter} onChange={event => setSeverityFilter(event.target.value)}><option value="">Toutes les sévérités</option><option value="critical">Critique</option><option value="high">Élevée</option><option value="medium">Modérée</option><option value="low">Faible</option></select><ChevronDown size={14}/></label><span className="result-count">{visibleAlerts.length} RÉSULTATS</span></div><section className="panel table-panel"><AlertTable rows={visibleAlerts} onIncident={createIncident} onOpen={id => void openIncident(id)} busy={busy}/></section></>}

        {page === 'incidents' && <>{selected ? <IncidentView assignees={assignees} onSeverity={severity => void patchIncident({ severity })} incident={selected} user={user} busy={busy} comment={comment} setComment={setComment} onBack={() => setSelected(null)} onStatus={status => void patchIncident({ status })} onAssignee={assignee => void patchIncident({ assignee })} onComment={addComment} onEvidence={uploadEvidence} onDownload={downloadEvidence} onAnalyze={() => void analyze()} question={assistantQuestion} setQuestion={setAssistantQuestion} answer={assistantAnswer} onPlaybook={runPlaybook} onApprove={approveRun}/> : <><PageTitle eyebrow="INVESTIGATION / CASE MANAGEMENT" title="Incidents" description="Qualification, affectation et suivi des investigations."/><div className="toolbar"><label className="search-field"><Search size={16}/><input placeholder="Rechercher un incident..." value={search} onChange={event => setSearch(event.target.value)}/></label><span className="result-count">{visibleIncidents.length} DOSSIERS</span></div><section className="panel table-panel"><IncidentTable rows={visibleIncidents} onOpen={id => void openIncident(id)}/></section></>}</>}

        {page === 'playbooks' && <><PageTitle eyebrow="RÉPONSE / ORCHESTRATION" title="Playbooks" description="Procédures simulées. Toute action sensible nécessite une approbation SOC."/><section className="playbook-grid">{[{ key: 'collect_evidence', name: 'Préserver les preuves', label: 'COLLECTE', description: 'Prépare les métadonnées utiles à l’investigation et consigne la simulation.', sensitive: false }, { key: 'isolate_host', name: 'Isoler un actif', label: 'CONFINEMENT', description: 'Action sensible soumise à approbation par un responsable SOC.', sensitive: true }, { key: 'disable_account', name: 'Désactiver un compte', label: 'IDENTITÉ', description: 'Action sensible soumise à approbation par un responsable SOC.', sensitive: true }].map(item => <article className="playbook-card" key={item.key}><div className="playbook-glyph"><Command size={20}/></div><div className="playbook-tag">{item.label}</div><h2>{item.name}</h2><p>{item.description}</p><div className="playbook-bottom"><span className={item.sensitive ? 'approval-label' : 'simulation-label'}>{item.sensitive ? <KeyRound size={13}/> : <ShieldCheck size={13}/>} {item.sensitive ? 'APPROBATION REQUISE' : 'SIMULATION'}</span><button className="icon-button" title="Ouvrir un incident avant lancement" onClick={() => { setPage('incidents'); setSelected(null) }}><ArrowRight size={17}/></button></div></article>)}</section><div className="info-strip"><ShieldCheck size={16}/> Les playbooks peuvent être lancés depuis un incident ouvert. Aucune intégration d’action réelle n’est configurée.</div></>}

        {page === 'admin' && <><PageTitle eyebrow="GOUVERNANCE / CONTRÔLE" title="Administration" description="Règles de détection, utilisateurs et journal d’audit."/><div className="segmented-control">{(['rules', 'users', 'audit'] as const).map(tab => <button className={adminTab === tab ? 'selected' : ''} key={tab} onClick={() => setAdminTab(tab)}>{tab === 'rules' ? <><ShieldAlert size={15}/> Règles</> : tab === 'users' ? <><Users size={15}/> Utilisateurs</> : <><Fingerprint size={15}/> Audit</>}</button>)}</div>{adminTab === 'rules' && <section className="panel admin-panel"><div className="panel-heading"><div><p className="eyebrow">DÉTECTION</p><h2>Règles de corrélation</h2></div></div>{rules.map(rule => <div className="rule-row" key={rule.key}><div><strong>{rule.name}</strong><small>{rule.event_type} · seuil {rule.threshold} / {rule.window_minutes} min · {severityNames[rule.severity]}</small></div><div className="rule-controls"><label>Seuil<input aria-label={`Seuil ${rule.key}`} type="number" min={2} max={100} defaultValue={rule.threshold} key={`threshold-${rule.threshold}`} onBlur={event => { const value = Number(event.target.value); if (value !== rule.threshold && value >= 2 && value <= 100) void updateRule(rule, { threshold: value }) }}/></label><label>Fenêtre (min)<input type="number" min={1} max={1440} defaultValue={rule.window_minutes} key={`window-${rule.window_minutes}`} onBlur={event => { const value = Number(event.target.value); if (value !== rule.window_minutes && value >= 1 && value <= 1440) void updateRule(rule, { window_minutes: value }) }}/></label><label>Sévérité<select value={rule.severity} onChange={event => void updateRule(rule, { severity: event.target.value })}>{Object.entries(severityNames).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label></div><button role="switch" aria-checked={rule.enabled} className={`toggle ${rule.enabled ? 'on' : ''}`} disabled={busy} onClick={() => void toggleRule(rule)} title="Activer ou désactiver la règle"><i/></button></div>)}</section>}{adminTab === 'users' && <div className="admin-columns"><section className="panel admin-panel"><div className="panel-heading"><div><p className="eyebrow">IDENTITÉS</p><h2>Comptes actifs</h2></div></div>{users.map(item => <div className="user-row" key={item.username}><span className="avatar">{item.username.slice(0, 1).toUpperCase()}</span><strong>{item.username}</strong><span className="role-pill">{roleNames[item.role as Role] || item.role}</span></div>)}</section>{user.role === 'admin' && <section className="panel admin-panel"><div className="panel-heading"><div><p className="eyebrow">NOUVEL ACCÈS</p><h2>Créer un utilisateur</h2></div><Plus size={17}/></div><form className="stacked-form" onSubmit={addUser}><label>Identifiant<input value={newUser.username} onChange={e => setNewUser({ ...newUser, username: e.target.value })} minLength={3} required/></label><label>Mot de passe<input type="password" value={newUser.password} onChange={e => setNewUser({ ...newUser, password: e.target.value })} minLength={12} required/></label><label>Rôle<select value={newUser.role} onChange={e => setNewUser({ ...newUser, role: e.target.value })}><option value="analyst">Analyste SOC</option><option value="soc_manager">Responsable SOC</option><option value="admin">Administrateur</option></select></label><button className="button button-primary"><Plus size={15}/> Créer le compte</button></form></section>}</div>}{adminTab === 'audit' && <section className="panel admin-panel"><div className="panel-heading"><div><p className="eyebrow">TRAÇABILITÉ</p><h2>Opérations récentes</h2></div></div><div className="audit-list">{auditRows.map(row => <div className="audit-row" key={row.id}><time>{formatDate(row.created_at)}</time><strong>{row.action}</strong><span>{row.actor} · {row.target}</span></div>)}</div></section>}</>}
        {page === 'admin' && <button className={`integration-switch ${adminTab === 'integrations' ? 'active' : ''}`} onClick={() => setAdminTab('integrations')}><Link2 size={15}/> Intégrations</button>}
        {page === 'admin' && adminTab === 'integrations' && <section className="panel admin-panel integration-panel"><div className="panel-heading"><div><p className="eyebrow">SOURCES & ENRICHISSEMENT</p><h2>Connecteurs simulés</h2></div></div>{integrations.map(item => <div className="rule-row" key={item.key}><span className="integration-glyph"><Link2 size={15}/></span><div><strong>{item.name}</strong><small>{item.kind} · mode {item.mode} · {item.key}</small></div><button role="switch" aria-checked={item.enabled} className={`toggle ${item.enabled ? 'on' : ''}`} onClick={() => void toggleIntegration(item)} title="Activer ou désactiver le connecteur"><i/></button></div>)}</section>}
      </div>
    </main>{toast && <div className="toast"><Check size={16}/>{toast}</div>}
  </div>
}

function PageTitle({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) { return <div className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="muted">{description}</p></div>{action}</div> }

function AlertTable({ rows, onIncident, onOpen, busy }: { rows: Alert[]; onIncident: (alert: Alert) => void; onOpen: (id: number) => void; busy: boolean }) {
  if (!rows.length) return <EmptyState title="Aucun signal" detail="Aucune alerte ne correspond aux filtres actuels."/>
  return <div className="table-scroll"><table><thead><tr><th>ALERTE</th><th>SÉVÉRITÉ</th><th>ÉVÉNEMENTS</th><th>STATUT</th><th>REÇUE</th><th/></tr></thead><tbody>{rows.map(alert => <tr key={alert.id} onClick={() => alert.incident_id && onOpen(alert.incident_id)} className={alert.incident_id ? 'click-row' : ''}><td><span className="alert-title"><i className={`severity-dot ${alert.severity}`}/><span><strong>{alert.title}</strong><small>DET-{String(alert.id).padStart(5, '0')}</small></span></span></td><td><span className={`severity-label ${alert.severity}`}>{severityNames[alert.severity] || alert.severity}</span></td><td className="mono">{alert.event_count}</td><td><span className="status-text">{statusNames[alert.status] || alert.status}</span></td><td className="date-cell">{formatDate(alert.created_at)}</td><td>{alert.incident_id ? <button className="icon-button row-action" title="Ouvrir l’incident" onClick={event => { event.stopPropagation(); onOpen(alert.incident_id!) }}><ArrowRight size={16}/></button> : <button disabled={busy} className="text-button create-link" onClick={event => { event.stopPropagation(); onIncident(alert) }}>Créer incident <ArrowRight size={14}/></button>}</td></tr>)}</tbody></table></div>
}

function IncidentTable({ rows, onOpen }: { rows: Incident[]; onOpen: (id: number) => void }) {
  if (!rows.length) return <EmptyState title="Aucun incident ouvert" detail="Convertissez une alerte corrélée en incident pour commencer l’investigation."/>
  return <div className="table-scroll"><table><thead><tr><th>DOSSIER</th><th>SÉVÉRITÉ</th><th>STATUT</th><th>AFFECTÉ À</th><th>MODIFIÉ</th><th/></tr></thead><tbody>{rows.map(item => <tr key={item.id} className="click-row" onClick={() => onOpen(item.id)}><td><span className="incident-id">INC-{String(item.id).padStart(5, '0')}</span><strong className="incident-name">{item.title}</strong></td><td><span className={`severity-label ${item.severity}`}>{severityNames[item.severity] || item.severity}</span></td><td>{statusNames[item.status] || item.status}</td><td>{item.assignee || 'Non affecté'}</td><td className="date-cell">{formatDate(item.updated_at)}</td><td><ArrowRight size={16}/></td></tr>)}</tbody></table></div>
}

function IncidentView({ assignees, onSeverity, incident, user, busy, comment, setComment, onBack, onStatus, onAssignee, onComment, onEvidence, onDownload, onAnalyze, question, setQuestion, answer, onPlaybook, onApprove }: { assignees: AdminUser[]; onSeverity: (severity: string) => void; incident: Incident; user: User; busy: boolean; comment: string; setComment: (value: string) => void; onBack: () => void; onStatus: (status: string) => void; onAssignee: (assignee: string) => void; onComment: (event: React.FormEvent) => void; onEvidence: (event: React.ChangeEvent<HTMLInputElement>) => void; onDownload: (id: number) => void; onAnalyze: () => void; question: string; setQuestion: (value: string) => void; answer: Record<string, any> | null; onPlaybook: (key: string) => void; onApprove: (id: number) => void }) {
  const canApprove = user.role === 'admin' || user.role === 'soc_manager'
  const transitions: Record<string, string[]> = { triage: ['investigating', 'closed'], investigating: ['contained', 'resolved', 'closed'], contained: ['investigating', 'resolved', 'closed'], resolved: ['closed', 'investigating'], closed: ['investigating'] }
  const statusOptions = [incident.status, ...(transitions[incident.status] || [])]
  return <><button className="back-link" onClick={onBack}><ArrowRight size={15}/> Tous les incidents</button><div className="incident-heading"><div><p className="eyebrow">DOSSIER INC-{String(incident.id).padStart(5, '0')} <span>/ ALERTE DET-{String(incident.alert_id).padStart(5, '0')}</span></p><h1>{incident.title}</h1><div className="incident-meta"><span className={`severity-label ${incident.severity}`}>{severityNames[incident.severity] || incident.severity}</span><span className="status-chip">{statusNames[incident.status] || incident.status}</span><span>Ouvert {formatDate(incident.created_at)}</span></div></div><label className="assignment-select"><span>AFFECTÉ À</span><select value={incident.assignee || ''} onChange={event => onAssignee(event.target.value)}><option value="">Non affecté</option><option hidden disabled value={incident.assignee || ""}>{incident.assignee}</option>{assignees.map(person => <option key={person.username} value={person.username}>{person.username}</option>)}</select></label></div>
    <div className="incident-layout"><div className="incident-main"><section className="panel evidence-summary"><div className="panel-heading"><div><p className="eyebrow">CONTEXTE ENRICHI</p><h2>Résumé de détection</h2></div><span className="event-count"><Fingerprint size={15}/>{incident.event_count} événements</span></div><div className="context-grid"><ContextItem label="Adresse source" value={incident.context.source_ip || 'Non observée'} mono/><ContextItem label="Compte ciblé" value={incident.context.username || 'Inconnu'}/><ContextItem label="Actif concerné" value={incident.context.asset || 'Inconnu'}/><ContextItem label="Règle" value={incident.context.rule_key || '—'} mono/><ContextItem label="Réputation IP" value={incident.context.enrichment?.ip?.reputation || 'Inconnue'}/><ContextItem label="Domaine" value={incident.context.domain || 'Non observé'}/></div></section>
      <section className="panel timeline-panel"><div className="panel-heading"><div><p className="eyebrow">PREUVES & JOURNAL</p><h2>Chronologie</h2></div><label className="button button-secondary upload-button"><FileUp size={15}/> Ajouter une preuve<input type="file" onChange={onEvidence}/></label></div><div className="timeline">{(incident.events || []).map(event => <article className="timeline-item event-item" key={`event-${event.id}`}><span className="timeline-marker marker-event"><Fingerprint size={13}/></span><div className="timeline-content"><div className="timeline-top"><strong>Événement · {event.event_type}</strong><time>{formatDate(event.occurred_at)}</time></div><p>{event.message}</p><small>{event.source_ip} · {event.username}</small></div></article>)}{(incident.timeline || []).map(entry => <article className="timeline-item" key={`entry-${entry.id}`}><span className={`timeline-marker marker-${entry.kind}`}><Activity size={13}/></span><div className="timeline-content"><div className="timeline-top"><strong>{entry.kind === 'comment' ? 'Commentaire' : entry.kind === 'evidence' ? 'Preuve enregistrée' : entry.kind === 'playbook' ? 'Réponse' : 'Mise à jour'} · {entry.author}</strong><time>{formatDate(entry.created_at)}</time></div><p>{entry.kind === 'evidence' ? `Métadonnées: ${entry.content}` : entry.content}</p>{entry.kind === 'evidence' && <button className="evidence-download" onClick={() => onDownload(entry.id)}><ArrowDownToLine size={13}/> Télécharger la preuve</button>}</div></article>)}</div><form className="comment-form" onSubmit={onComment}><input value={comment} onChange={event => setComment(event.target.value)} placeholder="Ajouter une note d’investigation..."/><button className="button button-primary" disabled={!comment.trim()}><Plus size={15}/> Ajouter</button></form></section>
      <section className="panel playbook-run-panel"><div className="panel-heading"><div><p className="eyebrow">RÉPONSE ORCHESTRÉE</p><h2>Actions disponibles</h2></div></div><div className="action-row"><div><strong>Préserver les preuves</strong><small>Collecte simulée, sans modification système</small></div><button className="button button-secondary" disabled={busy} onClick={() => onPlaybook('collect_evidence')}>Lancer <ArrowRight size={14}/></button></div><div className="action-row"><div><strong>Isoler un actif</strong><small>Action sensible · validation responsable requise</small></div><button className="button button-danger" disabled={busy} onClick={() => onPlaybook('isolate_host')}>Demander <KeyRound size={14}/></button></div><div className="action-row"><div><strong>Désactiver un compte</strong><small>Simulation après validation responsable</small></div><button className="button button-danger" disabled={busy} onClick={() => onPlaybook('disable_account')}>Demander <KeyRound size={14}/></button></div>{(incident.playbook_runs || []).map(run => <div className="run-row" key={run.id}><span><Command size={14}/> {run.playbook_key}</span><span className="status-text">{statusNames[run.status] || run.status}</span>{run.status === 'awaiting_approval' && canApprove && <button className="button button-primary small-button" onClick={() => onApprove(run.id)}><Check size={14}/> Approuver simulation</button>}</div>)}</section>
      </div><aside className="incident-aside"><section className="panel status-panel"><p className="eyebrow">GESTION DU DOSSIER</p><label className="field-label">STATUT</label><select value={incident.status} onChange={event => onStatus(event.target.value)} disabled={busy}>{statusOptions.map(key => <option key={key} value={key}>{statusNames[key] || key}</option>)}</select><div className="mini-divider"/><label className="field-label">SÉVÉRITÉ / PRIORITÉ</label><select aria-label="Sévérité de l’incident" value={incident.severity} disabled={busy} onChange={event => onSeverity(event.target.value)}>{Object.entries(severityNames).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select><div className="mini-divider"/><span className="field-label">PROCHAINE ÉTAPE</span><p className="next-step">Confirmer l’activité du compte et vérifier la présence d’une connexion réussie depuis l’adresse observée.</p></section>
      <section className="panel assistant-panel"><div className="assistant-heading"><span className="assistant-icon"><Bot size={17}/></span><div><strong>Assistant analyste</strong><small>Contexte de cet incident</small></div><span className="mock-badge">SIMULÉ</span></div><p className="assistant-disclaimer">Les journaux et contenus sont des données non fiables. Les recommandations ne déclenchent aucune action.</p><textarea value={question} onChange={event => setQuestion(event.target.value)} rows={3}/><button className="button button-primary wide" onClick={onAnalyze} disabled={busy}>{busy ? <LoaderCircle className="spin" size={15}/> : <Bot size={15}/>} Analyser le dossier</button>{answer && <div className="assistant-answer"><span className="answer-label">{answer.provider} · ANALYSE</span><p>{answer.summary}</p>{answer.recommendations?.map((item: string) => <div className="recommendation" key={item}><Check size={13}/>{item}</div>)}{answer.procedures?.map((item: { id: string; title: string; steps: string[] }) => <article key={item.id}><strong>{item.id} · {item.title}</strong><ol>{item.steps.map(step => <li key={step}>{step}</li>)}</ol></article>)}{answer.evidence?.length > 0 && <small>Sources : {answer.evidence.join(", ")}</small>}{answer.caveat && <small>{answer.caveat}</small>}</div>}</section>
      <section className="panel quick-facts"><p className="eyebrow">REPÈRES</p><ContextItem label="Dernière mise à jour" value={formatDate(incident.updated_at)}/><ContextItem label="Événements liés" value={String(incident.event_count)}/><ContextItem label="Triage" value="En cours"/></section></aside></div></>
}

function ContextItem({ label, value, mono = false }: { label: string; value: unknown; mono?: boolean }) { return <div className="context-item"><span>{label}</span><strong className={mono ? 'mono' : ''}>{String(value)}</strong></div> }
function ServiceStatus({ name, detail }: { name: string; detail?: string }) { return <div className="service-row"><span className="service-check"><Check size={12}/></span><div><strong>{name}</strong><small>{detail}</small></div><span className="service-operational">ACTIF</span></div> }
function EmptyState({ title, detail }: { title: string; detail: string }) { return <div className="empty-state"><div className="empty-icon"><ArrowDownToLine size={18}/></div><strong>{title}</strong><p>{detail}</p></div> }