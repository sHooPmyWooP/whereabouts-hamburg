# Hamburg Whereabouts

A daily geography guessing game for the districts of Hamburg, modeled on whereabouts.earth/daily. A pin is dropped on a map inside a Hamburg district and the player names the district. Helps newcomers learn Hamburg and lets locals sharpen what they already know.

## Language

**District**:
One of Hamburg's ~104 official *Stadtteile* (quarters, e.g. Eppendorf, St. Pauli, Blankenese), the unit the game asks the player to identify. Shared reference data with a name and a boundary polygon, identical for all players. Explicitly *not* the 7 coarse Bezirke.
_Avoid_: Area, region, neighborhood, Bezirk, borough

**Bezirk**:
One of Hamburg's 7 administrative boroughs, used to group Districts but never as an answer to a Pin.
_Avoid_: District, Stadtteil, area, region

**Pin**:
A single point dropped on the map inside one District, which the player must name. All Pins of the Daily Challenge are shown on one Hamburg map at once; each is either *unsolved* or *solved*, and solved Pins are recolored.
_Avoid_: Marker, question, location, round

**Guess**:
One named-District answer the player submits. Drawn from a shared budget spent across the whole Daily Challenge, not reset per Pin.
_Avoid_: Answer, attempt

**Guess Budget**:
The total number of Guesses a player may spend across all Pins in a Daily Challenge (start: 10 guesses for 5 Pins).
_Avoid_: Lives, tries limit

**Distance Feedback**:
The kilometer distance reported after a missed Guess, measured from the nearest point on the guessed District's boundary polygon to the nearest unsolved Pin, telling the player how close they were.
_Avoid_: Score, hint

**Global Guess**:
A Guess is matched against *every* unsolved Pin, not just the Pin currently in view. If the named District matches any unsolved Pin, that Pin is solved, regardless of which Pin the player was looking at.
_Avoid_: per-pin answer

**Daily Challenge**:
The fixed set of Pins for a given calendar day, identical for every player that day (start: 5 Pins). Generated deterministically from the calendar date (date-seeded PRNG): the date picks 5 distinct Districts and a stable random Pin point inside each. Computed on the fly, not curated or pre-stored. The canonical product term remains "Daily Challenge" in both English and German; "Daily Districts" is the first game type, with future variants (transit lines, streets) planned, hence type-scoped names like `game_daily_districts`.
_Avoid_: Game, level, quiz, Tages-Challenge

**Player**:
Whoever is playing. Either anonymous (no saved identity) or signed in to an Account.
_Avoid_: User, visitor

**Account**:
An optional, persistent identity a Player creates with a username and password so their play History is saved across sessions. Username is unique.
_Avoid_: Profile, login, user record

**History**:
The record of a signed-in Player's past Daily Challenge results (per day: Pins solved, Guesses spent). Only Accounts have History.
_Avoid_: Log, stats, record

**Game**:
A Player's in-progress or finished attempt at one Daily Challenge: which Pins are solved and how much Guess Budget remains. For logged-in Players it is a server-side row (`game_daily_districts`, server-enforced budget, becomes History when finished); for anonymous Players it lives only in the browser (localStorage). Every Guess is recorded for stats. Either way the server owns and never leaks the answers.
_Avoid_: Session, round, match

**Leaderboard**:
A public ranking of Accounts by Daily Challenge performance. Deferred to Task 4; when built, it is Accounts-only. Anonymous results live only in the browser (localStorage) and never rank.
_Avoid_: Ladder, ranking, scoreboard

## Relationships

- A **Daily Challenge** contains an ordered set of **Pins**
- A **Bezirk** contains multiple **Districts**, and each **District** belongs to exactly one **Bezirk**
- A **Pin** sits inside exactly one **District**
- A **Guess** is evaluated against all unsolved **Pins** in the **Daily Challenge** (Global Guess)
- An **Account** owns one **History**; a **History** has one result per **Daily Challenge** played
- Guess-checking is **server-authoritative**: the server holds the answer Districts and boundary polygons; the client sends a Guess and receives solved/miss + Distance Feedback. The client never learns the answers until a Pin is solved or the Challenge ends.
- **Game** (progress) storage splits by identity: anonymous Players keep progress in the browser (localStorage); logged-in Players have a server-side **Game** row that becomes **History** when finished. Answer-checking stays server-side for both.

## Flagged ambiguities

- The interaction model was contradictory: written notes described a click-the-map mechanic, but the reference (whereabouts.earth) uses a name-the-pin mechanic. **Resolved: name-the-pin.** The player reads a pinned map and types the District name; the map is read-only.
- Guesses are not scoped to a single Pin. **Resolved: Global Guess** — a correct name solves whichever unsolved Pin it matches, even one the player was not aiming at.
- Server-authoritative guessing only holds if the client lacks the boundary polygons. **Resolved:** during play the map shows a base map + Pins with *no* District boundaries drawn; boundaries are revealed only for solved Pins (or at the end).
