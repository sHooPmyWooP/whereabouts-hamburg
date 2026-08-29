# PRD: Hamburg Whereabouts (Daily Districts)

Domain language: [../CONTEXT.md](../CONTEXT.md). Architecture decision: [adr/0001-server-authoritative-guessing.md](./adr/0001-server-authoritative-guessing.md). Source plan: [../Task 1/PLAN.md](../Task%201/PLAN.md).

## Problem Statement

People new to Hamburg (and even long-time residents) don't have a good mental map of the city's ~104 Stadtteile. There's no low-friction, repeatable way to learn or test where a district actually is. Existing tools like whereabouts.earth do this for countries, but nothing does it for Hamburg at the district level.

## Solution

A daily geography guessing game, faithful to whereabouts.earth/daily but scoped to Hamburg's Stadtteile. Each day presents the same 5 Pins dropped on a map of Hamburg. The player names districts by typing (with autocomplete), spending from a shared budget of 10 Guesses. Guesses are global (a correct name solves whichever unsolved Pin it matches), and misses report how many kilometers off they were. Anyone can play anonymously in seconds; players who want their History saved can create an account. Same puzzle for everyone each day makes results comparable and shareable.

## User Stories

1. As a newcomer to Hamburg, I want to open the app and immediately understand what it does, so that I know why I'd play.
2. As a first-time visitor, I want to start playing with a single click and no sign-up, so that I face no friction.
3. As a player, I want to see a dark, calm start screen with the title and a one-line explanation, so that the game feels approachable.
4. As a player, I want to see today's date and that it's "5 pins in Hamburg", so that I know the scope of the daily.
5. As a player, I want to press Play and land on a map of Hamburg with the 5 Pins visible at once, so that I can tackle them in any order.
6. As a player, I want the map to show no district borders during play, so that the challenge isn't given away.
7. As a player, I want to type a district name into an input with autocomplete over all Stadtteil names, so that I don't have to guess exact spelling. Suggestions open after the first character; typing never submits by itself. Enter submits the sole remaining suggestion or the keyboard-selected suggestion, while mouse/touch selection submits the chosen entry directly. The input regains focus after each Guess.
8. As a player, I want my guess checked against every unsolved Pin at once, so that a correct name always counts even if I wasn't aiming at that Pin.
9. As a player, when I name a district correctly, I want the matching Pin to be marked solved and its boundary revealed, so that I get clear positive feedback.
10. As a player, when I guess wrong, I want to see the distance in kilometers to the nearest unsolved Pin and the guessed District boundary on the map, so that I learn how close I was. Near misses under 5 km are orange; misses at least 5 km away are red.
11. As a player, I want each guess (right or wrong) to spend from a shared budget of 10, so that guessing has stakes.
12. As a player, I want to always see how many guesses I have left, so that I can pace myself.
13. As a player, I want the game to end when all Pins are solved or my budget hits 0, so that there's a clear finish.
14. As a player, at the end I want all remaining answers revealed on the map, so that I learn the districts I missed.
15. As a player, I want an end screen summarizing how many Pins I solved and how many guesses I spent, so that I can judge my performance.
16. As a player, I want to keep seeing today's finished result and the next Daily Challenge time, so that one scored result is preserved per day.
17. As a returning anonymous player, I want my in-progress or finished game for today to survive a page refresh, so that I don't lose progress.
18. As a privacy-minded player, I want to play without creating an account, so that I share no personal data.
19. As a committed player, I want to create an account with a username and password, so that my History is saved across sessions and devices.
20. As a registered player, I want to log in, so that my saved History is loaded.
21. As a registered player, I want to log out, so that I can leave a shared device safely.
22. As a registered player, I want today's daily to resume from my saved server-side state when I log in, so that I continue where I left off.
23. As a registered player, I want to view my History of past dailies (Pins solved, Guesses spent per day), so that I can track improvement.
24. As a registered player, I want to delete my account and its data, so that I retain control over my information.
25. As any player, I want the answers to never be exposed by the app before I solve a Pin, so that the game can't be trivially cheated.
26. As a player, I want the same 5 Pins as everyone else on a given day, so that scores are comparable.
27. As a mobile user, I want the map, input, and budget to be usable on a small screen, so that I can play on my phone.
28. As a player, I want the autocomplete to tolerate partial input and match district names, so that typing is fast.
29. As a player, I want a guess for a district I've already used or that can't match to give sensible feedback, so that I'm not confused.
30. As a returning player, I want to be prevented from re-playing a day I already finished (or see my finished result), so that the daily stays a daily.
31. As a player, I want a newest-first list of my past Guesses and their result or distance, so that I can follow my reasoning during the Daily Challenge.

## Implementation Decisions

### Product contract refinements

- A Daily Challenge date is the calendar date in `Europe/Berlin`. The backend is the source of truth for the current date; the frontend displays the date returned by `/api/daily`.
- Each Player gets one scored attempt per date. Opening a completed Daily Challenge returns its finished result; there is no reset or scored "Play again" action. A separate practice mode is out of scope.
- Accounts and History are core scope, not mock authentication. Passwords use Argon2 with a per-hash salt. A signed, HTTP-only, `SameSite=Lax` cookie holds only the Account id; every authenticated request reloads that Account from Postgres.
- Anonymous progress remains client-trusted as accepted by ADR 0001. The server validates request shape and answer correctness, but an anonymous Player can alter their own local budget or solved indices. Anonymous results never enter History or future rankings.
- Anonymous localStorage is namespaced by challenge date and stores `{budget_remaining, solved_pins, missed_districts, guess_history, status}`. Solved and missed District entries retain only boundaries already earned through Guesses, so refresh restores the map and newest-first Guess History without another answer-bearing request. Data from a different date is ignored.
- Autocomplete suggestions contain Stadtteil names only. Bezirk names are not suggestion labels or search aliases; Bezirke are reserved for a separate future game mode.
- The mobile game view prioritizes the map and Guess input: repeated heading copy and the map key are hidden, Pin progress is compact, and Guess History scrolls without a footer overlay.
- Usernames are trimmed, 3-32 characters, and compared case-insensitively while preserving their entered display case. Passwords are 8-128 characters. Duplicate registration returns `409`; invalid credentials return `401` without revealing whether the username exists.

**Architecture is server-authoritative for answer-checking** (see ADR 0001). The client never receives which District a Pin belongs to, nor the boundary polygons, until a Pin is solved or the Challenge ends. No district borders are drawn on the map during play.

**Deep, pure-logic modules (no I/O):**

- **ChallengeGenerator** — `generate(date) -> Challenge` producing 5 distinct Districts and a stable Pin point inside each, deterministically seeded by the calendar date. Pin placement uses rejection sampling within each District polygon's bounding box. Same date always yields the same Challenge; not persisted.
- **Geometry** — wraps Shapely and the metric projection (EPSG:25832 / UTM 32N). Interface: `contains(district, point) -> bool`, `distance_km(district, point) -> float` (nearest point on the District boundary to the point), `random_point_in(district, rng) -> point`. Encapsulates GeoJSON loading, projection, and all geo math behind a small stable interface.
- **GuessEvaluator** — `evaluate(challenge, guessed_district, solved_pins) -> {correct, solved_pin_index?, distance_km?}`. Encodes the Global Guess rule (match against all unsolved Pins) and, on a miss, distance to the nearest unsolved Pin.

**I/O modules (thin wrappers):**

- **DistrictRepository** — seeds/loads Stadtteil reference data (`name`, `bezirk`, `boundary`) from a bundled GeoJSON file at startup.
- **GameStore** — persistence for logged-in games and guesses.
- **AuthService** — register/login, salted password hashing (argon2 or bcrypt, per-hash salt), session cookies.
- **API routers** (FastAPI) — thin glue.
- **Frontend** — MapView (base map + Pins, solved and missed boundaries), AutocompleteInput, newest-first Guess History, a game-state hook, and a localStorage adapter for anonymous progress.

**Schema:**

- `district`: `id` PK, `name` text unique, `bezirk` text, `boundary` GeoJSON text (server-only).
- `account`: `id` PK, `username` text unique, `password_hash` text (salted), `created_at`.
- `game_daily_districts`: `id` PK, `account_id` FK, `challenge_date` date (unique with `account_id`), `budget_remaining` int, `solved_pins` json, `status` (in_progress|finished), `finished_at` nullable.
- `guess`: `id` PK, `game_id` FK, `guessed_district_id` FK, `was_correct` bool, `solved_pin_index` int nullable, `distance_km` float nullable, `created_at`.
- History is the set of finished `game_daily_districts` rows for an account, not a separate table.

**API contract:**

- `GET /api/districts` -> `[{id, name, bezirk}]` (autocomplete; no boundaries).
- `GET /api/daily` -> `{date, pins:[{index, lat, lng}], initial_budget, budget_remaining, solved_pins:[{index, district_name, boundary}], status}`. For anonymous Players, `budget_remaining`, `solved_pins`, and `status` start at their initial values and the browser overlays its local state. For Accounts, these fields come from Postgres. Unsolved entries never include a District id, name, or boundary.
- `POST /api/daily/guess` request -> `{challenge_date, guessed_district_id, anonymous_state?}` where `anonymous_state` is `{budget_remaining, solved_pin_indices}` and is required only without an Account cookie. The server rejects a non-current `challenge_date`, an exhausted/finished state, out-of-range indices, duplicate indices, and unknown District ids with a clear 4xx response. Account requests ignore `anonymous_state` and use the row locked in Postgres.
- `POST /api/daily/guess` response -> `{correct, solved_pin_index, distance_km, missed_district, budget_remaining, status, reveals}`. `solved_pin_index` is nullable on a miss, `distance_km` and `missed_district` are nullable on a correct Guess, and a miss returns the earned `{district_id, district_name, boundary, distance_km}` for the guessed District. `reveals` contains the newly solved Pin or every still-hidden Pin when the Challenge finishes. Each solved reveal is `{index, district_name, boundary}`. Every accepted Guess spends one budget point, including correct and repeated/already-solved District Guesses.
- `POST /api/auth/register` -> `201` with `{id, username}` and a session cookie. `POST /api/auth/login` -> `200` with the same shape and cookie. Both accept `{username, password}`.
- `POST /api/auth/logout` -> `204` and clears the session cookie.
- `DELETE /api/account` -> `204`, deletes the authenticated Account and dependent rows, and clears the cookie.
- `GET /api/history` -> `[{date, pins_solved, guesses_spent, status}]`, newest first; Accounts only, otherwise `401`.
- Validation errors use FastAPI's `422` response. Domain conflicts use `409`, missing authentication uses `401`, and a request for a Daily Challenge other than the current date uses `400`.

### Persistence and startup

- Use SQLAlchemy 2 declarative models and Alembic migrations. Do not rely on `create_all` once the first migration exists.
- Store District boundaries as Postgres `JSONB`, still without PostGIS. Add database checks for budget range and status values, a unique constraint on `(account_id, challenge_date)`, and cascading deletion from Account to Game to Guess.
- Enforce case-insensitive username uniqueness with a unique index on `lower(username)`.
- Seed Districts idempotently from `data/hamburg-stadtteile.geojson`, keyed by unique `name`. Startup must fail clearly if the file is missing, malformed, or no longer contains 104 unique Districts.

### Deterministic generation

- Derive the PRNG seed from the SHA-256 digest of the ISO date plus a version string, rather than process-randomized `hash()`. Sort Districts by stable name before selection.
- Keep the generation version constant after launch so dependency or ordering changes cannot silently replace the same date's Daily Challenge. A deliberate algorithm change increments the version.
- Put a bounded attempt count around rejection sampling and fail clearly (or use a deterministic interior-point fallback) so malformed geometry cannot hang a request.

**Key interactions:**

- Anonymous progress, earned boundaries, and Guess History live in the browser (localStorage); the server stays stateless for anonymous play but still authoritative on correctness.
- Distances are computed in EPSG:25832, not raw lat/lng degrees.
- Table name is type-scoped (`game_daily_districts`) to leave room for future daily game types.

## Testing Decisions

**What makes a good test here:** exercise external behavior through a module's public interface, not its internals. Assert on returned values (is a guess correct, which Pin index solved, distance rounded to the expected km), never on Shapely internals, RNG internals, or private helpers.

**Modules under test (the three pure-core modules):**

- **ChallengeGenerator** — determinism (same date -> identical Challenge), 5 distinct Districts, every Pin point lies inside its District (verified via Geometry), and different dates generally differ.
- **Geometry** — `contains` true for interior points and false for exterior points; `distance_km` is 0 (or near 0) for a point inside the District and grows for farther Districts; `random_point_in` always returns a point that `contains` accepts; distances are in kilometers via the metric projection, spot-checked against a hand-computed value.
- **GuessEvaluator** — a correct name solves the matching unsolved Pin and returns its index; a name matching an already-solved Pin does not re-solve; a miss returns distance to the nearest unsolved Pin; the Global Guess rule holds (a name matching a Pin the player wasn't focused on still solves it).

**Contract and security-boundary tests:**

- `GET /api/daily` never returns answer District ids, names, or boundaries for unsolved Pins.
- A correct Guess reveals exactly the solved Pin; the final Guess or exhausted budget reveals every remaining Pin.
- A miss reveals only the guessed District boundary and distance, while `/api/daily` remains free of boundaries. The UI renders misses under 5 km orange and misses at least 5 km red.
- Every accepted Guess decrements the budget, and an Account cannot exceed the budget under concurrent requests.
- Anonymous state validation rejects malformed indices and exhausted state; Account requests cannot override database state with an anonymous payload.
- Registration hashes passwords, login accepts valid credentials and rejects invalid ones, authenticated History is Account-scoped, and Account deletion cascades.
- The District seed is idempotent and contains exactly the 104 unique names from the bundled normalized GeoJSON.

**Prior art:** none yet (greenfield repo). These become the reference pattern for pure-logic unit tests: construct fixed inputs (a fixed date, a small set of fake/real District polygons), call the interface, assert on the result.

Thin router delegation does not need a test per line, but the API secrecy, transaction/budget, persistence, and authentication contracts above do require integration tests because they enforce core game integrity.

## Out of Scope

- Leaderboard / public ranking (deferred to Task 4; accounts-only when built).
- Aggregate stats endpoint (`/api/stats`).
- Real auth hardening beyond salted password hashing (rate limiting, email verification, password reset, OAuth).
- Extended game types (transit lines, stations, streets) — only Daily Districts ships now.
- PostGIS — geometry runs in Python via Shapely.
- Curated or hand-authored dailies — generation is deterministic and on the fly.
- Server-side storage of anonymous games or anonymous guess history.

## Further Notes

- The autocomplete list of all ~104 Stadtteil names is necessarily public; knowing the names exist does not reveal which Pin is which.
- Stadtteil boundary GeoJSON should come from Hamburg's open-data portal or OpenStreetMap and be bundled with the app; it is reference data seeded once.
- Guess Budget (10) and Pin count (5) are starting values and should be easy to tune.
- The `game_daily_districts` unique constraint on `(account_id, challenge_date)` enforces one game per account per day, backing user story 30.
