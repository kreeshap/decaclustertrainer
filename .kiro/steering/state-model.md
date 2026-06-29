---
inclusion: manual
---

# User Preference State Model

## What this document is

A precise record of what was intentionally deferred in the event/cluster state system.
Read this before touching UserPrefs, localStorage, or event/cluster selection logic.

---

## Current architecture

**Single source of truth:** Supabase `profiles` table (`default_event`, `default_cluster`)

**Cache:** `localStorage` via `UserPrefs` in `common.js`

**Write rule:** Only `UserPrefs.setEvent()` writes `ct_selected_event` and `ct_selected_cluster`.
No other file is allowed to write these keys directly.

**Read rule:** All reads go through `UserPrefs.getEvent()` / `UserPrefs.getCluster()`.

**Hydration rule:** `UserPrefs.hydrateFromProfile(user)` syncs cache from an already-confirmed
server value. It does not hit the server. It does not overwrite cache with empty.

---

## Write paths (all routes through UserPrefs.setEvent)

| Trigger | File | Method |
|---------|------|--------|
| User picks event on opening screen | opening.js | `UserPrefs.setEvent()` |
| User saves event in settings | settings.js | `UserPrefs.setEvent()` |
| User clicks KPI search result | learn_extra.js | `UserPrefs.setEvent()` |
| Login / page load hydration | auth.js, learn.js, settings.js | `UserPrefs.hydrateFromProfile()` |

---

## What was resolved in the June 2026 refactor

- Multiple files writing `ct_selected_event` independently → eliminated
- `[object Object]` in event dropdowns (schema mismatch: events changed from strings to `{name, type}` objects) → fixed
- `default_event` missing from profile serialization and save routes → fixed
- `saveEventSelection` only saving `default_cluster`, not `default_event` → fixed

---

## Known remaining issues (intentionally deferred)

### 1. Navigation happens before server confirmation

`UserPrefs.setEvent()` awaits the server before writing cache. But the UI navigates
immediately (opening screen advances to next phase before the fetch resolves).
This means the immediate next page load may read stale cache if the server is slow.

**Shape of the risk:** user selects event → navigates to learn → learn reads old event.
**Frequency:** only under slow network. Self-corrects on next hydration.
**Not fixed because:** fixing it requires blocking navigation on network, which degrades UX.
**Fix when:** this produces confirmed user-reported confusion.

### 2. Hydration timing is decentralized

Each page independently decides when to call `hydrateFromProfile`. There is no shared
event or lifecycle hook that triggers re-hydration consistently. Pages that don't call
`/auth/me` on load will read from cache without refreshing.

**Current pages that hydrate:** learn.js (on init), settings.js (on loadSettings)
**Current pages that do not hydrate:** dashboard, opening (reads cache directly)

**Fix when:** a page shows wrong state and the root cause is stale cache post-hydration.

### 3. No conflict resolution rule

There is no defined rule for what happens when server state and cache disagree.

**Current behavior:** server wins on next hydration, but timing is undefined.
**Implicit assumption:** server is always more recent than cache. This is true as long as
`setEvent()` always succeeds before cache is written. If the server call fails silently,
cache could drift.

**The rule that should be written:**
> Server state always wins. If hydration returns a non-empty value, it replaces cache.
> If hydration returns empty, cache is left alone.

`hydrateFromProfile` currently implements this rule but it is not documented as a contract.

### 4. No cache expiry or invalidation

`ct_selected_event` persists in localStorage indefinitely. There is no TTL, no version,
no mechanism to detect that the server value changed since the cache was written.

**Risk:** user changes event on device A, device B still shows old event until it
re-hydrates from server. Since hydration only happens on page load (for pages that do it),
a device that doesn't reload won't see the change.

**Fix when:** cross-device sync becomes a stated product requirement.

### 5. Empty state fallback is undefined

If both server and cache have no event, `UserPrefs.getEvent()` returns `''`.
Each page handles this differently:
- learn.js: shows "No event found — go through the opening screen first"
- settings.js: dropdowns show placeholder options
- opening.js: welcome-back shows "Good to see you again," (no event name)

There is no shared empty-state handler. This is acceptable for now but will become
inconsistent as more pages read event state.

---

## What this is not

This is a **write-path consolidation refactor**. It is not a state correctness guarantee.

It reduced write chaos and made failures diagnosable. It did not eliminate timing gaps,
define state lifecycle rules, or implement a conflict resolution strategy.

---

## The question that must be answered before the next refactor

> What is allowed to happen when server state and cached state disagree?

Until that rule is written and enforced uniformly, the system is stable-looking, not stable.

---

## Suggested next step (when time allows)

Define a `UserPrefs.refresh()` method that:
1. Hits `/auth/me`
2. Calls `hydrateFromProfile` with the result
3. Returns the confirmed state

Then replace per-page hydration logic with a single call to `UserPrefs.refresh()` at
the start of any page that needs current event state. That moves the trigger logic
into one place and makes hydration timing consistent.
