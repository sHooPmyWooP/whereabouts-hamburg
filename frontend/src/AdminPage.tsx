import { useEffect, useState } from 'react'
import { Activity, ArrowLeft, CalendarDays, RefreshCw, Repeat2, Search, ShieldCheck, UserPlus, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { ApiError, apiFetch } from './api'
import { activeLanguage, formatNumber, formatPercent } from './i18n'

type Dashboard = {
  range_days: number
  overview: { consented_players: number; consented_anonymous_players: number; consented_accounts: number; new_accounts: number; returning_player_rate: number }
  daily_players: { date: string; players: number }[]
  modes: Record<string, number>
  daily: Record<string, number>
  training: Record<string, number>
  seeded_challenges: { fingerprint: string; players: number; opens: number; starts: number; completions: number }[]
}
type AccountRow = { id: number; username: string; registered: string; last_active: string; active_days: number; daily_completions: number; training_attempts: number; is_admin: boolean }
type AccountsResponse = { items: AccountRow[]; page: number; page_size: number; total: number }
type MetricProps = { label: string; value: string | number; icon: LucideIcon; tone: string }

function Metric({ label, value, icon: Icon, tone }: MetricProps) {
  return <div className={`admin-metric admin-metric--${tone}`}><span className="admin-metric__icon"><Icon size={18} aria-hidden="true" /></span><span className="admin-metric__label">{label}</span><strong>{value}</strong></div>
}

function TrendChart({ rows, t }: { rows: Dashboard['daily_players']; t: TFunction }) {
  const max = Math.max(1, ...rows.map((row) => row.players))
  if (!rows.length) return <div className="admin-empty"><Activity size={24} /><p>{t('admin.noActivity')}</p></div>
  return <div className="admin-chart" aria-label={t('admin.chart')}><div className="admin-chart__scale"><span>{max}</span><span>{max > 1 ? Math.round(max / 2) : '0.5'}</span><span>0</span></div><div className="admin-chart__plot">{rows.map((row) => <div className="admin-chart__column" key={row.date} title={`${row.date}: ${t('admin.players', { count: row.players })}`}><span className="admin-chart__value">{formatNumber(row.players)}</span><span className="admin-chart__bar" style={{ height: `${Math.max(5, row.players / max * 100)}%` }} /><small>{row.date.slice(5)}</small></div>)}</div></div>
}

const metricKeys: Record<string, string> = {
  account_starts: 'admin.metric.account_starts', account_completions: 'admin.metric.account_completions', account_abandoned: 'admin.metric.account_abandoned', completion_rate: 'admin.metric.completion_rate', give_up_rate: 'admin.metric.give_up_rate', average_pins_solved: 'admin.metric.average_pins_solved', average_guesses_spent: 'admin.metric.average_guesses_spent', consented_starts: 'admin.metric.consented_starts', consented_completions: 'admin.metric.consented_completions', sessions: 'admin.metric.sessions', engaged_sessions: 'admin.metric.engaged_sessions', attempts: 'admin.metric.attempts', accuracy: 'admin.metric.accuracy', returning_learners: 'admin.metric.returning_learners', home: 'admin.metric.home', daily: 'admin.metric.daily', training: 'admin.metric.training', explore: 'admin.metric.explore', admin: 'admin.metric.admin',
}
function StatList({ values, t }: { values: Record<string, number>; t: TFunction }) {
  return <dl className="admin-stat-list">{Object.entries(values).map(([key, value]) => <div key={key}><dt>{t(metricKeys[key] ?? 'common.error')}</dt><dd>{key.endsWith('rate') || key === 'accuracy' ? formatPercent(value) : formatNumber(value)}</dd></div>)}</dl>
}

export function AdminPage({ onHome }: { onHome: () => void }) {
  const { t } = useTranslation()
  const [days, setDays] = useState<0 | 7 | 30 | 90>(30)
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [accounts, setAccounts] = useState<AccountsResponse | null>(null)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState('last_active')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [requestId, setRequestId] = useState(0)


  useEffect(() => {
    let cancelled = false
    Promise.all([apiFetch<Dashboard>(`/api/admin/dashboard?days=${days}`), apiFetch<AccountsResponse>(`/api/admin/accounts?page=${page}&search=${encodeURIComponent(search)}&sort=${sort}&direction=desc`)]).then(([dashboardResult, accountResult]) => {
      if (!cancelled) { setDashboard(dashboardResult); setAccounts(accountResult); setError(null) }
    }).catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof ApiError && reason.status === 403 ? t('admin.restricted') : t('admin.loadError'))
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [days, page, requestId, search, sort, t])

  const refresh = () => { setLoading(true); setRequestId((value) => value + 1) }
  return <main className="admin-page">
    <div className="admin-hero"><header className="admin-header">
      <button className="admin-back" type="button" onClick={onHome}><ArrowLeft size={17} /> {t('admin.back')}</button>
      <div className="admin-heading"><p className="eyebrow">{t('admin.eyebrow')}</p><h1>{t('admin.title')}</h1><p>{t('admin.subtitle')}</p></div>
      <button className="admin-refresh" type="button" onClick={refresh} disabled={loading}><RefreshCw size={17} className={loading ? 'admin-spin' : ''} aria-hidden="true" /><span>{t(loading ? 'admin.refreshing' : 'admin.refresh')}</span></button>
    </header></div>
    <div className="admin-content">
      {error ? <section className="admin-error" role="alert"><ShieldCheck size={28} /><div><h2>{t('admin.unavailable')}</h2><p>{error}</p></div><button type="button" onClick={refresh}>{t('common.tryAgain')}</button></section> : null}
      {dashboard ? <>
        <div className="admin-toolbar"><div><CalendarDays size={17} /><span>{t('admin.reportingPeriod')}</span></div><nav className="admin-ranges" aria-label={t('admin.dateRange')}>{([7, 30, 90, 0] as const).map((range) => <button key={range} className={days === range ? 'active' : ''} type="button" onClick={() => { setLoading(true); setDays(range); setPage(1) }}>{range ? t('admin.days', { count: range }) : t('admin.all')}</button>)}</nav></div>
        <section className="admin-metrics" aria-label={t('admin.title')}>
          <Metric label={t('admin.consentedPlayers')} value={formatNumber(dashboard.overview.consented_players)} icon={Users} tone="green" /><Metric label={t('admin.anonymousPlayers')} value={formatNumber(dashboard.overview.consented_anonymous_players)} icon={ShieldCheck} tone="blue" /><Metric label={t('admin.consentedAccounts')} value={formatNumber(dashboard.overview.consented_accounts)} icon={Activity} tone="amber" /><Metric label={t('admin.newAccounts')} value={formatNumber(dashboard.overview.new_accounts)} icon={UserPlus} tone="violet" /><Metric label={t('admin.returningRate')} value={formatPercent(dashboard.overview.returning_player_rate)} icon={Repeat2} tone="coral" />
        </section>
        <p className="admin-coverage"><ShieldCheck size={15} />{t('admin.coverage')}</p>
        <section className="admin-panel admin-panel--chart"><div className="admin-panel__heading"><div><p>{t('admin.engagement')}</p><h2>{t('admin.dailyActive')}</h2></div><span>{t('admin.consentedPlayers')}</span></div><TrendChart rows={dashboard.daily_players} t={t} /></section>
        <div className="admin-panel-grid"><section className="admin-panel"><div className="admin-panel__heading"><div><p>{t('admin.gameMode')}</p><h2>{t('admin.dailyChallenge')}</h2></div></div><StatList values={dashboard.daily} t={t} /></section><section className="admin-panel"><div className="admin-panel__heading"><div><p>{t('admin.learning')}</p><h2>{t('admin.training')}</h2></div></div><StatList values={dashboard.training} t={t} /></section><section className="admin-panel"><div className="admin-panel__heading"><div><p>{t('admin.discovery')}</p><h2>{t('admin.modeAdoption')}</h2></div></div><StatList values={dashboard.modes} t={t} /></section></div>
        <section className="admin-panel admin-accounts"><div className="admin-panel__heading admin-panel__heading--accounts"><div><p>{t('admin.directory')}</p><h2>{t('admin.accounts')}</h2></div><span>{t('admin.total', { count: accounts?.total ?? 0 })}</span></div>
          <div className="admin-table-tools"><label><Search size={17} /><span className="sr-only">{t('admin.searchUsers')}</span><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder={t('admin.searchUsers')} /></label><select value={sort} onChange={(event) => setSort(event.target.value)} aria-label={t('admin.sortAccounts')}><option value="last_active">{t('admin.lastActive')}</option><option value="registered">{t('admin.registrationDate')}</option><option value="active_days">{t('admin.activeDays')}</option><option value="daily_completions">{t('admin.dailyCompletions')}</option><option value="training_attempts">{t('admin.trainingAttempts')}</option></select></div>
          <div className="admin-table-scroll"><table><thead><tr><th>{t('admin.account')}</th><th>{t('admin.registered')}</th><th>{t('admin.lastActive')}</th><th>{t('admin.activeDays')}</th><th>{t('admin.dailyCompletions')}</th><th>{t('admin.trainingAttempts')}</th></tr></thead><tbody>{accounts?.items.map((account) => <tr key={account.id}><td><strong>{account.username}</strong>{account.is_admin ? <small>{t('admin.admin')}</small> : null}</td><td>{new Date(account.registered).toLocaleDateString(activeLanguage())}</td><td>{new Date(account.last_active).toLocaleDateString(activeLanguage())}</td><td>{account.active_days}</td><td>{account.daily_completions}</td><td>{account.training_attempts}</td></tr>)}</tbody></table></div>
          <div className="admin-pagination"><span>{t('admin.page', { page })}</span><button type="button" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>{t('admin.previous')}</button><button type="button" disabled={!accounts || page * accounts.page_size >= accounts.total} onClick={() => setPage((value) => value + 1)}>{t('admin.next')}</button></div>
        </section>
      </> : loading && !error ? <div className="admin-loading"><RefreshCw className="admin-spin" /><span>{t('admin.loading')}</span></div> : null}
    </div>
  </main>
}
