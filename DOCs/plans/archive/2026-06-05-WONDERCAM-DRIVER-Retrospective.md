# WonderCam Driver Sprint - Retrospective

Sprint: `wc-driver-v1` | Build: v0.1.0 (compile-clean; behavioral turn-on owed)
Closeout: `DOCs/plans/archive/2026-06-05-WONDERCAM-DRIVER-Sprint-Closeout.md`
Date: 2026-06-05

Captures *what was learned*, not *what shipped* (that is the closeout). Signal, not narrative.

## Discovered perspectives

- **Research-first collapsed the build time.** Estimated ~40 h across 13 tasks;
  most tasks landed in single-digit minutes (e.g. §6 spatial API est 4 h / actual
  9 m; §8 demo framework est 5 h / actual 14 m). The device Theory of Operation had
  already absorbed all the protocol uncertainty, so each driver task was mechanical
  translation, not discovery.
- **The one task that took real time was the I2C transport (§1/`#2`, ~3 h 13 m)** -
  the only layer with genuine integration novelty (meeting the provided
  `isp_i2c_singleton` object's interface). Uncertainty clustered exactly where new
  external dependency met new code; everything downstream of a settled transport
  was fast.
- **The vendor reference is a liability, not just a source.** Five confirmed bugs
  and several single-sourced facts meant "port faithfully" would have shipped
  vendor defects. Isolating the unverified facts as FR-7 named constants (not
  hardcoded) is what turns hardware turn-on into a sequence of one-line
  confirmations instead of a debugging expedition.

## Process insights

- **The breadcrumb + task-handoff discipline survived a real context clear.** This
  session resumed cold (post-`/clear`) mid-`#13` boundary and recovered the entire
  sprint state from the resume key + todo board with zero re-derivation. The
  write-ahead protocol earned its keep.
- **No stranded `task_#N_*` keys across 13 tasks** - task-handoff's
  same-operation pattern-delete (iron rule #3) fired every time. The hygiene
  protocol is working, not just specified.
- **`simplify` friction recurred 3x in one sprint** (see Methodology). The skill is
  code-shaped and was mandated at handoff §2 even on pure-prose tasks where it does
  not apply. Worked around each time with an editorial self-check; the workaround
  caught a real spec self-contradiction at `#13` a code-pass would have missed.

## Quality and efficiency observations

- **Estimate-vs-actual delta was enormous and one-directional** (everything faster).
  Cause: the spec + theory-of-operation removed all in-task discovery. Lesson for
  next planning: when a research artifact precedes implementation, time estimates
  should be discounted hard for the translation tasks and concentrated on the
  genuine-integration tasks.
- **Single-source-of-truth art pipeline prevented drift.** The Pillow generator
  printing a ready-to-paste Spin2 CON block (not just BMPs) meant demo art and code
  geometry could not diverge - a pattern worth keeping.

## Downstream impact

- **Enables:** the host hardware turn-on (bring-up playbook is written and
  layer-keyed); any P2 robot design can now integrate the WonderCam over a
  dedicated I2C bus.
- **Owes / destabilizes:** nothing is behaviorally proven yet. The FR-7 tunables
  (`ADDR_LOW_FIRST`, `CHUNK_AUTOINC`, `TAG_REC_STRIDE`, contested func numbers) and
  the number/landmark modes stay unverified until L0-L5. The probability-return
  representation (scaled-int vs float) is an open decision that, if changed, ripples
  into the demo and regression readouts - decide before v0.1.0 ships.

## Methodology lessons (candidate triage recommendations)

Reads `feedback_skill_evolution_candidates.md` (6 entries). Verdicts are
recommendations for Stephen to confirm; promotion edits central skills, which is
his call.

| # | Candidate | Recommend |
| --- | --- | --- |
| 1 | Environment capability gating for `p2-dev-cycle` (compile-only vs flash env) | **Defer** - 1st surfacing; monitor for a 2nd project. |
| 2 | Spin2 authoring standard as a compile gate | **Promote** - corroborated by a 2nd project (P2 Robot Dog); two-project bar met. |
| 3 | "no test suite -> compile-all is the baseline gate" | **Promote** - corroborated by a 2nd project; two-project bar met. |
| 4 | A "build a P2 DEBUG-PLOT display" skill | **Defer** - 1st surfacing; build when a 2nd P2 PLOT project appears. |
| 5 | `simplify` doesn't fit prose/declarative diffs | **Promote/refine** - 3 data points this sprint; branch task-handoff §2 on deliverable shape (code -> simplify; prose -> editorial pass). |
| 6 | `test-playbook` references undefined `PLAYBOOK_FILENAME_PATTERN` slot | **Defer (low-effort fix)** - 1st surfacing; either document a default in the central skill or add the slot to the conventions schema. |

**Net:** three promotion-ready candidates (2, 3, 5), three first-surfacing defers
(1, 4, 6). This sprint produced real, actionable process learning - not a clean
no-delta execution.
