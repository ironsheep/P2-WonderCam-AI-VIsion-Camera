# WonderCam Driver Sprint - Closeout Audit

Sprint: `wc-driver-v1` | Build: v0.1.0 | Closed: 2026-06-05
Plan audited: `DOCs/plans/WONDERCAM-DRIVER-SPRINT-PLAN.md` (archived alongside this doc)
Retrospective: `DOCs/plans/archive/2026-06-05-WONDERCAM-DRIVER-Retrospective.md`
Auditor verdict: **CERTIFIED DONE** - every plan section SHIPPED.

This is a completeness audit of the plan against the as-built code, not a commit
inventory. Citations are `file:line` in the as-built tree.

## Verification posture (carried from the plan)

"First testing" for this sprint = **compiles clean under pnut-ts** (the container
path). Behavioral proof - does the driver actually talk to the camera - is the
deferred bottom-up hardware turn-on (Section 11's playbook, executed on the host),
which is explicitly a follow-on, NOT part of this sprint's completion. So every
SHIPPED verdict below means "code-complete and compile-clean"; cases tagged
`(turn-on)` in the plan remain to be confirmed on hardware.

## Per-section audit

| Plan section | Deliverable | Status | Evidence |
| --- | --- | --- | --- |
| S1 I2C transport | `readFromAddr`/`writeToAddr` + chunk strategy | SHIPPED | `src/isp_wondercam.spin2:755` (readFromAddr), `:743` (writeToAddr); chunk helpers `:786` startRead, `:808` sendRegAddr, `:820` summaryReadPlan |
| S2 Register map + tunable CON | VERSION + FR-7 knobs + full map | SHIPPED | `:28` `VERSION=0_01_00`; FR-7 `:185-188` ADDR_LOW_FIRST/READ_CHUNK/CHUNK_AUTOINC/TAG_REC_STRIDE; `:91` PROB_DIVISOR |
| S3 System control | start/stop/firmwareVersion/setLed/setMode/currentMode/updateResult | SHIPPED | `:216, :233, :242, :251, :262, :290, :303` |
| S4 Raw access API | readReg/writeReg | SHIPPED | `:319, :329` |
| S5 Result-record STRUCTs | spatial / line / tag (shared) | SHIPPED | `:173` spatial_result_t, `:175` line_result_t, `:177` tag_result_t |
| S6 High-level spatial API + 5 bug fixes | face/object/color/line/AprilTag | SHIPPED | families `:348-:620`; **5 vendor bug fixes** commented at `:377, :414, :464, :602, :608` |
| S7 High-level classification API | class/feature/number/landmark/QR/barcode | SHIPPED | `:624-:735`; number/landmark marked UNVERIFIED-until-L5 in-code |
| S8 Demo framework + asset pipeline | demo skeleton + generator + BMPs | SHIPPED | `src/demo_wondercam.spin2`; `tools/gen_wondercam_panel.py`; 4 BMPs `src/wc_panel_bg.bmp`, `wc_modes.bmp`, `wc_font.bmp`, `wc_led.bmp` |
| S9 Demo per-mode views (all 11) | one view per application | SHIPPED | dispatch `src/demo_wondercam.spin2:260-272` (11 FUNC_* cases + `other: viewIdle()` no-data fallback) |
| S10 Regression top | L0-L4 automatable self-check | SHIPPED | `src/test_wondercam.spin2`: L0 `:73`, PASS/FAIL/SKIP counters `:55-57`, named coverage gaps `:68` |
| S11 Bring-up playbook | numbered host bench procedure | SHIPPED | `DOCs/plans/WONDERCAM-DRIVER-BRINGUP-PLAYBOOK.md` (23.7 KB) |
| S12 Driver Theory of Operations | how-our-driver-works doc | SHIPPED | `DOCs/WonderCam-Driver-Theory-of-Operation.md` (17.4 KB) |
| S13 Documentation currency | spec/process/README brought current | SHIPPED | spec status -> IMPLEMENTED v0.1.0 + locked decisions; `WonderCam-Process-History.md` Phase 5; `README.md` status; bonus `CLAUDE.md` staleness fix |

**Cross-reference table:** reconciled both directions - 13 plan sections, 13 rows,
13 tasks `«#1»-«#13»`, all completed. No stale rows, no orphan sections.

**Driver surface:** 51 public methods; all 11 vision applications have a complete
accessor family; all 5 confirmed vendor bugs corrected (not re-ported), each
commented with the vendor behavior it replaces.

## Exit baseline (baseline-health)

- **Build:** clean, 0 warnings. All four `.spin2` files compile clean under
  pnut-ts 1.55.0: driver, demo (`-d`), regression top, and the provided
  `isp_i2c_singleton.spin2`.
- **"Tests":** compile-clean IS the in-container baseline. The regression top's
  behavioral L0-L4 self-checks run host-only at turn-on and are explicitly named
  as not-exercised in-container - a documented dual-environment deferral, not a
  silent skip.
- **Entry -> exit:** entry baseline was greenfield clean-slate (no source
  compiled). Exit baseline is four files compile-clean. **IMPROVED; no
  regression.** Exit is a green protection point for the next sprint.

## Carryover (all on the punch list; none are plan-section gaps)

These are deferred decisions and demo niceties, explicitly out of v0.1.0 scope -
not unfinished plan commitments:

1. **Shared-bus I2C locking** - v0.1.0 owns a dedicated bus, no lock. Add a
   caller-supplied lock around each transaction in
   `src/isp_wondercam.spin2` (`writeToAddr`/`readFromAddr`) + a `lockId` param on
   `start()` when a deployment shares the bus. (PUNCH-LIST; spec FR-5.)
2. **Front-panel demo polish** - (a) floating per-box id labels need a second
   font-strip row on the dark VIEW_BG; (b) AprilTag 6-DoF pose not shown
   numerically (needs float formatting). Both demo-only. (PUNCH-LIST, from `#9`.)
3. **Probability return representation** - Stephen's call before v0.1.0 ships:
   classification `*TopProb`/`*ProbOfId` currently return a scaled integer
   `0..PROB_DIVISOR` (negatives = error codes), keeping the driver float-free. The
   vendor returns `float`. Localized change to those methods + the `#9`/`#10`
   readouts if a float return is preferred. (PUNCH-LIST, from `#7`.)

## Behavioral verification still owed (host turn-on, follows the sprint)

The bring-up playbook L0-L5 and the regression top's behavioral run have NOT
executed - no P2 board has run this code (container compiles only). Until then the
FR-7 tunables (`ADDR_LOW_FIRST`, `READ_CHUNK`, `CHUNK_AUTOINC`, `TAG_REC_STRIDE`,
contested func numbers color=5/number=10/landmark=11) and the number/landmark
modes remain unverified-but-overridable. This is by design, not an audit gap.
