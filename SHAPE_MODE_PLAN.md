# Shape-Based Pattern Search — Design & Implementation Plan

Status: DRAFT for review (do not implement until approved)
Author: planning pass, 2026-07-16

## 1. Goal
Add a **shape-based** candidate generator to gapbf: instead of enumerating the whole
legal path space (graph-based, → centuries on a 5×5), start from the *shapes a human
actually draws* (initials like "R S", letters, a house, lines, corners), expand each into
many variations (scale, rotate, mirror, translate, direction, …), and try those first.
Turns a centuries-long search into hours/days when the pattern is a deliberate shape.

## 2. Architecture decision — integrate, don't fork  (recommended)
**Recommendation: one repo, a pluggable candidate source. NOT a separate project.**

Reason: the shape approach shares almost everything with the current tool and differs in
exactly one place — *where candidate patterns come from*. Everything downstream is identical:

| Shared (reuse as-is) | New (shape-specific) |
|---|---|
| SQLite attempt DB, dedup, resume, retry-first | Shape library (templates) |
| `ADBHandler` → `twrp decrypt`, 10s throttle, backoff | Transform/variation engine |
| Telegram success notify (`notify.py`) | Shape→grid render + snap |
| Web UI shell, board widget | Drawing canvas + notes |
| **Pattern-legality primitives** in `PathFinder` (blocker/intermediate nodes, crossing cache, distance) | Candidate ranking |
| Config/validation, CLI, live dashboard | — |

Design: introduce a **`CandidateSource`** abstraction that yields patterns. Two impls:
- `GraphCandidateSource` (wraps today's `PathFinder` DFS).
- `ShapeCandidateSource` (new).
Config/UI picks `search_mode: graph | shape | shape_then_graph`. `shape_then_graph` runs the
shape dictionary first, then falls back to the graph space — best of both.

A fork would duplicate the DB/adb/throttle/notify/UI and immediately diverge; every bug fix
(like the recent shell-quoting + throttle work) would have to be done twice. Rejected.

(If you still want a public-facing "shape-based" identity, it's a README section + a mode
name, not a second codebase.)

## 3. Core pipeline
```
drawn shape / picked template
      │
      ▼
 normalized shape (grid-independent polyline on a reference lattice)
      │  transform engine (scale·rotate·mirror·translate·direction·start·segment)
      ▼
 many candidate polylines
      │  render → snap to target N×N dots → node sequence
      ▼
 legality filter (reuse PathFinder: adjacency/distance, blocker, crossings, length, no-revisit)
      │  rank + dedup vs DB
      ▼
 ordered candidate list  ──►  existing ADBHandler (twrp decrypt, 10s spacing, notify)
```

## 4. Grid-independent shape model
Shapes are stored **abstractly**, not tied to a grid — the user's key insight.
- A shape = one or more **strokes**; each stroke = an ordered polyline of points in a
  normalized unit space `[0,1]²` (origin top-left).
- Rendering to an N×N grid = map unit space onto the dot lattice, then **snap** each polyline
  vertex to the nearest dot; a straight run between two dots auto-includes the dots it passes
  over (matches Android's intermediate-dot rule).
- Because patterns are a *single continuous stroke with no finger lift*, multi-stroke shapes
  (like a literal "R") are realized as the plausible **single-stroke approximations** a person
  draws (the engine enumerates stroke-joining orders / drops the impossible lifts).

Data model (sketch):
```python
@dataclass(frozen=True)
class Shape:
    name: str                      # "R", "S", "house", "line-diag", "initials-RS"
    strokes: tuple[Polyline, ...]  # normalized [0,1]^2 points
    tags: tuple[str, ...]          # "letter","monogram","geometric","common"
    base_rank: int                 # commonness / priority
Polyline = tuple[tuple[float, float], ...]
```

## 5. Standard shape library (grid-independent, seeded from real-world research)
Curated, each defined once in unit space, reused for every grid size. **Seeded from empirical
studies of real patterns** (see §11), NOT guessed. Priority tiers:
- **Tier A — the owner's initials**: `R`, `S`, and joined monogram `RS` (single-stroke forms +
  variants). Pinned to the top: ~10% of real patterns are the owner's own initial (Løge).
- **Tier B — empirically most-common letter shapes** (Munyendo SOUPS'21, Løge): `Z` (most common
  of all), `L`, `W`, `M`, `N`, `U`, `V`, `C`, `O`, `S`, `G`, `X`. Then the rest of A–Z.
- **Tier C — digits**: especially `2` (very common), plus `1`, `7`, `4`.
- **Tier D — geometric strokes**: diagonal line top-left→bottom-right (very common), L-corner,
  staircase, box/square, triangle, U/V, zigzag, cross, checkmark, arrow, spiral, lines (all orient).
- **Tier E — household/object**: house (box+roof), heart, star (lower priority).

Concrete seeds to vendor (license-checked): the 120 real patterns from **Ye et al. NDSS'17**
(shapes extracted grid-independently), the letter catalog from **Munyendo SOUPS'21**, and the
letter/3-gram tables from **Løge**. Stored as data (`shapes/library/*.json`) with a `base_rank`.

NOTE: all source data is **3×3**. We import the *shapes and priors*, not raw node-sequences, and
render them onto the 5×5 (or any N×N) via the grid-independent engine. This is the whole reason
grid-independence matters.

## 6. Variation ("wildness") engine
Composable transforms applied in normalized space, then rendered+snapped:
- **Translate** — place the shape at every valid grid offset.
- **Scale** — fit the shape at multiple sizes (e.g. spanning 3, 4, 5 dots across).
- **Rotate** — 0/90/180/270° (optionally 45° increments).
- **Mirror** — horizontal, vertical, both.
- **Direction** — draw the stroke forward and reversed.
- **Start point** — for closed/loop shapes, start at each vertex.
- **Segment edit** — optionally drop a trailing/leading segment (people shorten shapes).
- **Snap tolerance** — how loosely a hand-drawn stroke maps to dots (accounts for sloppiness).

A single **`wildness` level (0–3)** controls breadth:
- `0` exact: identity + mirror + 4 rotations.
- `1` low: + scales + translations.
- `2` medium: + direction + start-point + 45° rotations.
- `3` high: + segment edits + loose snap tolerance (full cartesian product).

Each level prints an estimated candidate count *before* running (so the user sees "this makes
4,812 candidates ≈ 13 h" and can dial it).

Engine (sketch):
```python
def expand(shape: Shape, grid_size: int, wildness: int, cfg: Config) -> Iterator[list[str]]:
    for t in transforms_for(wildness):
        poly = t.apply(shape)
        seq = render_and_snap(poly, grid_size)          # -> node chars
        if is_legal(seq, cfg):                            # reuse PathFinder primitives
            yield seq
```

## 7. Legality filter (reuse, don't reinvent)
Candidate node-sequences are validated with gapbf's **existing** `PathFinder` primitives:
adjacency/`path_max_node_distance`, blocker/intermediate-node rule, crossing constraints,
`path_min_length`/`path_max_length`, no node revisit. This guarantees shape candidates are the
same "legal patterns" the graph mode produces — and that they map to the same `twrp decrypt`
strings and the same DB dedup keys.

## 8. Ranking & dedup — driven by empirical priors
Order candidates by a score combining shape priority and **research-backed priors** (Løge,
Munyendo, Aviv-Markov):
1. **Owner's drawn shapes** + their low-wildness variants (highest).
2. **Initials R/S/RS**, then Tier-B common letters, then rest of library by `base_rank`.
3. **Start-node prior**: top-left first, then the other 3 corners (77% of real patterns start in a
   corner, 44% top-left), then edges, center last.
4. **Length prior**: 4 → 5 → 6 first (real avg ~5, 4 most common), longer later.
5. **Direction prior**: left→right and top→bottom strokes before their reverses.
6. **Simplicity prior**: fewer crossings / lower complexity first (real avg complexity is low).
7. Higher-wildness variants last.
Optionally break ties with an **Aviv-style Markov model** over node-transitions. Dedup against the
DB (`attempt`+device+grid) exactly like retry-first; the ordered list feeds the existing pipeline
(model on `_gather_retry_first_paths`).

## 9. Web drawing UI
Extend the existing web board:
- **Canvas on the N×N grid**: user drags across dots → captured as a node sequence; the app
  shows the snapped pattern and a guess label ("looks like: R").
- **Multiple candidates**: add several drawn shapes; also pick named shapes from the library.
- **Notes**: free-text note per shape ("pretty sure it started top-left") — persisted with the run.
- **Wildness slider** (0–3) with a **live candidate-count + ETA** estimate.
- **Launch** → generates the dictionary, dedups, starts the run; live log + Telegram on hit.
- Shape "identification" (classifier naming the drawn shape) is **optional/nice-to-have** — the
  core needs only the drawn node-sequence + variations, so MVP ships without ML.

## 10. Module layout & config
```
src/gapbf/shapes/
  library.py        # Shape dataclass + seed templates (+ json data)
  transforms.py     # translate/scale/rotate/mirror/direction/start/segment, wildness levels
  render.py         # normalized polyline -> grid node sequence (snap + intermediate dots)
  source.py         # ShapeCandidateSource: expand + filter(legality) + rank + dedup
src/gapbf/candidate_source.py   # CandidateSource protocol; GraphCandidateSource wrapper
```
Config additions: `search_mode: graph|shape|shape_then_graph`, `shapes: [<drawn node lists>]`,
`shape_library: [names]`, `wildness: 0..3`, `transforms: {enabled...}`. Existing
grid/length/distance/crossing constraints still apply as the legality filter.

## 11. Research findings (done 2026-07-16) + remaining open items
Empirical basis for the library and ranking (all real-world pattern studies):
- **Løge 2015** (~4,000 patterns, DEF CON 23 / NTNU thesis "Tell Me Who You Are…"): 44% start
  top-left, 77% start in a corner; avg ~5 nodes, 4 most common, 8 least; **~10% are a letter,
  usually the owner's initial**; motion left→right/top→bottom; low complexity/crossings.
  https://www.schneier.com/blog/archives/2015/08/regularities_in.html ,
  https://arstechnica.com/information-technology/2015/08/new-data-uncovers-the-surprising-predictability-of-android-lock-patterns/
- **Munyendo et al. SOUPS'21** (blocklists): most common patterns depict letters —
  Z, L, W, X, V, U, C, M, G, S and digit 2; users start from an initial.
  https://gwusec.seas.gwu.edu/android-pattern-blocklists/soups21-84-pattern-blocklist.pdf
- **Ye et al. NDSS'17** "Cracking Android Pattern Lock in Five Attempts": 120 real patterns dataset
  (node notation 0–8). https://doi.org/10.17635/lancaster/researchdata/250
- **Aviv et al.** Markov ranking of all 389,112 patterns by likelihood (for tie-break ordering).
- Enumeration/validation refs: github.com/delight-im/AndroidPatternLock (all combos by length),
  github.com/greigdp/android-pattern-combinations.

CRITICAL CAVEAT: every dataset above is **3×3**. Import shapes + priors, not raw sequences; render
to N×N via the grid-independent engine.

Remaining open items:
- Vendor + license-check the concrete seed data (NDSS'17 set, Munyendo letter catalog).
- Confirm the **>9 node encoding** for this 5×5 lockscreen mod before trusting a 5×5 run
  (3×3 matches AOSP; larger grids unverified — see CASE_NOTES.local.md).
- Best single-stroke drawable forms for each letter (esp. R, S) on a 5×5.

## 12. Phased implementation
- **Phase 0** — this plan (review/approve).
- **Phase 1 (unblocks the real recovery FAST, CLI-only)** — shape model + transform engine +
  render/snap + legality filter + seed library (**R, S, RS, house, lines, corners**). Output a
  deduped candidate dictionary. One self-check test (counts + a couple known snaps). *No UI yet.*
- **Phase 2** — `ShapeCandidateSource` wired into the run as a prioritized source; `search_mode`
  config; deploy to rs-bf; Telegram-on-hit. **→ start the actual month-long run here.**
- **Phase 3** — web drawing canvas + notes + wildness slider + live count/ETA + launch.
- **Phase 4** — full library (A–Z, digits, symbols), ranking polish, optional shape-identify label,
  README "shape mode" section.

## 13. Recommendation on sequencing for the actual goal (the photos)
Do **Phase 1 + 2 first and fast** (a curated R/S/RS/house/line dictionary is maybe a few hundred
candidates = hours). Get that running on rs-bf while we build the nicer drawing UI (Phase 3) in
parallel. Don't let the UI block the recovery run.
```
```
