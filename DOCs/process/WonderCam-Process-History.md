# WonderCam P2 Driver - Process and History

Status: LIVING DOCUMENT - started 2026-06-04, annotated as the project proceeds.

This is the project's narrative: how the WonderCam P2 Spin2 driver came to be and
the process/methodology used to build it. It is deliberately a history, not a
spec - it records *what we did and why we did it that way*. New phases get
appended as work continues; existing entries are corrected for accuracy, not
rewritten to look tidy.

Companion documents:
- Device study: `DOCs/research/WONDERCAM-THEORY-OF-OPERATION.md`
- Driver requirements: `DOCs/spec/WonderCam-Driver-Requirements.md`
- Project conventions: `.claude/skill-conventions.md`

---

## Timeline at a glance

| When | Phase | Outcome |
|------|-------|---------|
| 2026-06-03 | Repo genesis | Repo created (commit `92399e9`): `.gitignore`, `LICENSE`, README stub |
| 2026-06-04 | Initial content | Reference material + devcontainer + policy docs landed (commit `fd9924f`) |
| 2026-06-04 | Scaffolding | `CLAUDE.md` authored to orient future work |
| 2026-06-04 | Research | Multi-agent study of the vendor's shipped SDKs -> device Theory of Operation |
| 2026-06-04 | Project prep | Skills methodology bootstrapped: conventions + overlays |
| 2026-06-04 | Requirements | Research turned into the driver Requirements & Specification |
| 2026-06-05 | Implementation | Driver, demo + asset generator, regression top authored; compile-clean under pnut-ts |
| 2026-06-05 | Companion docs | Bring-up playbook + Driver Theory of Operations authored against the as-built code |
| (next) | Hardware bring-up | Walk L0-L5 on a P2 board (host turn-on); retire the unverified facts |

Vendor reference material (the `Register list.pdf` / `Specification.pdf` the study
relied on) is dated 2025-11-27 - it predates this repo and was supplied as input.

---

## Phase 0 - Repo genesis (2026-06-03)

The repository was created with a one-line README naming the intent: "P2 Driver
for the Hiwonder WonderCam AI Vision Camera." No code, no plan yet - a placeholder
staking out the work. The Propeller 2 is the one platform the vendor does NOT ship
a WonderCam driver for; that gap is the whole reason this project exists.

## Phase 1 - Scaffolding and methodology (2026-06-04)

Two things framed everything that followed.

**A working guide (`CLAUDE.md`).** Before any code, the repo was given a concise
orientation file: what the project is, how to build (pnut-ts), the mandatory Spin2
authoring standard, where the protocol source-of-truth lives, and - importantly -
the dual-environment reality (see below).

**A skills methodology.** This project is built with a set of central,
project-agnostic "skills" (procedures) plus two per-project files that adapt them:
- `.claude/skill-conventions.md` - the project's slot VALUES (build commands, doc
  paths, version scheme, P2 tooling).
- `.claude/skills/<skill>/project-overlay.md` - additive procedural DELTAS for a
  specific skill.

The point of the model: keep the procedure reusable across projects, keep the
project-specific bits in two known files. The driver work rides on top of it.

**The dual-environment fact, established early.** The working tree is shared
between a Linux dev container and a macOS host. The container has only the
compiler (`pnut-ts`); the host adds the loader (`pnut-term-ts`) and a second
compiler (`flexspin`). So: we COMPILE in the container and FLASH/RUN on the host.
This single constraint shaped the build/test commands, the test strategy, and a
project overlay on the P2 dev cycle.

## Phase 2 - Research: studying the vendor's shipped examples (2026-06-04)

The deliberate principle: **understand the device completely before writing any
driver code.** Rather than guess the protocol, we mined the vendor's own shipped
example SDKs, which implement the same 8 vision applications across ~6 host
platforms (Arduino, ESP32 Arduino + MicroPython, STM32, Raspberry Pi, C51).

The study was run as a multi-agent research workflow:
- **Foundation** - the register-map PDFs, the canonical Arduino driver (read in
  full), and the wire-protocol PDF, in parallel.
- **Per-application** - one agent per vision application, cross-checking the
  Arduino C++ sketch against the Raspberry Pi Python example.
- **Cross-check** - diffing the driver-library copies for drift, and validating
  register offsets in code against the register-list PDF.
- **Synthesis** - assembling the device Theory of Operation.

The result, `DOCs/research/WONDERCAM-THEORY-OF-OPERATION.md`, documents the I2C
wire protocol, the mode-select model, the per-application result memory map, and
the full capability surface. Crucially, it is HONEST about where the vendor's own
code is buggy or single-sourced - it computed a checksum to prove the driver copy
was identical across examples, flagged confirmed bugs (an unlearned-face count
that returns a pointer cast; an AprilTag stride typo; number/road-sign accessor
methods that are declared but never defined, so the vendor's own example would not
link), and marked facts that only one source attests (the I2C address, the chunk
auto-increment assumption, two Python-only result regions). Those flags became
direct inputs to the requirements: we will fix the bugs and verify the
single-sourced facts on hardware rather than trust them blindly.

## Phase 3 - Project preparation (2026-06-04)

With the device understood, the project was prepared to generate code, using the
two preparatory skills:

- **`bootstrap-conventions`** probed the project and wrote
  `.claude/skill-conventions.md`: identity, the compile-clean build/test commands
  (with the dual-environment split made explicit), the Iron Sheep file-naming
  convention (`isp_wondercam.spin2` driver, `demo_`/`test_` tops), the version
  scheme (a `VERSION` CON), doc paths, and the P2 dev-cycle tuning slots
  (clock 320 MHz, host-only flexspin compat, etc.).
- **`overlay-survey`** found this project's procedural deltas and wrote two
  overlays: one on `p2-dev-cycle` (the container-vs-host capability gating, plus
  the Spin2 authoring-guide compile gate) and one on `baseline-health` (with no
  behavioral suite, the compile-clean sweep IS the baseline gate). It also
  recorded promote-to-central candidates - two of which a sibling P2 project had
  independently surfaced, crossing the promotion bar.

Housekeeping in the same phase: `REF-NO-COMMIT/` (vendor material - port from it,
never commit it) was added to `.gitignore`, and the README was expanded from its
one-line stub into a statement of intent and approach.

## Phase 4 - Requirements from research (2026-06-04)

The device Theory of Operation was turned into
`DOCs/spec/WonderCam-Driver-Requirements.md`. Key decisions captured there:
- A **two-layer driver** - full register access underneath, an ergonomic API for
  all 11 vision applications on top (the high layer corrects the vendor bugs).
- **Passive, polled, single-cog**, and **shared-I2C-bus ready** for the robot it
  will eventually live on.
- A **unified DEBUG "front panel"** demo using the crop-and-overlay display
  technique (documented in `DOCs/dbg-display-theory/`).
- A **bottom-up hardware bring-up** test plan (prove each hardware layer, then
  update the code's expectations) plus an automatable regression top - this is how
  the theory of operation's unverified facts get retired.

## Phase 5 - Implementation (2026-06-05)

With requirements settled, the driver was built as a single tracked sprint
(`wc-driver-v1`, build `v0.1.0`) decomposed into thirteen sequenced tasks - the
seven driver layers, the demo and its generator, the regression top, the two
bench/companion documents, and this doc-currency pass. Each task opened with a
write-ahead breadcrumb and closed only at a recoverable known-good state, so a
context loss mid-sprint never cost more than the current task. Everything below
**compiles clean under pnut-ts in the container**; the on-hardware bring-up
(below) is the host-only turn-on that follows.

**The driver (`src/isp_wondercam.spin2`, `{Spin2_v50}`, 51 public methods).**
Built bottom-up exactly as the requirements layered it: a named-constant backbone
(no magic numbers - the FR-7 "tunable until hardware confirms" knobs are isolated
named constants), a private I2C transport, the public system-control layer
(`start`/`stop`/`firmwareVersion`/`setLed`/`setMode`/`currentMode`/
`updateResult`), the raw `readReg`/`writeReg` full-control API, the result-record
`STRUCT`s, and the ergonomic high-level API across all 11 vision applications.
The five confirmed vendor bugs from the device study were FIXED here (not
re-ported), each commented with the vendor behavior it replaces. The number and
road-sign modes - which have no vendor C path and would not even link in the
vendor example - were authored from the Python reference and carry explicit
"single-sourced / unverified until turn-on" comments.

**A provided I2C object, not embedded bit-banging.** A decision locked during
implementation: the driver composes a PROVIDED singleton I2C object
(`src/isp_i2c_singleton.spin2`, `{Spin2_v46}`) that it owns and configures as a
DEDICATED bus. v0.1.0 ships without the optional shared-bus lock; that lock is
deferred to the punch list, to be added if a deployment actually shares the bus.

**The unified front-panel demo (`src/demo_wondercam.spin2`, `{Spin2_v50}`).** A
single DEBUG PLOT instrument window built with the crop-and-overlay (sprite-blit)
technique, with one per-mode view for each of the 11 applications - vector
bounding boxes for the spatial modes, font-strip readout panels for the
classification-style ones. Its art is generated by `tools/gen_wondercam_panel.py`
(Python 3 + Pillow), which emits the BMP layers AND prints a ready-to-paste Spin2
`CON` layout block so the art and the code cannot drift. The windowed run is
host-only; in-container the demo compiles with DEBUG (`-d`) and the art is
verified by converting BMP to PNG.

**The regression top (`src/test_wondercam.spin2`, `{Spin2_v50}`).** The
automatable subset of the bring-up (bus ACK, version sanity, mode write/echo
round-trip, large-read integrity, per-mode summary-shape checks), emitting
pass/fail to the log and naming anything it cannot exercise - no silent coverage
gaps. The L5 per-application decode stays a manual playbook because it needs
physical targets in front of the lens.

**Two companion documents, written against the as-built code.** The bottom-up
hardware **bring-up playbook** (`DOCs/plans/WONDERCAM-DRIVER-BRINGUP-PLAYBOOK.md`)
walks L0-L5, and each step names which unverified theory-of-operation fact it
retires and which FR-7 constant to update on the finding. The **Driver Theory of
Operations** (`DOCs/WonderCam-Driver-Theory-of-Operation.md`) describes how OUR
driver works - the two-layer architecture, the passive/polled/single-cog model,
the dedicated-bus contract, the latch-summary/fetch-detail result model, and the
configurable-unverified knobs - distinct from the device study that preceded it.

A handful of pnut-ts case-insensitive reserved-word collisions surfaced during
authoring (`wc`/`step`/`neg` while building the demo; the `skip`/`pa`-register
family while building the regression top); these were folded back into
`DOCs/policy/SPIN2-AUTHORING-GUIDE.md` as concrete examples so later work avoids
the same round-trips.

**Still pending: hardware bring-up.** No P2 board has yet run this code. The
container can only compile; flashing and running are host-only. So the bring-up
layers (L0-L5), the behavioral PASS/FAIL of the regression top, and the flexspin
compat-compile all remain for the host turn-on - and the unverified facts the
driver carries as overridable constants stay unverified until then. The driver is
written to make that turn-on a sequence of small confirmations, not a debugging
expedition.

---

## The process model, in brief

A few principles run through the whole project and are worth stating on their own:

1. **Research before development.** Study the device (from the vendor's own
   working code) and write it down before specifying or coding. The theory of
   operation preceded the requirements; the requirements precede the driver.
2. **Honesty about uncertainty.** Findings are labelled by how well they are
   corroborated; vendor bugs are named, not silently inherited; single-sourced
   facts are verified on hardware before they are trusted.
3. **Bottom-up verification.** Prove the hardware layer by layer and update the
   code's expectations after each layer, rather than assuming the stack works.
4. **Reusable procedure, project-local specifics.** The skills methodology keeps
   the "how we work" reusable and the project's particulars in two known files.
5. **Compile here, flash there.** The dual-environment split is honored
   everywhere - it is a property of the work, not a nuisance to route around.

## Keeping this document current

Append a new phase entry (and a timeline row) when a meaningful chunk of work
completes. Correct earlier entries when they turn out to be inaccurate; do not
rewrite history to look cleaner than it was. Date every annotation.
