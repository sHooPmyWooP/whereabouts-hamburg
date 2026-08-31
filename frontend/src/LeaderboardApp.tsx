import { useEffect, useState } from 'react'
import { ArrowLeft, RefreshCw } from 'lucide-react'
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

  async function load(date: string, nextOffset = 0) {
    try {
      setError(null)
      setBoard(await apiFetch<Board>(`/api/leaderboard/${date}?offset=${nextOffset}&limit=50`))
      setOffset(nextOffset)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not load standings.') }
  }
  useEffect(() => {
    apiFetch<string[]>('/api/leaderboard/dates').then((items) => {
      setDates(items)
      if (items[0]) { setSelected(items[0]); void load(items[0]) }
    }).catch((reason: unknown) => setError(reason instanceof ApiError && reason.status === 401 ? 'Log in to view your leaderboard history.' : 'Could not load leaderboard history.'))
  }, [])

  return <main className="mode-home">
    <section className="mode-picker leaderboard-page" aria-labelledby="leaderboard-title">
      <button className="panel-secondary-action" type="button" onClick={onHome}><ArrowLeft size={16} /> Back</button>
      <div className="mode-picker__heading"><p className="eyebrow">Daily history</p><h1 id="leaderboard-title">Leaderboard</h1></div>
      {dates.length > 0 ? <label>Challenge date<select value={selected} onChange={(event) => { setSelected(event.target.value); void load(event.target.value) }}>{dates.map((date) => <option key={date} value={date}>{date}</option>)}</select></label> : null}
      {error ? <p className="notice notice--error">{error}</p> : null}
      {board ? <>
        <p><strong>You placed #{board.your_entry.rank} of {board.player_count} players</strong></p>
        <ol className="guess-history">{board.entries.map((entry) => <li className="guess-history__item" key={`${entry.rank}-${entry.username}`}><strong>#{entry.rank} {entry.is_you ? 'You' : entry.username}</strong><small>{entry.pins_solved}/5 · {entry.guesses_used} guesses · {entry.total_missed_distance_km.toFixed(1)} km</small></li>)}</ol>
        <div className="result-actions"><button className="panel-secondary-action" type="button" onClick={() => void load(selected, offset)}> <RefreshCw size={16} /> Refresh standings</button>{offset > 0 ? <button type="button" onClick={() => void load(selected, Math.max(0, offset - 50))}>Previous</button> : null}{offset + 50 < board.player_count ? <button type="button" onClick={() => void load(selected, offset + 50)}>Next</button> : null}</div>
      </> : !error ? <p>Finish a Daily Challenge to see your leaderboard history.</p> : null}
    </section>
  </main>
}
