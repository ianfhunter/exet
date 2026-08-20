# Before/after test with Lufz (change #1)

Change #1 replaces the weak per-word trial in `findDeadendsByClue()` with
`refineLightChoices()` — the same propagation used in the grid sweep.

## Automated test (three-part suite)

Open [`exet-test-deadend-lufz.html`](../exet-test-deadend-lufz.html):

| Part | What it tests | Pass means |
|------|---------------|------------|
| **1 — Toy lexicon** | CART on 12-word dict | Weak KEEP, strong REJECT |
| **2 — Lufz, no grid sweep** | Rows 0–2 (`skipGridSweep` equivalent) | ≥1 weak-only word (e.g. WERE) |
| **3 — Lufz, grid sweep first** | Normal live-editor path | **0** gaps (expected) |

Part 3 showing 0 gaps is correct for the 4×4 X grid — grid sweep already applies
`refineLightChoices` globally before clue sweep runs.

## Live editor A/B (sidebar)

Use URL params on [`exet.html`](../exet.html):

| Mode | URL |
|------|-----|
| **Before** (weak) | `exet.html?clueDeadend=weak&skipGridSweep=1` |
| **After** (strong) | `exet.html?clueDeadend=strong&skipGridSweep=1` |

`skipGridSweep=1` skips the grid refine phase so you are testing **only** the
clue-sweep trial — not the stronger grid sweep that already runs first in
normal editing.

### Manual protocol

1. Open **before** URL, wait for lexicon load.
2. Build or paste your test grid (or use File → New).
3. Select the clue you care about (e.g. `??EN`).
4. Wait until the sweep indicator stops animating (~500 ms per tick).
5. Note:
   - Count in the main suggestions table (`#xet-light-choices`).
   - Words in the purple rejects table (`#xet-light-rejects`).
6. Reload with **after** URL, same grid, same clue.
7. Compare: **after** should move some words from main → purple that **before**
   left in main.

Toggle at runtime (devtools console):

```javascript
exet.strongClueDeadendCheck = false;  // before
exet.strongClueDeadendCheck = true;   // after
exet.skipGridDeadendSweep = true;
exet.resetViability();
```

## What to expect

### WERE on the 4×4 X grid (row 0 across)

WERE forces down col 1 to `E??X`, which has **no** Lufz matches. Two separate
mechanisms apply:

1. **Grid sweep** (`findDeadendsByCell` → `refineLightChoices`) — runs first in
   normal editing. Propagates constraints from down `???X` (46 words) and
   removes WERE from the across list **before clue sweep runs**. This happens in
   **both** before and after modes.

2. **Clue sweep trial** (change #1) — if you isolate it with
   `skipGridSweep=1`, weak trial keeps WERE (down still has >4 cached choices)
   but strong trial rejects it. You won't see this in normal editing because
   grid sweep already removed WERE.

The old automated test skipped step 1 and falsely listed WERE as a gap.

### Other cases

- **OVEN on the ?Z?? grid** — eliminated by grid sweep via down `?VZZ`, not a
  clue-sweep test.
- **CART + toy lexicon** — gap only when grid sweep doesn't catch it and down
  has >4 stale matches.
- **Real Lufz clue-sweep gaps** — thousands exist with `skipGridSweep=1` (Part 2);
  **zero** survive grid sweep on the X grid (Part 3).

## Code

- Toggle: `exet.strongClueDeadendCheck` (default `false` = before; set `true` or use
  `?clueDeadend=strong` for after).
- Skip grid phase: `exet.skipGridDeadendSweep` (URL `skipGridSweep=1`).
- Trial site: `findDeadendsByClue()` in `exet.js`.
