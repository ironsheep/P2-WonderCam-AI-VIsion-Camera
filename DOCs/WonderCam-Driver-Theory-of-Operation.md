# WonderCam P2 Driver - Theory of Operation

**Driver:** `src/isp_wondercam.spin2` - `VERSION = 0_01_00` (v0.1.0)
**Audience:** P2 developers integrating the driver.
**Scope:** how *this driver* works. It is the companion to - and deliberately distinct from - the *device* study in `DOCs/research/WONDERCAM-THEORY-OF-OPERATION.md` (which describes how the **camera** behaves). This document describes how the **Spin2 object** is structured, what contract it offers a caller, and which of its behaviors are still UNVERIFIED pending the hardware bring-up.

> **Status:** written against the as-built v0.1.0 code, not an aspiration. Behavioral facts marked UNVERIFIED are confirmed/corrected by the bring-up playbook (`DOCs/plans/WONDERCAM-DRIVER-BRINGUP-PLAYBOOK.md`); the automatable subset is re-checked by the regression top (`src/test_wondercam.spin2`).

---

## 1. Purpose and scope

The WonderCam is an I2C smart camera (Kendryte K210 + OV2640) that runs eleven on-device vision applications - face, object, image-classification, feature-learning, color, line-follow, AprilTag, QR, barcode, number, and road-sign (landmark) recognition. The driver gives a P2 program two things at once:

1. **Total reach** - raw 16-bit register read/write, so nothing on the device is unreachable.
2. **Ergonomics** - a per-application method family (`anyFaceDetected`, `numTags`, `qrData`, ...) that hides the register map, the chunked-read mechanics, and the per-mode record layouts behind intent-named calls returning decoded values.

What the driver is **not**: it is not a background service, it spawns no cog, it does not own a frame buffer, and it does not interpret the camera's video. It is a passive, polled accessor that the caller drives.

---

## 2. Two-layer architecture

The object is built as two layers in one file:

```
        caller (your top object)
              |
   +----------------------------+   LAYER 2: ergonomic 11-application API
   |  anyFaceDetected, numTags, |   - decodes summary + detail records
   |  getObject, qrData, ...     |   - per-mode getters fill STRUCTs
   |  setMode, updateResult, ... |   - returns decoded values + error codes
   +----------------------------+
              |
   +----------------------------+   LAYER 1: raw register transport
   |  readReg / writeReg (public)|   - 16-bit addressed reg read/write
   |  readFromAddr/writeToAddr   |   - chunk strategy, address byte order
   +----------------------------+
              |
        i2c : "isp_i2c_singleton"     low-level I2C (start/stop/wr_block/rd_block)
              |
           WonderCam @ 0x32
```

- **Layer 1 (transport).** `readReg(addr, pBuf, len)` and `writeReg(addr, pBuf, len)` are thin public passthroughs over the private `readFromAddr` / `writeToAddr`. Every device register stays reachable even if a high-level wrapper does not exist for it. Transport returns a byte count (`>= 0`) on success or `E_NAK`; the passthrough never rewrites a specific transport error into a generic one.
- **Layer 2 (application API).** The per-application methods sit on top of the transport plus the summary cache (section 5). They translate the device's register/record conventions into decoded counts, ids, coordinates, probabilities, and payloads, and they return the driver's error-code vocabulary (section 7.1).

The two layers coexist deliberately: a caller can stay entirely in Layer 2 for normal use, drop to Layer 1 for a register the API doesn't wrap, and mix the two freely.

---

## 3. Execution model - passive, polled, single-cog

The driver runs **entirely in the caller's cog**. There is no `cognew`/`coginit` anywhere in the object; every method executes synchronously and returns to the caller.

- **Passive.** The driver never acts on its own. Nothing happens between calls.
- **Polled.** The caller decides when to refresh device state (`updateResult()`) and when to read decoded results (the accessors). A typical loop: `setMode` once, then repeatedly `updateResult()` + accessors.
- **Single-cog / re-entrancy.** Because all state is instance VAR (`modeActive`, `summBuffer`) and the bus is driven inline, a single driver instance is meant to be driven from **one** cog. Two cogs sharing one instance would race the summary cache and the bus; give each cog its own instance on its own bus, or serialize access in the caller.
- **Blocking calls.** Most calls are bus-transaction-short. The exception is `setMode()`, which polls the device's mode echo and can block up to roughly `MODE_SETTLE_MS + MODE_POLL_MAX * MODE_POLL_MS` (~4 s worst case) while the on-device model swaps. This is bounded - an unresponsive device returns `E_MODE`, never hangs (section 5).

---

## 4. I2C bus contract

- **The driver owns a dedicated bus.** `start(sclPin, sdaPin, busKHz, pullup)` calls `i2c.setup(...)` and configures the bus itself. v0.1.0 assumes this bus is the driver's exclusively.
- **No bus lock in v0.1.0.** There is no lock id and no arbitration. Shared-bus locking is a known deferral, tracked in `DOCs/plans/PUNCH-LIST.md` (spec FR-5). If another device must share these pins, that locking layer has to land first; until then, the dedicated-bus assumption is a hard precondition.
- **Address probe at start.** `start()` issues a presence probe (`i2c.present(CAM_ADDR_WR)`); it returns `E_OK` if the camera ACKs its address byte (`$64`), `E_NAK` if absent. Either way it forms a STOP to leave the lines idle-high. Allow the camera's power-on boot to finish before calling `start()`.
- **Transaction shape.** Every register access sends the **16-bit register address first** (two bytes, order set by `ADDR_LOW_FIRST`, default low-byte-first), then transfers the payload. Reads use a repeated-start into the read phase.
- **Chunking.** Reads larger than one I2C chunk are governed by `CHUNK_AUTOINC` (section 6): `TRUE` does one continuous `rd_block`; `FALSE` re-addresses the device before each `READ_CHUNK`-byte chunk. This is the single most consequential unverified behavior - it gates every read over 32 bytes (classification summary 128 B, feature 64 B, QR/barcode payloads up to 400 B).
- **stop().** Releases the bus by forming a STOP. The driver holds no cog or other resource, so there is nothing else to tear down.

---

## 5. Result and summary-cache model

The driver mirrors the device's own two-step result protocol, and keeps the slow and fast paths separate (spec FR-2):

- **`setMode(funcId)` - the slow path.** Writes `REG_FUNC` ($0035) then **polls the read-back echo** until the device reports it adopted the mode (the model swap can take seconds). The poll is bounded by `MODE_POLL_MAX`; if the echo never matches, it returns `E_MODE` rather than hanging. Call this once per mode change, not in the hot loop.
- **`updateResult()` - the fast path.** Reads `REG_FUNC` to learn the active mode, then reads **that mode's summary region** into the instance buffer `summBuffer` at the mode's summary size (classification 128 B, feature 64 B, every other mode 48 B). This is the per-frame poll. It latches a snapshot; it does not decode.
- **Accessors read the cache.** Every `any*` / `num*` / `*Detected` / `get*` / `*TopId` / `*TopProb` / `*Length` call reads the **latched `summBuffer`** - it does **not** re-touch the bus for summary data. `guardMode()` checks the call against `modeActive` (the last mode `updateResult`/`currentMode` saw) and returns `E_MODE` if the caller asks a face question while object mode is latched. This is why accessors are cheap and why `updateResult()` must be called first.
- **Detail records are fetched on demand.** Bounding-box / pose / payload records are **not** in the summary. A `get*` accessor finds the record's slot in the latched summary's id-list, then issues a fresh transport read for just that record (`base + DETAIL_OFFS + slot * stride`) into the caller's STRUCT or buffer. So the cost model is: one cheap summary read per frame, plus one small detail read per record actually requested.

```
   setMode(FUNC_FACE)          // slow: write 0x0035, poll echo (once)
   repeat
     updateResult()            // fast: latch 48 B summary into summBuffer
     if anyFaceDetected()      // cheap: reads summBuffer[count]
       getFaceById(id, @rec)   // on-demand: one detail read into rec
```

---

## 6. The FR-7 configurable-but-unverified knobs

Several device behaviors are corroborated only by the vendor *code* (not the PDF), or differ between vendor sources. The driver encodes its best reading as a **named constant in one place**, so hardware bring-up can correct any of them without touching logic. Each is retired by a specific bring-up step (see the playbook's coverage matrix).

| Knob (CON in `isp_wondercam.spin2`) | Default | Meaning / why unverified | Retired by |
| --- | --- | --- | --- |
| `ADDR_LOW_FIRST` | `TRUE` | 16-bit register address byte order. Code sends low byte first; PDF prose contradicts. Wrong order makes every transaction read garbage. | playbook L1.1 |
| `READ_CHUNK` | `32` | Bytes per I2C read transaction (vendor uses 32). | playbook L3.1 |
| `CHUNK_AUTOINC` | `TRUE` | Does the device auto-increment its read pointer across chunk reads? If false, every read > 32 B corrupts unless the driver re-addresses. Gates all big reads. | playbook L3.1 (+ L5.8 known QR payload) |
| `TAG_REC_STRIDE` | `32` | AprilTag per-record advance. The vendor `tagId()` used `0x32 = 50` (a hex/decimal typo); the record is 32 B. | playbook L5.5 |
| `FUNC_COLOR` | `5` | Color function number - code only; PDF omits it. | playbook L5.3 |
| `FUNC_NUMBER` | `10` | Number-recognition function number - Python-only source, no vendor C path. | playbook L5.10 |
| `FUNC_LANDMARK` | `11` | Road-sign (landmark) function number - Python-only source, no vendor C path. | playbook L5.11 |

Two related correctness notes the API surface carries:

- **Fixed vendor bugs.** The driver corrects five confirmed vendor bugs rather than re-porting them (unlearned-face count read as a byte not a pointer; object loop running off the end; 1-based pre-decrement indexing in `getFaceOfIndex`/`tagId`; the AprilTag stride typo). Each fix is commented in the code with the vendor behavior it replaces.
- **UNVERIFIED modes.** `numberTopId/Prob` and `landmarkTopId/Prob` are authored from the Python reference with no vendor C path; they are labeled UNVERIFIED until bring-up L5 flips them to verified-or-removed. The landmark id map additionally has a "1 = none vs 1 = a valid sign" ambiguity to resolve on hardware.

---

## 7. Public API contract

### 7.1 Return-value and error model

PUB methods return **error codes, not booleans**, except the predicates that are boolean by nature.

| Code | Value | Meaning |
| --- | --- | --- |
| `E_OK` | 0 | success (read/write also return a byte count `>= 0`) |
| `E_NAK` | -1 | device did not acknowledge (bus failure) |
| `E_ARG` | -2 | invalid argument |
| `E_MODE` | -3 | operation not valid for the latched active mode |
| `E_NOTFOUND` | -4 | requested id/index absent in this frame's latched results |

- **Counts and `get*`** return a non-negative success value (a count, a byte count, or `E_OK`) **or** a negative error code. A caller tests `>= 0` for success.
- **`any*` / `*Detected`** are true predicates: they return canonical `TRUE`/`FALSE`, and `FALSE` when the mode is not active (they never error).
- **Probabilities** are returned as a **scaled integer `0..PROB_DIVISOR` (10000)**: `raw / 10000` = `0.0..1.0`. A negative value is an error code. This keeps the driver float-free and lets the return double as value-or-error; a caller wanting a float computes `FLOAT(prob) /. FLOAT(PROB_DIVISOR)`.
- **Error propagation** never overwrites a specific transport error with a generic one.
- **Method conventions** (per the authoring guide): every method name is unique (no overloading), single exit point, loops exit with `quit` not `return`, no magic numbers.

### 7.2 Decoded record STRUCT types

Defined once in the driver (requires `{Spin2_v50}`), auto-exported to parents (e.g. `cam.spatial_result_t`), and shared by the API, the demo, and the regression top:

| STRUCT | Size | Fields | Used by |
| --- | --- | --- | --- |
| `spatial_result_t` | 8 B | `WORD x, y, w, h` | face / object / color box |
| `line_result_t` | 12 B | `WORD start_x, start_y, end_x, end_y, angle, offset` | line follow |
| `tag_result_t` | 32 B | `WORD x, y, w, h` + `LONG x_t, x_r, y_t, y_r, z_t, z_r` | AprilTag (+ 6 pose floats) |

Reading conventions: the device sends each multi-byte field little-endian and the P2 is little-endian, so a bulk record read lands field-aligned. **Signed `int16` coordinates are stored as `WORD`** (unsigned) - sign-extend with `value SIGNX 15` when reading into a 32-bit value. **Pose fields are `LONG`** holding the raw IEEE-754 bit pattern - treat as `FLOAT` at use.

### 7.3 System and transport methods

| Method | Returns | Notes |
| --- | --- | --- |
| `null()` | - | marker; this is not a top-level object |
| `start(sclPin, sdaPin, busKHz, pullup)` | `E_OK`/`E_NAK` | configures the dedicated bus, probes for the camera |
| `stop()` | `E_OK` | releases the bus (STOP) |
| `firmwareVersion(pStr)` | byte count (16) / `E_NAK` | 16 ASCII bytes at `REG_FW_VERSION`, not NUL-terminated |
| `setLed(bEnable)` | byte count / `E_NAK` | fill light on (nonzero) / off |
| `setMode(funcId)` | `E_OK`/`E_ARG`/`E_NAK`/`E_MODE` | slow path: write `REG_FUNC`, poll echo (bounded) |
| `currentMode()` | mode id / `E_NAK` | reads `REG_FUNC`, caches `modeActive` |
| `updateResult()` | summary byte count / `E_NAK` / `E_MODE` | fast path: latch active-mode summary |
| `readReg(regAddr, pBuf, byteCount)` | byte count / `E_NAK` | raw read (Layer 1) |
| `writeReg(regAddr, pBuf, byteCount)` | byte count / `E_NAK` | raw write (Layer 1) |

### 7.4 Spatial-detection API (face / object / color / line / AprilTag)

All read the summary latched by the most recent `updateResult()`; coordinates land in the caller's STRUCT.

| Mode | Methods |
| --- | --- |
| Face | `anyFaceDetected()`, `numFaces()`, `numLearned()`, `numUnlearned()`, `faceIdDetected(id)`, `getFaceById(id, pRec)`, `getUnlearnedFace(index, pRec)` |
| Object | `anyObject()`, `numObjects()`, `objectIdDetected(id)`, `numObjectsOfId(id)`, `getObject(id, index, pRec)` |
| Color | `anyColor()`, `numColors()`, `colorIdDetected(id)`, `getColor(id, pRec)` |
| Line | `anyLine()`, `numLines()`, `lineIdDetected(id)`, `getLine(id, pRec)` |
| AprilTag | `anyTag()`, `numTags()`, `tagIdDetected(id)`, `numTagsOfId(id)`, `getTag(id, index, pRec)` |

Family conventions: `any*` -> boolean; `num*` -> count or `E_MODE`; `*IdDetected` -> boolean; `get*` -> `E_OK`/`E_MODE`/`E_NOTFOUND`/`E_NAK` (plus `E_ARG` where an `index` is taken). Face adds learned/unlearned counts and by-index unlearned access; AprilTag adds `numTagsOfId` and the 6-float pose; `getObject`/`getTag` take a 0-based `index` to reach multiple records of one id; `getLine` returns raw endpoints plus normalized angle/offset (the endpoints-vs-box interpretation stays open until bring-up L5.4).

### 7.5 Classification-style API (classification / feature / number / landmark)

Each reports an argmax id and a probability (scaled integer, section 7.1).

| Mode | Methods |
| --- | --- |
| Image classification | `classTopId()`, `classTopProb()`, `classProbOfId(id)` |
| Feature learning | `featureTopId()`, `featureTopProb()`, `featureProbOfId(id)` |
| Number recognition | `numberTopId()`, `numberTopProb()` - **UNVERIFIED** |
| Road-sign / landmark | `landmarkTopId()`, `landmarkTopProb()` - **UNVERIFIED** |

`*TopId` -> argmax id or `E_MODE`; `*TopProb` -> scaled probability or `E_MODE`; `*ProbOfId(id)` -> scaled probability of a 1-based id, or `E_MODE`/`E_ARG` (the id table is bounded by the mode's summary size). Number/landmark have no `*ProbOfId` form in v0.1.0 and are single-sourced from Python (see section 6).

### 7.6 Payload API (QR / barcode)

| Mode | Methods |
| --- | --- |
| QR code | `qrDetected()`, `qrLength()`, `qrData(pBuf)` |
| Barcode | `barcodeDetected()`, `barcodeLength()`, `barcodeData(pBuf)` |

`*Detected` -> boolean; `*Length` -> decoded payload length or `E_MODE`; `*Data(pBuf)` -> bytes copied (0 if empty) / `E_MODE` / `E_NAK`. Provide a buffer of at least `QR_DATA_MAX` (400) bytes; the payload is not NUL-terminated and spans the chunk boundary (exercises `CHUNK_AUTOINC`).

### 7.7 Related artifacts

- **Regression top** `src/test_wondercam.spin2` - automatable L0-L4 self-checks of this API.
- **Bring-up playbook** `DOCs/plans/WONDERCAM-DRIVER-BRINGUP-PLAYBOOK.md` - retires the section 6 knobs and the UNVERIFIED modes on hardware.
- **Device study** `DOCs/research/WONDERCAM-THEORY-OF-OPERATION.md` - how the *camera* behaves (the source this driver was ported from).
- **Demo** `src/demo_wondercam.spin2` - an interactive front-panel exercising the full API.

---

## 8. Doc-review checklist

- [ ] All 51 public methods appear in the section 7 tables.
- [ ] Every FR-7 / section-2 tunable constant is named and explained in section 6.
- [ ] The two-layer architecture, single-cog/polled execution model, and dedicated-bus (lock-deferred) contract are each stated.
- [ ] The summary-cache model (`updateResult` latches; details on demand) is described.
- [ ] The error-code vocabulary and the scaled-integer probability contract are specified.
