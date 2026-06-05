# WonderCam P2 Spin2 Driver - Requirements and Specification

Status: IMPLEMENTED (v0.1.0) - as-built 2026-06-05; supersedes DRAFT v0.1 (2026-06-04)
Owner: Stephen (stephen@ironsheep.biz)
Supersedes: nothing (initial requirements)

This document turns the device study in
`DOCs/research/WONDERCAM-THEORY-OF-OPERATION.md` into a buildable driver spec.
It defines WHAT the driver must do and the shape of its public API; it does not
contain Spin2 implementation. Hex addresses, struct layouts, and the per-mode
result map are owned by the theory of operation and referenced here rather than
duplicated.

**As-built (2026-06-05).** The v0.1.0 driver, demo, and regression top are
implemented and compile clean under pnut-ts in the container; on-hardware bring-up
(the Section 7 L0-L5 work) is the host-only turn-on that follows. Two decisions
locked during implementation refine the requirements below and are noted inline:
- **Provided I2C object dependency.** The driver does not embed its own
  bit-banged I2C. It composes a provided singleton I2C object
  (`src/isp_i2c_singleton.spin2`) that it OWNS and configures as a dedicated bus.
  This satisfies FR-5's bus model minus the optional lock (see 3.3 / FR-5).
- **flexspin compat deferred.** The secondary portability compile under flexspin
  (NFR-3 / Section 11) is DEFERRED to a post-certification pass; v0.1.0 acceptance
  rests on pnut-ts compile-clean plus the host bring-up. flexspin is host-only and
  is not a v0.1.0 gate.

---

## 1. Purpose and scope

Build a Parallax Propeller 2 (P2) Spin2 driver for the Hiwonder WonderCam AI
vision camera (I2C, address 0x32). The vendor ships drivers for Arduino, ESP32,
STM32, Raspberry Pi, and C51 but not the P2; this fills that gap.

**North star:** the driver lands on another robot, dropped into a mix of I2C
sensors. Simplicity of integration and safe bus-sharing are first-class
constraints, not afterthoughts.

**In scope (v1):**
- Full, register-level control of the device (nothing on the device unreachable).
- An ergonomic high-level API over all 11 vision applications.
- A single unified interactive DEBUG "front panel" demo.
- A bottom-up hardware bring-up test plan plus an automatable regression top.
- Two companion documents (driver theory of operation; process/history).

**Out of scope (v1):** raw image / frame-buffer transfer (the device exposes no
streaming register); on-device enrollment of faces/colors/features (camera-UI
only); camera configuration registers (none found); permanent FLASH release
programming (a separate concern from this driver).

---

## 2. Source of truth and the caveats we must carry

The theory of operation is authoritative for the wire protocol and memory map.
Two classes of findings shape these requirements directly:

**Confirmed vendor-code bugs** - the high-level API MUST implement CORRECT
behavior, not faithfully re-port these:
- `numOfTotalUnlearnedFaceDetected()` returns a pointer cast instead of the byte.
- `objDetected()` loop can run off the end (UB).
- `getFaceOfIndex()` / `tagId()` use pre-decrement-then-zero (1-based indexing).
- AprilTag `tagId()` advances 0x32 = 50 bytes/record while the record is 32 bytes.
- Number/landmark accessor methods are declared but never defined (link failure).

**Single-sourced / hardware-unverified facts** - each is retired by a specific
bring-up layer (Section 7) and must be a named, overridable constant until then:
- I2C address 0x32; register address byte-order (low-first per code vs PDF prose).
- Chunk auto-increment across 32-byte reads (gates ALL reads > 32 bytes).
- Color = func 5; object class id 20; AprilTag summary off-by-one and stride.
- Number base 0x0D00 / landmark base 0x0D80 (Python-only).
- Line-follow first four int16 = endpoints (Arduino) vs box (Python).
- Landmark id-to-meaning map (Arduino 1..5 vs Python 1=none,2..6).

---

## 3. Architecture

### 3.1 Two layers, one object

`src/isp_wondercam.spin2` exposes the device in two layers:

```
+-------------------------------------------------------------+
|  HIGH LEVEL (ergonomic) - per-application PUB methods        |
|  anyFaceDetected, getColor, getTag, classTopId, ...          |
|  corrects vendor bugs; returns decoded values / error codes  |
+-------------------------------------------------------------+
|  LOW LEVEL (full control) - every register reachable         |
|  readReg / writeReg primitives + named CON for every         |
|  register, region base, offset, stride, func number          |
+-------------------------------------------------------------+
|  I2C transport - smart-pin I2C, caller-set pins, opt. lock   |
+-------------------------------------------------------------+
```

The low level satisfies "full control of the device, all registers." The high
level satisfies "simplified, natural API." A caller can stay entirely in the
high level, drop to the low level for anything not yet wrapped, or mix.

### 3.2 Execution model: passive, polled, single-cog

The driver is a passive object. It launches NO background cog. The caller drives
it synchronously from its own cog: `setMode`, then per frame `updateResult`
followed by result accessors. This matches the "polled / interactive, not a
backend service" intent and keeps the object trivial to add to a robot's
existing cog layout.

### 3.3 Shared I2C bus coexistence

The driver MUST be usable on a bus shared with other I2C devices:
- The caller supplies the SDA and SCL pin numbers and the bus speed at `start`.
- The driver accepts an OPTIONAL bus lock (a P2 lock id, or "no lock"). When
  given, every I2C transaction acquires/releases it so concurrent drivers on
  the same bus do not interleave transfers.
- The driver assumes nothing about pull-ups or exclusive ownership of the pins.

**As-built (v0.1.0):** the driver composes a provided singleton I2C object
(`src/isp_i2c_singleton.spin2`) that it OWNS and configures as a DEDICATED bus,
and v0.1.0 ships WITHOUT the optional lock - `start` configures its own bus and
no `lockId` is taken. The shared-bus lock is deferred (decision 2026-06-05,
tracked in `DOCs/plans/PUNCH-LIST.md`); the own-instance object already satisfies
the bus-model half of this requirement, leaving only the lock to add when a
deployment actually shares the bus.

### 3.4 Spin2 / pnut-ts version posture

The driver targets pnut-ts (see `.claude/skill-conventions.md`). Typed pointers
and `STRUCT` result records require the appropriate `{Spin2_v##}` directive per
the authoring guide. The demo requires `{Spin2_v50}` for DEBUG PLOT layer/crop.

---

## 4. Functional requirements

- **FR-1 Full register access.** Every register, region base, per-record offset,
  stride, and function number documented in the theory of operation is a named
  CON. `readReg(addr, pBuf, len)` and `writeReg(addr, pBuf, len)` reach any
  address. No device-side capability is gated behind "we didn't wrap it."

- **FR-2 System control.** `start` (I2C pins, speed, optional lock); `stop`;
  `firmwareVersion`; `setLed(on)`; `setMode(func)` and `currentMode` (with the
  0x0035 mode-echo readiness check); `updateResult` (latches the active mode's
  summary). `setMode` is potentially slow (mode change up to ~3 s) and MUST be
  bounded by a caller-visible timeout, separate from the fast poll path.

- **FR-3 High-level API for all 11 applications.** Face, object, classification,
  feature-learning, color, line-follow, AprilTag (with 6-DoF pose), QR, barcode,
  number, road-sign. Each exposes the natural "presence / count / by-id /
  by-index / get-record" family appropriate to that mode (Section 5). Number and
  road-sign read logic is authored from the Python reference (no vendor C path)
  and is clearly marked unverified until bring-up Layer 5.

- **FR-4 Bug corrections.** The five confirmed vendor bugs in Section 2 are fixed
  in the high level. Each fix is commented with the vendor behavior it replaces.

- **FR-5 Result records.** Detection results are returned as decoded values or
  filled `STRUCT` records (coordinates sign-extended int16; counts / confidence /
  length unsigned; AprilTag pose as floats; multi-byte payloads little-endian).
  Confidence/probability is normalized (raw / 10000.0) at the high level.

- **FR-6 Error model.** Per the authoring guide, API methods return error CODES,
  not bare booleans. Define a small named-constant set (e.g. success >= 0;
  negative = specific error: NAK / wrong-mode / timeout / bad-arg). Specific
  errors are never overwritten by generic ones. Boolean-by-nature queries
  (`anyFaceDetected`) return TRUE/FALSE explicitly.

- **FR-7 Configurable unverified behavior.** Address byte-order, the read-chunk
  strategy (auto-increment vs re-address-per-chunk), the AprilTag record stride,
  and the contested func numbers are named constants with documented defaults,
  changeable in one place after bring-up confirms the hardware truth.

- **FR-8 Versioning.** A `VERSION` CON in the driver, starting at 0.1.0.

---

## 5. Public API surface (proposed shape)

Natural, standard-looking; final signatures settle during implementation. Names
avoid the authoring guide's known collisions.

> **As-built note (v0.1.0).** This section is the PROPOSED shape; the binding
> as-built API contract lives in `DOCs/WonderCam-Driver-Theory-of-Operation.md`.
> One signature settled differently: `start` takes a bus-pullup flag rather than a
> `lockId` (the driver owns a dedicated bus and the shared-bus lock is deferred -
> see 3.3), i.e. `start(sclPin, sdaPin, busKHz, pullup)`.

**Lifecycle / system**
```
start(sdaPin, sclPin, busKHz, lockId) : status   ' lockId = NO_LOCK to skip locking
stop()
firmwareVersion(pStr) : status
setLed(bEnable)
setMode(funcId) : status                          ' bounded, confirms 0x0035 echo
currentMode() : funcId
updateResult() : status                           ' latch active mode summary
```

**Raw (full control)**
```
readReg(addr, pBuf, len) : countOrError
writeReg(addr, pBuf, len) : countOrError
```

**Per-application (illustrative; one family per mode, all 11 present)**
```
' Face
anyFaceDetected() : bTRUE_FALSE
numFaces() / numLearned() / numUnlearned() : count
getFaceById(id, pRec) : status
getUnlearnedFace(index, pRec) : status
' Object
anyObject() / numObjects() / numObjectsOfId(id) : count
getObject(id, index, pRec) : status
' Classification / Feature / Number / Road-sign (classification-shaped)
classTopId() / classTopProb() / classProbOfId(id)
featureTopId() / featureTopProb() / featureProbOfId(id)
numberTopId() / numberTopProb()           ' marked unverified until Layer 5
landmarkTopId() / landmarkTopProb()        ' marked unverified until Layer 5
' Color
anyColor() / numColors() / colorIdDetected(id) ; getColor(id, pRec)
' Line follow
anyLine() / numLines() ; getLine(id, pRec)         ' raw + normalized angle/offset
' AprilTag
anyTag() / numTags() / numTagsOfId(id) ; getTag(id, index, pRec)   ' x,y,w,h + pose
' QR / Barcode
qrDetected() / qrLength() / qrData(pBuf)
barcodeDetected() / barcodeLength() / barcodeData(pBuf)
```

Result records (`STRUCT`) mirror the theory of operation's field order and widths
exactly. The high level reads the cached summary; detail records are fetched on
demand, not inside `updateResult`.

---

## 6. Demo: the unified DEBUG "front panel"

`src/demo_wondercam.spin2`, a `{Spin2_v50}` DEBUG PLOT instrument window built
with the crop-and-overlay (sprite-blit) technique documented in
`DOCs/dbg-display-theory/`. One window, all modes - a software front panel for
the driver.

### 6.1 What it shows
- **Mode selector + status** - active application name (word-strip sprite,
  Pattern A/B) and the live device mode echo; `pc_key` cycles modes, mapping to
  `setMode`.
- **Live result region ("camera view")** - a framed area where detections are
  drawn as **vector bounding boxes** (`set`/`line`, the analog-meter needle
  technique) from each detection's x/y/w/h, plus id labels.
- **Numeric readouts** - counts, ids, confidence/probability, AprilTag pose, QR/
  barcode text length - as **font-strip** digit blits (Pattern B).
- **LED toggle and help footer** - `pc_key` toggles `setLed`; static footer art.

### 6.2 Asset pipeline
- `tools/gen_wondercam_panel.py` (Python 3 + Pillow) generates 24-bit
  uncompressed no-alpha BMPs (background, font strips, mode-name strips) AND
  prints a ready-to-paste Spin2 `CON` layout block - layout is single-source in
  the generator so art and code cannot drift.
- BMPs live next to the `.spin2` source; the windowed terminal runs from `src/`.

### 6.3 Interaction loop and dual-environment fit
- Dirty-flag loop: poll camera (`updateResult` + accessors) and `pc_key`/
  `pc_mouse`; recompose and `update` only on change; flicker-free via double
  buffering.
- The WINDOWED terminal run is HOST-ONLY (`pnut-term-ts -r ... -b 2000000`); the
  agent compiles in-container, generates BMPs, verifies art by converting BMP to
  PNG, and reads `src/logs/debug_*.log` to see what the operator saw. (Matches
  the p2-dev-cycle overlay's host-only flash/run rule.)
- Source sets `DEBUG_BAUD = 2_000_000` (matches `P2_DEBUG_BAUD`); known pnut-ts
  gotchas from the display docs apply (`abs()` not `||`, `>=` not `=>`).

---

## 7. Test strategy

Two complementary tracks: a one-time bottom-up bring-up that PROVES the hardware
layer by layer (and retires the unverified facts), and a repeatable regression
top for the automatable subset.

### 7.1 Bottom-up hardware bring-up (host; proposed layering)

Each layer is verified before the next is trusted; after each, the driver's
constants/expectations are updated to the proven hardware truth. Reorder/split
as bench experience dictates.

| Layer | Proves | Retires | Auto? |
|-------|--------|---------|-------|
| L0 Bus presence | device ACKs at 0x32 (wiring, pull-ups, address) | addr 0x32 | yes (ACK probe) |
| L1 Register read | firmware version @0x0000 reads sane ASCII -> 16-bit framing AND address byte-order | byte-order | yes (sane string) |
| L2 Register write + echo | LED @0x0030 (eyeball) and mode write/echo @0x0035 | write path, mode readiness | partial (echo auto) |
| L3 Chunked read > 32B | a 128B region / payload reads intact -> chunk auto-increment vs re-address | chunk strategy (gates all big reads) | yes (integrity vs known bytes) |
| L4 Mode select + latch | `updateResult` summary header + counts per mode | summary off-by-ones | partial |
| L5 Per-app decode | known targets in frame -> each mode's record decodes correctly | color=5, number/landmark bases, AprilTag stride, line endpoints-vs-box, landmark id map | manual (needs targets) |

### 7.2 Regression top (`src/test_wondercam.spin2`)

The automatable subset of L0-L4 built so EVERY driver change can re-verify
capabilities against hardware on the host: bus ACK, version sanity, mode
write/echo round-trip, large-read integrity against a known pattern, and per-mode
summary-shape checks. Self-checks emit pass/fail to the log. L5 per-application
decode stays a manual playbook (authored later with the `test-playbook` skill)
because it needs physical faces/tags/colors/etc. in front of the lens. The
regression top names anything it could NOT exercise (no silent coverage gaps).

### 7.3 Compile-clean baseline (container)

Per the `baseline-health` overlay: `BUILD_COMMAND` compiles the demo top and
`TEST_COMMAND` compiles the regression top; a "failing test" in-container is a
non-compiling object; behavioral health is the L0-L5 hardware work above. The
flexspin compat compile (portability check) is host-only.

---

## 8. Non-functional requirements

- **NFR-1 Authoring-guide conformance.** Every `.spin2` file obeys
  `DOCs/policy/SPIN2-AUTHORING-GUIDE.md` (a hard gate; see the p2-dev-cycle
  overlay). ASCII-only, error-code returns, single exit, named constants, etc.
- **NFR-2 Dual-environment discipline.** Compile in the container; flash/run and
  flexspin compat on the macOS host. The driver must not assume a runtime tool
  that the container lacks.
- **NFR-3 Reuse / portability.** The driver object is dependency-light (it
  composes only the provided `isp_i2c_singleton` object) so it drops into the
  robot's sensor mix. It compiles clean under pnut-ts; the flexspin
  compat-compile is DEFERRED to a post-certification pass (host-only) and is not
  a v0.1.0 gate.
- **NFR-4 Documentation parity.** Public methods carry doc-comments per the
  authoring guide; result-record `STRUCT`s are documented with field units.

---

## 9. Deliverables

1. `src/isp_wondercam.spin2` - the two-layer driver (`VERSION` CON).
2. `src/demo_wondercam.spin2` (+ `tools/gen_wondercam_panel.py` + BMP assets) -
   the unified front-panel demo.
3. `src/test_wondercam.spin2` - the regression top (Section 7.2).
4. Bring-up test plan / playbook (Section 7.1), authored with `test-playbook`.
5. **Driver Theory of Operations** - how our driver works (distinct from the
   device theory of operation): layering, API contract, result model, the
   configurable-unverified knobs, bus/cog model.
6. **Process / history document** - narrative from repo creation -> skills
   adoption -> vendor-code research (multi-agent study) -> driver development;
   annotated as the project proceeds.

---

## 10. Open questions and risks (carried from the theory of operation)

The 15 open questions in `WONDERCAM-THEORY-OF-OPERATION.md` Section 8 remain
open until their bring-up layer (Section 7.1) closes them. Highest risk:
- **Chunk auto-increment (L3)** - if false, every read > 32 bytes corrupts; the
  configurable chunk strategy (FR-7) is the mitigation.
- **Address byte-order (L1)** - wrong order makes every transaction read garbage.
- **Mode-switch settling (L4)** - first `updateResult` calls after `setMode` may
  return stale/empty summaries while the model spins up.

These are why the test strategy verifies bottom-up before the high-level API is
trusted.

---

## 11. Acceptance (v1)

- Driver compiles clean under pnut-ts (container). flexspin compat-compile is
  deferred to a post-certification pass (host-only) - not a v0.1.0 gate.
- Full register access demonstrated (read version, toggle LED, switch modes, read
  each region) via the regression top.
- High-level API present for all 11 applications; the five vendor bugs corrected.
- Unified front-panel demo renders and switches modes on the host bench.
- Bring-up L0-L4 pass on hardware; L5 exercised for the applications with
  available physical targets; any unexercised app named explicitly.
- Driver Theory of Operations and Process/history documents exist and are current.
