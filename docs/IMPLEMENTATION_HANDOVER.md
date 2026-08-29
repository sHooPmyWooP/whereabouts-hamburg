# Hamburg Whereabouts: Implementation Handover

This document describes the implemented state of the PRD through authenticated Daily Challenge persistence and seeded party mode. The product contract remains in [PRD.md](./PRD.md), with domain terms in [../CONTEXT.md](../CONTEXT.md) and the server-authoritative decision in [adr/0001-server-authoritative-guessing.md](./adr/0001-server-authoritative-guessing.md).

## Current Status

The anonymous Daily Challenge and shareable seeded rounds are playable end to end on desktop and mobile. Five deterministic Pins are shown over an unannotated Hamburg satellite map. A Player can search Stadtteil names, submit Global Guesses, receive solved or distance feedback, exhaust the shared Guess Budget, see all answers at the end, and resume the same browser-local state after a refresh.

PostgreSQL connectivity, Account registration, password login, and authenticated Daily Challenge persistence are implemented. A Player can create an Account with a case-insensitively unique username and Argon2-hashed password, log in from the homepage, and have that identity restored after refresh through a protected cookie. Signed-in progress and completed results are restored from PostgreSQL, and a finished Daily Challenge cannot be replayed while signed in. District seeding, cross-date History, logout, account deletion, and password recovery remain to be implemented.

### Account registration

- SQLAlchemy owns short-lived database sessions through a shared dependency, and Alembic owns schema changes.
- The initial migration creates the `account` table and a unique index on `lower(username)`.
- Usernames are trimmed, 3-32 characters, case-preserving, and case-insensitively unique.
- Passwords are 8-128 characters and stored only as Argon2 hashes.
- Successful registration returns the public Account fields and sets a signed HTTP-only, `SameSite=Lax` cookie containing only the Account id.
- Existing Accounts can log in with a case-insensitive username match and their password. Unknown usernames and wrong passwords return the same generic `401` response.
- `/api/auth/me` validates the time-limited signature and reloads the Account from PostgreSQL on every request.
- The start screen exposes accessible login and registration dialogs and restores the signed-in username after refresh.
- Registration does not import, clear, or synchronize anonymous Daily Challenge progress.

### Authenticated Daily persistence

- Migration `0002_create_daily_games` adds one `game_daily_districts` row per Account and challenge date plus cascade-owned `guess` rows.
- `/api/daily` resolves the optional signed session. Anonymous Players receive fresh server defaults, while Accounts receive their stored budget, status, earned reveals, missed Districts, and ordered Guess History.
- `/api/daily/guess` ignores browser-supplied progress for Accounts, locks the Account Game row, evaluates the Guess, and commits the Game and Guess atomically.
- The unique Account/date constraint prevents duplicate Daily Games, while the row lock and finished-state check prevent budget races and replay.
- The frontend refetches `/api/daily` after login or registration and maps Account state directly into the existing game/result UI.
- Authenticated progress is not written to localStorage. Anonymous progress remains independent and is not imported when an Account session begins.

## Implemented PRD Scope

### Daily Challenge core

- The backend uses the `Europe/Berlin` calendar date.
- `ChallengeGenerator` derives a stable SHA-256 seed from the date and generation version.
- Five distinct Stadtteile are selected from the bundled 104-feature GeoJSON.
- After District selection, each Pin is placed using bounded rejection sampling inside a safe metric inset of its District.
- The inset is 60% of the District's maximum interior radius, bounded to 200-750 meters. Compact Districts retain a strict 200-meter minimum while larger Districts keep Pins visually farther from their borders.
- Safe Pin areas are precomputed for all 104 bundled Districts; generation fails explicitly rather than weakening the rule if future source data violates that invariant.
- Challenge responses expose the generation version, which namespaces browser persistence so old reveals cannot be restored against Pins from a changed algorithm.
- Geometry is loaded in WGS84 and projected to EPSG:25832 for metric calculations.
- The same date produces the same ordered Pins for every Player.

### Server-authoritative Guessing

- `/api/daily` returns Pin coordinates but no answer ids, names, or boundaries.
- A Guess is evaluated against every unsolved Pin (Global Guess).
- Every accepted correct or incorrect Guess spends one point from the shared budget of 10.
- A correct Guess reveals the matching Pin name and boundary.
- A miss returns the nearest-unsolved-Pin distance and only the guessed District boundary.
- Misses under 5 km render orange; misses at least 5 km away render red.
- Finishing by solving all Pins or exhausting the budget reveals every remaining answer.
- Malformed anonymous state, duplicate/out-of-range solved indices, unknown Districts, and non-current dates are rejected.
- Signed-in Guesses use only PostgreSQL state; browser-provided anonymous state is ignored.
- Finished signed-in Games reject additional Guesses with `409 Conflict`.

### Seeded party mode

- **Create your own** generates a URL-safe random seed and opens `?seed=<seed>` with all five numbered Pins visible as a pre-game preview.
- A custom phrase is normalized to lowercase ASCII letters, digits, underscores, and hyphens and can be previewed before play.
- Opening the same seed URL always produces the same ordered Pins and coordinates.
- Seed generation is versioned and namespaced separately from Daily generation, so custom seeds do not change the Daily sequence.
- A seeded start screen renders a QR code for the canonical invite URL, supports clipboard copy, uses the native Web Share API where available, and falls back to copying where it is not.
- The creator can randomize another round or return to the Daily Challenge.
- Seeded Guess evaluation uses dedicated stateless endpoints while reusing the same server-authoritative geometry logic.
- Seeds are limited to 3-64 ASCII letters, digits, underscores, or hyphens.
- No seeded challenge or Player state is stored in PostgreSQL.

### Anonymous frontend

- Start, game, and finished-result states are implemented.
- The map uses Esri World Imagery without a reference/label layer, preserving rivers, lakes, harbor, terrain, and urban geography without written place hints.
- District boundaries are absent before they are earned by a Guess.
- The controlled Stadtteil combobox:
  - stays closed while the focused field is empty;
  - filters after the first character;
  - contains Stadtteil names only, without Bezirk labels;
  - never submits from typing alone;
  - submits the sole result with Enter;
  - supports arrow-key selection plus Enter;
  - submits direct mouse/touch selection; and
  - restores input focus after each Guess.
- Solved Pins and boundaries are green; near misses are orange; far misses are red; unsolved final reveals are amber.
- The map refits around Pins and all earned boundaries while reserving the desktop control rail.
- A newest-first Guess History shows each District and its solved Pin or miss distance.
- Guess History uses the available result rail height without a nested scrollbar.
- Players can give up with a two-step confirmation; the server reveals all answers without consuming the unused Guess Budget.
- Finished rounds offer a fresh seeded game or navigation back to the current round's start screen.
- Mobile play prioritizes the map and input, uses compact Pin progress and budget controls, and bounds Guess History without a footer overlay.

### Anonymous persistence

- Date- or seed-scoped `localStorage` stores remaining budget, solved Pin indices, earned solved boundaries, missed District boundaries, Guess History, and status.
- Refreshing restores an in-progress or finished Daily or seeded Challenge.
- Progress for different seeds and the Daily Challenge is isolated by distinct storage keys.
- Anonymous state is intentionally client-trusted under ADR 0001. It cannot affect account History or a future Leaderboard.

## Implemented API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | FastAPI process health |
| `GET` | `/health/database` | PostgreSQL connectivity probe |
| `GET` | `/api/districts` | Public autocomplete metadata for 104 Stadtteile |
| `GET` | `/api/daily` | Public Pins and anonymous defaults or restored Account progress |
| `POST` | `/api/daily/guess` | Evaluate anonymous state or transactionally update an Account Game |
| `POST` | `/api/daily/give-up` | Finish the anonymous Daily round and reveal all answers |
| `GET` | `/api/challenges/{seed}` | Public Pin coordinates and initial state for a deterministic seed |
| `POST` | `/api/challenges/{seed}/guess` | Server-side anonymous Guess evaluation for a seeded round |
| `POST` | `/api/challenges/{seed}/give-up` | Finish a seeded round and reveal all answers |
| `POST` | `/api/auth/register` | Create an Account, hash its password, and establish a session |
| `POST` | `/api/auth/login` | Verify an existing Account and establish a session |
| `GET` | `/api/auth/me` | Restore the Account represented by the signed session cookie |

The current API schemas live in [../backend/main.py](../backend/main.py). Pure challenge, geometry, and Guess logic lives in [../backend/game.py](../backend/game.py).

## Main Frontend Files

- [../frontend/src/App.tsx](../frontend/src/App.tsx): screen state, controlled autocomplete, Guess requests, localStorage, feedback, and Guess History.
- [../frontend/src/MapView.tsx](../frontend/src/MapView.tsx): Leaflet map, unannotated imagery, Pins, boundaries, and responsive fitting.
- [../frontend/src/App.css](../frontend/src/App.css): desktop and mobile layouts and visual states.
- [../frontend/src/api.ts](../frontend/src/api.ts): typed API fetch helper with credential support for future cookie sessions.

`qrcode.react` renders the invite QR code as an accessible inline SVG; no external QR service receives the invite URL.

## Verification Completed

- Backend API contracts cover deterministic/no-leak Daily and seeded responses, seed isolation and validation, correct Global Guesses, missed-Guess distance and boundary feedback, final reveals, invalid anonymous state, Account validation, Argon2 storage, duplicate handling, signed-session restoration, authenticated progress restoration, and finished-Game replay rejection.
- Ruff, ESLint, and the TypeScript/Vite production build pass.
- Integrated browser tooling was used instead of adding a project Playwright dependency.
- Desktop and `390x844` mobile checks cover map loading, Pin framing, no horizontal overflow, autocomplete keyboard/mouse behavior, retained focus, orange/red/green boundaries, Guess History, finish behavior, refresh persistence, seeded URL creation, custom phrase normalization, five-Pin preview, QR rendering, share fallback, and seeded Guess submission.
- Live PostgreSQL/browser validation covers Account registration, ten persisted Guesses, restored `0/5` and `10/10` results with ten History rows, absence of the Guess input after completion, and `409` replay rejection.

Run the repeatable code checks from the repository root:

```bash
cd backend
uv run pytest -q
uv run ruff check .
cd ../frontend
npm run lint
npm run build
```

## Remaining PRD Scope

1. Add a persistent `district` reference table and seed the 104 rows idempotently from normalized GeoJSON. Runtime District data currently remains file-backed.
2. Implement a cross-date Account History screen and API; today's in-progress or finished result already restores across sessions.
3. Implement logout, account deletion, and password recovery using the existing Account/session foundation.
4. Add PostgreSQL integration tests for migration round trips, District seeding, and concurrent Account/game writes.
5. Add rate limiting and automated off-host PostgreSQL backups. Production static-file serving and the homelab Docker Compose deployment are configured; TLS termination belongs to the homelab reverse proxy.

## Known Constraints

- The satellite basemap requires network access to `server.arcgisonline.com` and is subject to Esri service availability and usage terms.
- Anonymous Players can alter their own localStorage state. This is accepted for the prototype because anonymous results are not server-persisted or ranked.
- `DATABASE_URL` and a non-placeholder `SESSION_SECRET` of at least 32 characters must be configured when FastAPI imports the application. `SESSION_COOKIE_SECURE` must be `true` in an HTTPS deployment and may be `false` only for local HTTP development.
- The production container applies Alembic migrations before starting the API. Authenticated gameplay requires the current schema; anonymous gameplay remains file-backed and client-persisted.
- There is no repository-level browser-test dependency or command. Visual checks use the integrated VS Code browser/Playwright tooling.

## Recommended Next Slice

Add a cross-date Account History endpoint and view using the persisted Game and Guess rows. In parallel, seed District reference data and replace catalog ids with database-backed foreign keys before adding ranked or long-term historical features.