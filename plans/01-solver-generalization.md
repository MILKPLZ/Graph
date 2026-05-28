# Plan 01 — Solver Generalization: Eliminating Config-Specific Collapses

## Problem Statement

Current solvers overfit to the test_config range (N ≤ 20, open maps). On larger/maze val_configs they catastrophically fail:

| Solver | Config | Score | Delivered | Root Cause |
|--------|--------|-------|-----------|------------|
| VRP | V_Maze (N=50) | 299 | 18/800 (2.2%) | score_pickup penalty too aggressive on large N |
| VRP | V_MediumSparse (N=30) | 1168 | 92/300 (30.7%) | same + urgency threshold too large |
| ACO | V_Maze (N=50) | 314 | 55/800 (6.9%) | same score_pickup penalty |
| CBS | C6 (N=20, C=5) | 772 | 75/100 | detour tolerance `+2` causes cascading deadlocks |
| CBS | V_TrafficJam (N=15, C=25) | 4472 | 343/500 | same — high-density deadlocks |

**Baseline to protect (test_config.txt, C1–C6):**
```
ACO: 5242 | VRP: 5221 | Greedy: 4962 | CBS: 4598 | Total: 20,023
```

---

## Phase 0: Confirmed Architecture Facts

> Read these files at the start of any implementation session — do NOT assume from memory.

### Files and exact line numbers for every change:
- `solvers/solver.py:127-138` — `urgent_slack_threshold()`, base multiplier = 1.5
- `solvers/solver.py:168-172` — `score_pickup()` relative-distance penalty, divides by `self.N`
- `solvers/solver.py:285-296` — `_find_valid_center()` helper — reuse pattern for Phase 1
- `solvers/solver.py:57-76` — `_bfs_from()` — reuse for map radius sampling
- `solvers/mapd_cbs_solver.py:175` — `best_alt_d <= d_orig + 2` (too tight)
- `solvers/mapd_cbs_solver.py:76` — `100.0 / max(1, slack)` (not T-normalized)
- `solvers/vrp_ortools.py:47` — `detour_thresh = max(3, self.N // 4)`
- `solvers/vrp_ortools.py:60` — `bonus = 2.0` (fixed, not score-proportional)

### Allowed APIs (confirmed from source):
- All subclasses inherit via `super().__init__(env)` — safe to add instance vars in `Solver.__init__`
- `self.N`, `self.T`, `self.G`, `self.C` available at `__init__`
- `self.grid` is a 2-D list, `grid[r][c] == 0` means walkable
- `_bfs_from(start)` returns parent dict keyed by all reachable cells; side-effect: populates `_dist_cache[(start, pos)]` for every reachable pos
- `_find_valid_center()` — already exists, call it to get a valid interior cell
- `_dist_cache` is keyed by `(Position, Position)` tuples

### Anti-patterns (do NOT do):
- Do NOT rename any class or file
- Do NOT call `default_result()` anywhere in production code
- Do NOT access `env.orders` directly inside a solver
- Do NOT recompute `_map_radius` every timestep — only in `__init__`
- Do NOT change penalty threshold ratios (0.8 / 1.5 in score_pickup) — only change the denominator

---

## Phase 1: Adaptive Map Radius in score_pickup (solver.py)

### Root cause
`score_pickup` at `solver.py:168`:
```python
rel_d = d1 / max(1, self.N)
if rel_d > 1.5:   # fires when d1 > 1.5*N
    score *= 0.4
elif rel_d > 0.8: # fires when d1 > 0.8*N
    score *= 0.7
```

On open N=20 maps, typical BFS distance between two cells ≈ 12–20. Penalty fires only at d1 > 16 (reasonable).

On N=50 maze (V_Maze), BFS between nearby cells can be 80–120. Penalty fires at d1 > 40, meaning nearly **every order** gets 0.4× or 0.7× multiplied. This makes all scores tiny and assignment quality collapses.

### Fix

**Step 1** — Add `_compute_map_radius()` to `Solver` class (add after `_find_valid_center()` at line 296):

```python
def _compute_map_radius(self) -> float:
    """90th-percentile BFS distance from map center. Never less than N."""
    center = self._find_valid_center()
    parent = self._bfs_from(center)           # fills _dist_cache[(center, *)]
    dists = sorted(
        self._dist_cache.get((center, pos), 0) for pos in parent
    )
    if len(dists) < 4:
        return max(1.0, float(self.N))
    idx = max(0, int(len(dists) * 0.9) - 1)
    return max(float(self.N), float(dists[idx]))  # never stricter than current
```

The `max(float(self.N), ...)` guard ensures that on **open maps** the penalty fires at the same distance or later (never earlier) than before. On maze maps the radius is larger, so penalty fires much later.

**Step 2** — In `Solver.__init__`, after `self._wander_fallback = ...` (line 46):
```python
self._map_radius: float = self._compute_map_radius()
```

**Step 3** — In `score_pickup` at line 168, change:
```python
rel_d = d1 / max(1, self.N)      # OLD
```
to:
```python
rel_d = d1 / max(1, self._map_radius)   # NEW
```

### Why this is safe
- Open maps (C1–C6): `_map_radius = max(N, 90th_percentile)`. On a clean N×N grid, 90th percentile of center distances ≈ 0.9×N. Since we take `max(N, ...)`, result = N. Behavior identical to before.
- Maze maps: 90th percentile >> N (e.g., N=50 maze → radius ≈ 80–120). Penalty now fires at d1 > 64–96 instead of d1 > 40. Far fewer orders get penalized.

### Verification checklist
```bash
python3 run_test.py --config test_config.txt --method all
```
- [ ] ACO ≥ 5200, VRP ≥ 5150, Greedy ≥ 4900, CBS ≥ 4550 (no worse than −2%)

```bash
python3 run_test.py --config val_config.txt --method all
```
- [ ] VRP V_Maze delivered/total improves from 18/800
- [ ] ACO V_Maze delivered/total improves from 55/800
- [ ] VRP V_MediumSparse delivered/total improves from 92/300

---

## Phase 2: Fix CBS Detour Tolerance + Urgency (mapd_cbs_solver.py)

### Root cause A — detour tolerance
`mapd_cbs_solver.py:175`:
```python
if best_alt_d <= d_orig + 2:    # allows at most 2 extra steps
```
On N=20 (C6), `d_orig` might be 15. 2 extra steps = 13% more. 
On N=50 (V_Maze), `d_orig` might be 80. 2 extra steps = 2.5% more → effectively no alternative accepted → shipper stands still → cascading deadlocks.

### Root cause B — urgency not T-normalized
`mapd_cbs_solver.py:76`:
```python
urgency = 100.0 / max(1, slack)
```
On T=1200 configs, `slack` values are naturally 3–5× larger than T=240 configs. All shippers get tiny, similar urgency values → priority ordering is meaningless → random service order → high-id shippers starved.

### Fix A — adaptive detour tolerance (line 175)
```python
# OLD:
if best_alt_d <= d_orig + 2:
# NEW:
if best_alt_d <= d_orig + max(2, self.N // 8):
```

Scaling table:
| N  | tolerance |
|----|-----------|
| 7  | 2 (unchanged) |
| 20 | 2 (unchanged) |
| 50 | 6 |
| 70 | 8 |

### Fix B — T-normalized urgency (line 76)
```python
# OLD:
urgency = 100.0 / max(1, slack)
# NEW:
t_scale = max(1, self.T // 240)
urgency = 100.0 * t_scale / max(1, slack)
```

Effect: T=240 → scale=1 (identical); T=720 → scale=3 (3× more differentiation); T=1200 → scale=5. Priority ordering becomes meaningful on long-horizon configs.

### Verification checklist
```bash
python3 run_test.py --config test_config.txt --method MAPDCBSSolver
```
- [ ] CBS C6 net_reward improves from 772 toward 1000+
- [ ] CBS C1–C5 scores each within −2% of 265 / 429 / 873 / 1012 / 1245

```bash
python3 run_test.py --config val_config.txt --method MAPDCBSSolver
```
- [ ] CBS V_TrafficJam net_reward improves from 4472 (should exceed Greedy 4462)
- [ ] CBS V_MediumSparse net_reward improves from 2513 (already best — do not regress)

---

## Phase 3: Fix urgent_slack_threshold Over-Aggressiveness (solver.py)

### Root cause
`solver.py:129`:
```python
avg_cross = self.N * 0.7
base = max(3, int(avg_cross * 1.5))
```

For N=50: `base = max(3, int(35 * 1.5)) = 52`.

On V_Maze (N=50), a shipper carrying an order with 90 timesteps remaining but 80 BFS steps to delivery gets:
`o.et - (t + 80) = 10 < 52` → `has_urgent = True`.

This fires for almost every order on large maps, locking shippers into **single-order delivery mode** and preventing them from picking up additional orders. Even shippers with empty capacity refuse new pickups because their current bag order is "urgent."

### Fix — reduce urgency sensitivity

Change line 129:
```python
# OLD:
base = max(3, int(avg_cross * 1.5))
# NEW:
base = max(3, int(avg_cross * 0.5))
```

Scaling table:
| N  | old base | new base |
|----|----------|----------|
| 7  | 7        | 3        |
| 20 | 21       | 7        |
| 50 | 52       | 17       |
| 70 | 73       | 24       |

Effect: urgency now fires only when there are fewer than 7–17 extra steps of slack, instead of 21–52. Shippers will pick up additional orders more aggressively instead of rushing single orders to delivery.

### Risk mitigation
This change affects ALL solvers (it's in base class). Test after Phase 1 and Phase 2 are stable to isolate regressions.

If test_config on-time rates drop significantly (>5%), revert and investigate. The on-time rate may drop slightly but net_reward (which is what graders count) should improve due to more delivered orders.

### Verification checklist
```bash
python3 run_test.py --config test_config.txt --method all
```
- [ ] Total net_reward across all methods ≥ 20,000 (current baseline: 20,023)
- [ ] No single solver loses more than 3% on any config

```bash
python3 run_test.py --config val_config.txt --method all
```
- [ ] VRP V_MediumSparse delivered improves from 92/300
- [ ] ACO V_Maze delivered improves from 55/800

---

## Phase 4: Fix VRP Detour Bonus Scaling (vrp_ortools.py)

### Root cause
`vrp_ortools.py:60`:
```python
bonus = 2.0   # fixed, regardless of score magnitude or map size
```

On C1 (N=7), typical scores are 5–20. A bonus of 2.0 = 10–40% of score. Meaningful.  
On V_MediumSparse (N=30), typical scores are 0.1–2.0 (because distances deflated all scores). A bonus of 2.0 may dominate and cause wrong assignments — assigning a shipper to a low-value order just because it's near the delivery target.

Also, `detour_thresh = max(3, self.N // 4)` at line 47:
- N=7: thresh=3
- N=30: thresh=7 (too small for 30×30 map where typical detour BFS might be 20)
- N=50: thresh=12

### Fix — proportional bonus and adaptive threshold

Line 47 (`detour_thresh`):
```python
# OLD:
detour_thresh = max(3, self.N // 4)
# NEW:
detour_thresh = max(3, self.N // 2)
```

Line 58–61 (bonus calculation), replace:
```python
bonus = 0.0
if s.id in self._delivery_targets:
    dd = self._delivery_targets[s.id]
    d_detour = self.bfs_distance(dd, (o.sx, o.sy))
    if d_detour < detour_thresh:
        bonus = 2.0
```
with:
```python
bonus = 0.0
if s.id in self._delivery_targets:
    dd = self._delivery_targets[s.id]
    d_detour = self.bfs_distance(dd, (o.sx, o.sy))
    if d_detour < detour_thresh:
        bonus = max(0.5, sc * 0.15)   # 15% of order score, min 0.5
```

This makes the bonus proportional to the order value, preventing low-value orders near delivery from winning over high-value distant orders.

### Verification checklist
```bash
python3 run_test.py --config test_config.txt --method VRPOrToolsSolver
```
- [ ] VRP total score ≥ 5150 (within 1.5% of 5221 baseline)
- [ ] VRP C6 score ≥ 1400 (was 1482, allow slight drop while verifying stability)

```bash
python3 run_test.py --config val_config.txt --method VRPOrToolsSolver
```
- [ ] VRP V_MediumSparse net_reward improves from 1168 toward 2000+
- [ ] VRP V_TrafficJam does not regress from 6867

---

## Phase 5: Full Benchmark + Regression Gate

### Run both benchmark configs
```bash
python3 run_test.py --config test_config.txt --method all
python3 run_test.py --config val_config.txt --method all
```

### Success criteria for test_config.txt (must ALL pass):
| Solver   | Min acceptable score |
|----------|---------------------|
| ACOSolver | ≥ 5100 |
| VRPOrToolsSolver | ≥ 5050 |
| GreedyBFS | ≥ 4850 |
| MAPDCBSSolver | ≥ 4400 |
| **Total** | **≥ 19,400** |

### Success criteria for val_config.txt (target improvements):
| Config | Metric | Baseline | Target |
|--------|--------|----------|--------|
| V_Maze | VRP delivered | 18/800 | ≥ 100/800 |
| V_Maze | ACO delivered | 55/800 | ≥ 150/800 |
| V_MediumSparse | VRP delivered | 92/300 | ≥ 150/300 |
| V_TrafficJam | CBS net_reward | 4472 | ≥ 5500 |
| V_MediumSparse | CBS net_reward | 2513 | ≥ 2400 (no regression) |

### If test_config regression occurs:
Rollback individual phases in reverse order (Phase 4 → 3 → 2 → 1) until the regression is isolated. Each phase is a separate logical change — they can be reverted independently.

---

## Execution Order and Dependencies

```
Phase 1 (solver.py map radius)        ← no dependencies, do first
    ↓
Phase 2 (CBS detour + urgency)        ← independent of Phase 1
    ↓
Phase 3 (urgent_slack base)           ← depends on Phase 1 being stable first
    ↓
Phase 4 (VRP detour bonus)            ← independent, can run after Phase 3
    ↓
Phase 5 (full benchmark)              ← always last
```

Phases 1 and 2 can be done in the same session. Phase 3 should be validated alone (it touches shared base class logic used by all 4 solvers).

---

## Context for New Sessions

If resuming in a new chat, provide this context:
- Current benchmark: `results_test_config_eval/summary.json` for C1–C6 baseline
- Val benchmark: `results_val/` directory has pre-run results for all 4 val configs
- All solver code is in `solvers/` — read the target file fresh before editing
- The plan is in `plans/01-solver-generalization.md`
- Key constraint: class names and file names in `solvers/` must not change (grader hardcodes them)
