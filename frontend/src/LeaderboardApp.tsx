import { useEffect, useState } from 'react'
import { ArrowLeft, CalendarDays, MapPin, RefreshCw, Target, Trophy, Users } from 'lucide-react'
import { ApiError, apiFetch } from './api'

type Entry = {
  rank: number
  username: string
  pins_solved: number
  guesses_used: number
  total_missed_distance_km: number
  is_you: boolean
}
type Board = { date: string; player_count: number; entries: Entry[]; context_entries: Entry[]; your_entry: Entry; offset: number; limit: number }

export function LeaderboardApp({ onHome }: { onHome: () => void }) {
  const [dates, setDates] = useState<string[]>([])
  const [selected, setSelected] = useState('')
  const [board, setBoard] = useState<Board | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)

  async function load(date: string, nextOffset = 0) {
    try {
      setLoading(true)
      setError(null)
      setBoard(await apiFetch<Board>(`/api/leaderboard/${date}?offset=${nextOffset}&limit=50`))
      setOffset(nextOffset)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load standings.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    apiFetch<string[]>('/api/leaderboard/dates').then((items) => {
      setDates(items)
      if (items[0]) {
        setSelected(items[0])
        void load(items[0])
      } else {
        setLoading(false)
      }
    }).catch((reason: unknown) => {
      setError(reason instanceof ApiError && reason.status === 401 ? 'Log in to view your leaderboard history.' : 'Could not load leaderboard history.')
      setLoading(false)
    })
  }, [])

  return <main className="leaderboard-page">
    <div className="leaderboard-hero">
      <header className="leaderboard-header">
        <button className="leaderboard-back" type="button" onClick={onHome}><ArrowLeft size={17} /> Back</button>
        <div className="leaderboard-heading">
          <p className="eyebrow">Daily history</p>
          <h1 id="leaderboard-title">Leaderboard</h1>
          <p>See how your Daily Challenge result compares with Hamburg's best.</p>
        </div>
        <button className="leaderboard-refresh" type="button" onClick={() => selected && void load(selected, offset)} disabled={loading || !selected}>
          <RefreshCw size={17} className={loading ? 'leaderboard-spin' : ''} aria-hidden="true" />
          <span>{loading ? 'Refreshing' : 'Refresh'}</span>
        </button>
      </header>
    </div>

    <div className="leaderboard-content" aria-labelledby="leaderboard-title">
      {dates.length > 0 ? <div className="leaderboard-toolbar">
        <div><CalendarDays size={17} aria-hidden="true" /><span>Challenge date</span></div>
        <select aria-label="Challenge date" value={selected} onChange={(event) => { setSelected(event.target.value); void load(event.target.value) }}>
          {dates.map((date) => <option key={date} value={date}>{date}</option>)}
        </select>
      </div> : null}

      {error ? <section className="leaderboard-error" role="alert"><Trophy size={26} /><div><h2>Leaderboard unavailable</h2><p>{error}</p></div></section> : null}

      {board ? <>
        <section className="leaderboard-overview" aria-label="Your result">
          <div className="leaderboard-rank-card">
            <span className="leaderboard-rank-card__icon"><Trophy size={21} aria-hidden="true" /></span>
            <span>Your position</span>
            <strong>#{board.your_entry.rank}</strong>
            <small>of {board.player_count} players</small>
          </div>
          <div className="leaderboard-stat"><span><Users size={17} aria-hidden="true" /></span><div><small>Players</small><strong>{board.player_count}</strong></div></div>
          <div className="leaderboard-stat"><span><Target size={17} aria-hidden="true" /></span><div><small>Pins solved</small><strong>{board.your_entry.pins_solved}<em>/5</em></strong></div></div>
          <div className="leaderboard-stat"><span><RefreshCw size={17} aria-hidden="true" /></span><div><small>Guesses used</small><strong>{board.your_entry.guesses_used}</strong></div></div>
          <div className="leaderboard-stat"><span><MapPin size={17} aria-hidden="true" /></span><div><small>Distance missed</small><strong>{board.your_entry.total_missed_distance_km.toFixed(1)}<em> km</em></strong></div></div>
        </section>

        <section className="leaderboard-panel">
          <div className="leaderboard-panel__heading">
            <div><p>Daily Challenge</p><h2>Standings</h2></div>
            <span>{board.date}</span>
          </div>
          <div className="leaderboard-table-head" aria-hidden="true"><span>Rank</span><span>Player</span><span>Pins</span><span>Guesses</span><span>Distance</span></div>
          <ol className="leaderboard-list" start={offset + 1}>
            {board.entries.map((entry) => <li className={`leaderboard-entry${entry.is_you ? ' leaderboard-entry--you' : ''}`} key={`${entry.rank}-${entry.username}`}>
              <strong className="leaderboard-entry__rank">#{entry.rank}</strong>
              <span className="leaderboard-entry__player"><span>{entry.is_you ? 'You' : entry.username}</span>{entry.is_you ? <small>Your result</small> : null}</span>
              <span data-label="Pins"><strong>{entry.pins_solved}</strong>/5</span>
              <span data-label="Guesses">{entry.guesses_used}</span>
              <span data-label="Distance">{entry.total_missed_distance_km.toFixed(1)} km</span>
            </li>)}
          </ol>
          <div className="leaderboard-pagination">
            <span>Showing {offset + 1}–{Math.min(offset + board.entries.length, board.player_count)} of {board.player_count}</span>
            <button type="button" disabled={offset === 0 || loading} onClick={() => void load(selected, Math.max(0, offset - 50))}>Previous</button>
            <button type="button" disabled={offset + 50 >= board.player_count || loading} onClick={() => void load(selected, offset + 50)}>Next</button>
          </div>
        </section>
      </> : !error && !loading ? <section className="leaderboard-empty"><Trophy size={32} /><h2>No standings yet</h2><p>Finish a Daily Challenge to see your leaderboard history.</p></section> : null}

      {loading && !board && !error ? <div className="leaderboard-loading"><RefreshCw className="leaderboard-spin" /><span>Loading standings</span></div> : null}
    </div>
  </main>
}
