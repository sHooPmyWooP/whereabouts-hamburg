# Server-authoritative guessing with split anonymous/account game state

The game is faithful to whereabouts.earth: a Guess is checked against the answers and the client must never learn which District a Pin is until it is solved. We therefore keep answer-checking on the server (the client POSTs each Guess and gets back solved/miss + distance) and, crucially, draw **no District boundaries on the map during play** — otherwise the client could point-in-polygon locally and the server "authority" would be theater. Boundaries are revealed only for solved Pins or at the end.

Game *progress* (which Pins are solved, remaining Guess Budget) is stored differently per identity: anonymous Players keep it in the browser (localStorage), logged-in Players get a server-side `game_daily_districts` row that becomes History and whose Guesses are recorded for stats.

## Considered Options

- **Fully client-side play** (ship answers + polygons, client runs everything, POST only the final result). Rejected: trivially cheatable and it leaks the answers, which kills the core mechanic's integrity.
- **Server-authoritative, all state server-side** (persist a game row for anonymous Players too, keyed by an opaque cookie). Rejected for today: extra write path and GC burden for throwaway anonymous games that have no History or Leaderboard stake.

## Consequences

- Answer integrity holds for everyone; only the throwaway progress counter is client-trusted for anonymous Players, who can at worst cheat themselves (no History, no Leaderboard).
- Individual Guesses and stats are an accounts-only feature, since `guess` hangs off the logged-in `game_daily_districts` row.
- The autocomplete list of all ~104 Stadtteil names is necessarily public; knowing the names exist is not the same as knowing which Pin is which.
