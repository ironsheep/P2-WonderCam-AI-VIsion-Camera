# WONDERCAM DRIVER - SPRINT PLAN

Status: CLOSED - 2026-06-05 (all 13 sections SHIPPED, build v0.1.0 compile-clean).
        Closeout audit: `DOCs/plans/archive/2026-06-05-WONDERCAM-DRIVER-Sprint-Closeout.md`.
        Behavioral hardware turn-on (L0-L5) follows the sprint (host-only).
Scope owner: Stephen

## Sprint start record (2026-06-05)

- **Build version:** v0.1.0 (the `VERSION` CON created in Section 2;
  `src/isp_wondercam.spin2`).
- **Working-tree audit:** clean and committed (HEAD at start `ebb3627`). Finding:
  the repo `.gitignore` ignored all of `.claude/`, leaving the methodology config
  (`skill-conventions.md` + overlays) un-versioned. Decision: track the config,
  keep local/transient `.claude` content ignored - fixed and committed in
  `ebb3627`.
- **Tracking-readiness entry check:** todo board empty (0 tasks); nothing to
  archive, no leftovers.
- **Baseline-health entry check (entry baseline):** greenfield - no source
  compiles yet (`src/` empty). Entry baseline = clean slate (no build, no tests).
  Exit baseline at closeout is the compile-clean sweep per the baseline-health
  overlay.
Authoritative requirements: `DOCs/spec/WonderCam-Driver-Requirements.md`
Device study: `DOCs/research/WONDERCAM-THEORY-OF-OPERATION.md`
Display technique: `DOCs/dbg-display-theory/`
Vendor reference (grounding citations below): `REF-NO-COMMIT/3. Multi-Controller
Communication Tutorial/3.2 Color Recognition/3.2.1 Arduino UNO/02 Program/
ColorDetect_RGB/WonderCam.cpp` (cited as `vendor WonderCam.cpp:NN`).

---

## Sprint goal

Build the COMPLETE v1: the full two-layer driver (all 11 vision applications),
the unified front-panel demo with its asset pipeline, the test infrastructure
(regression top + written bring-up playbook), and all documentation - to
**compile-clean** under pnut-ts. Behavioral correctness is proven afterward by a
bottom-up hardware turn-on (a follow-on, not part of this sprint's completion).

## Verification posture (applies to every section)

"First testing" for this sprint = **compiles clean under pnut-ts** (the
container path) and is structurally ready for the bench. Behavioral proof - does
the driver actually talk to the camera - is the deferred bottom-up turn-on
(Section 11's playbook, executed on the host). Each section below still names its
normal / edge / error cases so the regression top, the playbook, and turn-on
target them. Where a case can only be confirmed on hardware, it is tagged
`(turn-on)`.

## Inputs and dependencies

- **Provided tested I2C object** (Stephen to deliver) - the transport layer
  (Section 1) wraps it. Its exact object name and method signatures are pinned on
  receipt; Section 1 states the interface the wrapper needs so delivery and
  wrapper can meet in the middle.
- **No existing project code** - `src/` is empty; this is greenfield. "Current-code
  starting point" citations therefore point at the spec, the theory of operation,
  and the vendor reference rather than at project code.
- flexspin compatibility is **explicitly out of scope** (a post-certification
  compatibility pass). The driver targets pnut-ts only this sprint.

## Decisions locked at planning

- Driver and demo both target `{Spin2_v50}` (one version story; STRUCTs available).
- Multi-field results returned via caller-supplied `STRUCT` pointer; simple
  queries return values / error codes (authoring guide 5.4, 5.5).
- AprilTag pose exposed as 6 pass-through IEEE-754 floats.
- Bring-up playbook authored this sprint, executed at turn-on.
- High-level API corrects the vendor's confirmed bugs (does not re-port them).

---

## 1. I2C transport layer

**Why.** Every other layer depends on reaching the device correctly. This wraps
the provided tested I2C object with the WonderCam's framing: 16-bit
little-endian register addressing, chunked reads, and shared-bus locking.

**Starting point.** `vendor WonderCam.cpp:8-39` (`readFromAddr` / `writeToAddr`):
address is sent low byte then high byte (`:11-12`, `:36-37`); reads come back in
32-byte `requestFrom` transactions (`:18`, `:25`). Theory of operation Section 2.

**Target behavior.** Private `readFromAddr(addr, pBuf, len)` and
`writeToAddr(addr, pBuf, len)` that: send the 2-byte LE address (byte-order a
named constant per FR-7), then transfer `len` bytes; reads loop in `CHUNK`-byte
(default 32) transactions, with the chunk strategy (auto-increment vs
re-address-per-chunk) a named constant. Acquire/release the optional bus lock
around each transaction.

**Integration points.** Sits on the provided I2C object (byte-level
start/stop/write/read). Consumed by Sections 3, 4, 6, 7.

**Verification - normal/edge/error.**
- Normal: read 16 bytes @ 0x0000; write 1 byte @ 0x0030.
- Edge: read > 32 bytes (128 B classification region) spanning chunks; `len` not
  a multiple of 32 (last short chunk); `lockId = NO_LOCK` path vs held-lock path.
- Error: device NAK / no-ACK returns a specific error code, not a hang
  `(turn-on for true NAK behavior)`.

## 2. Register map and tunable constants (CON)

**Why.** No magic numbers (authoring guide 5.7); the unverified facts must live
as one-place-editable constants (FR-7) so turn-on findings update trivially.

**Starting point.** Theory of operation Section 4 (system registers; per-app
region bases, summary sizes, detail base +0x30, strides). `vendor
WonderCam.cpp:512-549` (per-mode summary read sizes).

**Target behavior.** Named CON for: I2C address (0x32); system registers
(0x0000 version, 0x0030 LED, 0x0035 mode); the 11 func numbers; each region base;
the +0x30 detail offset; the 16/32/4-byte strides; the +0x10 per-id table offset;
the /10000 probability divisor. Tunable group (FR-7): `ADDR_BYTE_ORDER`,
`READ_CHUNK`, `CHUNK_AUTOINCREMENT`, `TAG_RECORD_STRIDE`, contested func numbers
(color, number, landmark). `VERSION = 0.1.0`.

**Integration points.** Referenced everywhere; the single source of device-map
truth in code.

**Verification.** Compiles; every constant cross-checks against the theory of
operation Section 4 table (reviewer checklist). No behavioral case.

## 3. System control layer

**Why.** Mode selection, version, LED, and the result-latch cycle are the spine
the per-application API rides on.

**Starting point.** `vendor WonderCam.cpp:42-58` (version `:42-46`, currentFunc
`:48-53`, changeFunc `:56-72`), `:512-549` (updateResult per-mode summary reads).
Theory of operation Section 3.

**Target behavior.** `start(sdaPin, sclPin, busKHz, lockId)`; `stop()`;
`firmwareVersion(pStr)`; `setLed(bEnable)`; `setMode(funcId)` - writes 0x0035,
confirms the mode echo, bounded by a caller-visible timeout (mode change up to
~3 s); `currentMode()`; `updateResult()` - reads the active mode's summary
(48 B most modes, 64 B feature, 128 B classification). `setMode` (slow) and
`updateResult` (fast) are deliberately separate (spec FR-2).

**Integration points.** Uses Section 1 transport + Section 2 constants. Consumed
by Sections 6, 7, demo, regression.

**Verification - normal/edge/error.**
- Normal: set each of the 11 modes; read back the echo; read firmware version.
- Edge: `setMode` timeout path; first `updateResult` after a switch may see a
  stale/empty summary while the model spins up `(turn-on)`.
- Error: echo never matches -> specific error, no infinite wait.

## 4. Raw access API (full control)

**Why.** FR-1: nothing on the device is unreachable, even before a high-level
wrapper exists.

**Starting point.** Section 1 transport (this is its public face).

**Target behavior.** `readReg(addr, pBuf, len)` and `writeReg(addr, pBuf, len)`
public methods returning bytes-transferred or an error code.

**Integration points.** Thin passthrough over Section 1. Independent of the
high-level API.

**Verification - normal/edge/error.** Normal: read version, write LED via raw.
Edge: large raw read (shares Section 1's chunk path). Error: propagates
transport error codes unchanged (authoring guide 5.6).

## 5. Result-record STRUCT types (shared component)

**Why.** Face/object/color/line/AprilTag (and the classification-style payloads)
all return fixed-shape records. Defined ONCE as shared types used by the
high-level API, the demo, and the regression top (skill rule: plan shared from
the start, never "refactor to shared later").

**Starting point.** Theory of operation Section 4.4 (detail-record byte layouts);
`vendor WonderCam.h` struct definitions.

**Target behavior.** `STRUCT` types mirroring field order/width exactly:
spatial record (int16 x,y; uint16 w,h); line record (endpoints + angle + offset);
AprilTag record (int16 x,y; uint16 w,h; 6 floats). Coordinates sign-extended;
counts/confidence/length unsigned; payloads little-endian.

**Integration points.** Consumed by Sections 6, 7, 9, 10.

**Verification.** Compiles under `{Spin2_v50}`; field offsets match the theory of
operation Section 4.4 table.

## 6. High-level API - spatial-detection modes

**Why.** The ergonomic surface (spec FR-3) for the five modes that return boxes:
face, object, color, line-follow, AprilTag.

**Starting point.** `vendor WonderCam.cpp` per-app reads: face `:140-165`, object
`:221`, color `:452`, line `:500`, AprilTag `:332`. Theory of operation
Sections 5.1, 5.2, 5.5, 5.6, 5.9. Confirmed bugs to FIX (theory Section 7.3):
unlearned-face count cast, objDetected loop UB, getFaceOfIndex/tagId 1-based
pre-decrement, AprilTag `0x32` vs 32 stride.

**Target behavior.** Per mode, the natural family: `anyXDetected`, counts,
`xIdDetected(id)`, `getX(id[, index], pRec)` filling a Section 5 STRUCT. Face adds
learned/unlearned counts and by-index unlearned access. AprilTag adds pose +
`numTagsOfId`. Line returns raw endpoints and normalized angle/offset (keep the
raw-vs-box interpretation question open per theory Section 5.6).

**Integration points.** Uses Sections 3 (updateResult/summary) + 1 (detail reads)
+ 5 (records). Consumed by demo Section 9, regression Section 10.

**Verification - normal/edge/error.**
- Normal: decode one record per mode `(turn-on for real targets)`.
- Edge: zero detections; max count; id range bounds; 1-based vs 0-based index
  (the fixed bug); AprilTag stride read of index > 0 `(turn-on)`.
- Error: accessor called in the wrong active mode -> error code.

## 7. High-level API - classification-style modes

**Why.** Spec FR-3 for the six modes that return a class/payload, not boxes:
classification, feature-learning, number, road-sign, QR, barcode.

**Starting point.** Theory of operation Sections 5.3, 5.4, 5.7, 5.8, 5.10, 5.11.
`vendor WonderCam.cpp:372` (QR), `:406` (barcode), `:524`/`:528` (classification /
feature summaries). Number/road-sign have NO vendor C path - author from the
Python reference (`recognition.py`, `sign_recognition.py`); mark unverified.

**Target behavior.** Classification/feature/number/road-sign: `xTopId`,
`xTopProb` (raw/10000), `xProbOfId(id)`. QR/barcode: `xDetected`, `xLength`,
`xData(pBuf)` (payload up to 400 B). Number/road-sign read bases 0x0D00 / 0x0D80
behind clearly-labeled "single-sourced/unverified" comments.

**Integration points.** Uses Sections 1, 3. QR/barcode large payloads exercise
Section 1's chunk strategy. Consumed by demo Section 9, regression Section 10.

**Verification - normal/edge/error.**
- Normal: top-id + probability `(turn-on for real classes)`.
- Edge: no-detection sentinel (road-sign id=1 ambiguity, theory 5.11); payload
  spanning 32-byte chunks (depends on `CHUNK_AUTOINCREMENT`); empty payload.
- Error: wrong-mode accessor -> error; number/road-sign return a clear
  "unverified" status until turn-on.

## 8. Front-panel demo - framework and asset pipeline

**Why.** The unified interactive "software front panel" (spec Section 6); this is
the reusable skeleton all 11 mode-views (Section 9) plug into.

**Starting point.** `DOCs/dbg-display-theory/` - the crop-overlay technique,
the common skeleton (DISPLAY-PATTERNS Section 2), the host-windowed/agent-log
loop (HOWTO Section 2), and gotchas (`-b 2000000`, `abs()` not `||`, `>=` not
`=>`).

**Target behavior.** `src/demo_wondercam.spin2` (`{Spin2_v50}`): PLOT window
(`hidexy update`), layer loads, dirty-flag loop, `pc_key` mode cycling -> `setMode`,
`pc_key` LED toggle -> `setLed`, mode-name + status readout.
`tools/gen_wondercam_panel.py` (Python 3 + Pillow): emits 24-bit uncompressed
no-alpha BMPs (background, digit font strip, mode-name strip) AND prints the Spin2
CON layout block (single source of truth so art and code cannot drift). BMPs sit
in `src/`; source sets `DEBUG_BAUD = 2_000_000`.

**Integration points.** Drives the Section 3 + 6 + 7 driver API. Run is host-only
(p2-dev-cycle overlay).

**Verification - normal/edge/error.**
- Normal: compiles `-d`; generator output BMPs verified by BMP->PNG inspection;
  CON block matches the art `(window render + key input: turn-on on host)`.
- Edge: mode cycle wraps; window without focus ignores keys (documented).
- Error: missing BMP / wrong cwd surfaces clearly (run from `src/`).

## 9. Front-panel demo - per-mode views (all 11)

**Why.** Full-demo scope: every application visualized in the panel.

**Starting point.** Section 8 framework + Sections 6/7 API; DISPLAY-PATTERNS
Section 5 (vector overlay for boxes; font strips for readouts).

**Target behavior.** Spatial modes (face/object/color/line/AprilTag) draw live
**vector bounding boxes** in the camera-view region from each record's x/y/w/h
(the analog-meter `set`/`line` technique), with id labels. Classification-style
modes (classification/feature/number/road-sign/QR/barcode) render readout panels
(top-id, probability, payload-length). Each mode view is selected by the active
mode.

**Integration points.** One view per mode, all hung off the Section 8 dirty-flag
loop.

**Verification - normal/edge/error.**
- Normal: each mode's panel composes; box coords map correctly from x/y/w/h
  `(visual confirmation: turn-on)`.
- Edge: zero detections (clean frame); many detections (overlap); long payloads
  truncate gracefully in the readout.
- Error: a mode with no data shows an explicit "no detection" state, not stale art.

## 10. Regression top (`src/test_wondercam.spin2`)

**Why.** Spec Section 7.2: the automatable L0-L4 subset, re-runnable on every
driver change so capabilities are re-verified against hardware.

**Starting point.** Spec Section 7 (bring-up layers + regression split); the
driver API (Sections 3, 4, 6, 7).

**Target behavior.** A top that self-checks and emits pass/fail to the log: bus
ACK at 0x32 (L0), version-string sanity (L1), mode write/echo round-trip for all
11 (L2/L4), large-read integrity vs a known pattern (L3), per-mode summary-shape
sanity (L4). Explicitly NAMES anything it could not exercise (no silent coverage
gaps). L5 per-application decode stays the manual playbook (Section 11).

**Integration points.** Uses Sections 3/4/6/7 and Section 5 records.

**Verification - normal/edge/error.**
- Normal: all automatable checks emit PASS `(executed at turn-on, host)`.
- Edge: a check whose precondition is absent reports SKIPPED-and-named, never
  silent.
- Error: a failed check prints the expected-vs-actual, not just "fail".

## 11. Bring-up playbook (document, via `test-playbook`)

**Why.** Spec Section 7.1: the bottom-up, layer-by-layer bench procedure that
proves the hardware and retires the unverified facts; executed at turn-on.

**Starting point.** Spec Section 7.1 (L0-L5 table); theory of operation Section 8
(the 15 open questions each layer closes).

**Target behavior.** A numbered, pass/fail-keyed exercise document walking L0->L5,
each step naming what it proves, the expected observation, and which code constant
(Section 2) to update on the finding. Authored with the `test-playbook` skill.

**Verification.** Document review: every theory-of-operation open question maps to
a numbered step; every Section 2 tunable constant has a step that confirms it.

## 12. Driver Theory of Operations (document)

**Why.** Spec deliverable: how OUR driver works (distinct from the device study).

**Starting point.** Spec Sections 3, 5, 9; the as-built code from Sections 1-7.

**Target behavior.** A document covering the two-layer architecture, the
passive/polled/single-cog model, the shared-bus + lock contract, the result/cache
model, the configurable-unverified knobs, and the public API contract. Written
against the actual code so it is accurate, not aspirational.

**Verification.** Each public method in the as-built driver appears; each tunable
constant is explained.

## 13. Documentation currency

**Why.** Keeping project docs current is sprint work, not an afterthought.

**Starting point.** `DOCs/spec/WonderCam-Driver-Requirements.md`,
`DOCs/process/WonderCam-Process-History.md`, `README.md`.

**Target behavior.** Update SPEC_DOC status and fold in the decisions locked here
(provided-I2C-object dependency; flexspin deferred post-certification). Append the
Process/History "Phase 5 - Implementation" annotations as work lands. Refresh the
README status line if the planned layout changes. (No help / manual / style-guide
slots are set for this project, so those deliverables do not apply.)

**Verification.** Docs reflect the as-built state; no stale "src/ is empty" claims.

---

## Out of scope (this sprint)

- flexspin compatibility (post-certification pass).
- Executing the bring-up on hardware (the turn-on follows the sprint).
- On-device enrollment, raw frame transfer, camera config (device exposes none).
- Permanent FLASH release programming.

---

## Section -> Task cross-reference

Generated by `plan-to-tasks` (2026-06-05). Sprint tag: `wc-driver-v1`. Build: v0.1.0.
`seq` is the execution order (`todo_next` walks it); it is foundational -> dependent.

| Plan section | Deliverable | Task | seq |
| --- | --- | --- | --- |
| Section 2 | Register map + tunable constants (CON) | «#1» | 1 |
| Section 1 | I2C transport layer (wraps provided I2C object) | «#2» | 2 |
| Section 3 | System control (start/version/LED/setMode/updateResult) | «#3» | 3 |
| Section 4 | Raw access API (readReg/writeReg) | «#4» | 4 |
| Section 5 | Result-record STRUCTs (shared) | «#5» | 5 |
| Section 6 | High-level API - spatial modes (face/object/color/line/tag) | «#6» | 6 |
| Section 7 | High-level API - classification modes (class/feature/number/road-sign/QR/barcode) | «#7» | 7 |
| Section 8 | Front-panel demo - framework + asset pipeline | «#8» | 8 |
| Section 9 | Front-panel demo - per-mode views (all 11) | «#9» | 9 |
| Section 10 | Regression top (test_wondercam.spin2) | «#10» | 10 |
| Section 11 | Bring-up playbook (doc, via test-playbook) | «#11» | 11 |
| Section 12 | Driver Theory of Operations (doc) | «#12» | 12 |
| Section 13 | Documentation currency | «#13» | 13 |

Note: execution order differs from the plan's narrative section order - Section 2
(constants) is foundational and runs first, then Section 1 (transport), etc.
