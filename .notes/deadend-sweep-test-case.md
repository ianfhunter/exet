# Dead-end sweep test case (change #1)

This documents a **real, reproducible** case where the sidebar dead-end check
(`someClueTurnsNonViable`) keeps a bad word, but `refineLightChoices` correctly
rejects it.

## Grid

4×4, all white cells. Only **X at (3,1)** is given:

```
        col0  col1  col2  col3
row0      ?     ?     ?     ?
row1      ?     ?     ?     ?    ← across row 1: ????
row2      ?     ?     ?     ?
row3      ?     X     ?     ?    ← down col 1: ???X
```

- **Across (row 1):** four letters, pattern `????` (completely open).
- **Down (col 1):** four letters, pattern `???X` — only `(3,1)=X` is fixed.

## Word list (minimal)

| Pattern | Words |
|---------|-------|
| `????` | CART, BART, DART, HART, PART, TART, WART (7 words) |
| `???X` | BARX, CARX, MARX, PARX, WARX (**5 words — more than 4**) |

There are **no** words matching `?A?X` in the dictionary.

The “more than 4” count on the down clue matters: `someClueTurnsNonViable`
**skips** full re-checking on clues with more than `sweepMaxChoicesSmall` (4)
remaining words.

## The bad suggestion: CART

You are filling across `????` on row 1. **CART** is a valid match.

But CART puts **A** at cell `(1,1)`. That forces the down entry (col 1) to
become `?A?X` instead of `???X`. **Nothing in the dictionary matches `?A?X`.**
The grid is a dead end.

## What each check does

### `someClueTurnsNonViable()` (current sidebar trial)

1. Clone fill state, set CART’s letters on across cells (including `(1,1)=A`).
2. Run one shallow propagation pass.
3. Down still has **5** stale cached `lChoices` for `???X` → **skipped** (not ≤ 4).
4. Returns **false** (“not a dead end”) → **CART stays in the sidebar**.

### `refineLightChoices()` (what change #1 would use)

1. Same clone and letter placement.
2. Full propagation: re-runs `getLexChoices("?A?X")` on the down entry.
3. Gets **zero** matches → `viable = false`.
4. **CART rejected**.

## Expected test result

| Check | Result for CART |
|-------|-----------------|
| `someClueTurnsNonViable` | KEEP (bug) |
| `refineLightChoices` | REJECT (correct) |

## Run the automated test

1. Serve the `exet/` folder locally (or open via your usual Exet dev setup).
2. Open [`exet-test-deadend-refine.html`](../exet-test-deadend-refine.html).
3. The page should show **PASS** in green.

Files:

- [`lexicon-deadend-test.js`](../lexicon-deadend-test.js) — 12-word dictionary
- [`exet-test-deadend-refine.html`](../exet-test-deadend-refine.html) — runs the trial

## Why this shape matters in real grids

You do not need this toy dictionary in production. The same failure mode appears
whenever:

1. Picking a word **narrows a crossing entry** to a pattern with no matches.
2. That crossing still shows **many** cached sidebar matches (>4), so the weak
   check never re-evaluates it.
3. The strong check **would** re-run `getLexChoices()` on the crossing and
   prune the word.

Typical situation: you have typed a few letters, the crossing down still lists
dozens of `???X`-style options, and an across candidate silently kills all of
them — but stays in your sidebar until the slow sweep happens to notice.
