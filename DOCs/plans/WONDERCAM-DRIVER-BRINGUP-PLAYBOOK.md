# WonderCam Driver - Hardware Bring-Up Playbook

**Build target:** v0.1.0 (`VERSION = 0_01_00` in `src/isp_wondercam.spin2`)
**Sprint:** `wc-driver-v1` (plan section 11; spec section 7.1)
**Targets:** one P2 development board + one Hiwonder WonderCam wired on a dedicated I2C bus, driven from the **macOS host** (`pnut-term-ts`). Plus props for L5: known faces, objects (incl. a monitor), color cards, a line, >=2 AprilTags of one id, classification/feature subjects, a QR code and a barcode with **known** payloads, printed digits, and road-sign cards.
**Estimated run time:** ~90 min for L0-L4 + the QR/barcode/face/object/color/tag subset of L5; budget another ~60 min for the full L5 sweep incl. the UNVERIFIED number/landmark modes.

---

## How to use this playbook

This is the one-time **bottom-up** bring-up that proves the hardware layer by layer and **retires the driver's UNVERIFIED facts**. It runs at turn-on, on the host, **after the sprint's code compiles clean**. Each layer is proven before the next is trusted: a red step blocks the layers above it.

- **Dual environment.** Compiling happens in either environment; **executing happens only on the macOS host** (it needs the board + camera + `pnut-term-ts`). Nothing here runs in the Linux dev container.
- **Record outcomes inline.** Each exercise ends with a `Pass/Fail: [ ]` box and a `Finding:` line. Fill them in as you go - the filled playbook is what `sprint-closeout` reads to report "verified on hardware" honestly.
- **Automated gates run first (skill discipline).** The compile baseline (G1) and the automated regression top (G2) must be green before any manual exercise. They fail fast and cheap; do not spend bench time on a system not yet known good.
- **On a finding, update ONE place.** Every UNVERIFIED constant lives in a clearly-commented spot in `src/isp_wondercam.spin2` (the FR-7 "tunable" CON block, or the named map constants). Each exercise names the exact constant to correct. After correcting, **re-run G1 + G2** before continuing.
- **Gather, then fix.** If a session surfaces several wrong behaviors, record them all first, then hand the set to `defect-fixing` as one symptom inventory - multiple decode failures often share one root cause (a wrong stride, a reversed byte order).

**Layer map (spec section 7.1):** L0 bus presence -> L1 register read + byte order -> L2 register write + echo -> L3 chunked read >32 B -> L4 mode select + summary latch -> L5 per-application decode. The **coverage matrix in section 7** maps every theory-of-operation open question (Q1-Q15) and every FR-7 tunable to the step that closes it.

---

## 0. Prerequisites (do these before powering the bench)

- **P-1 Wiring set.** In `src/test_wondercam.spin2`, `src/demo_wondercam.spin2`: set `PIN_SCL`, `PIN_SDA`, `BUS_KHZ` to the actual bench wiring. The camera needs its 5 V supply and a moment to finish its power-on boot before `start()` is called.
- **P-2 Pull-ups chosen.** Confirm the `start()` pull-up argument (`i2c.PU_3K3` in the demo/test) matches the board: external pull-ups -> `PU_NONE`; rely on P2 internal -> `PU_3K3` (~3.3 k) as a starting point.
- **P-3 Bus is dedicated.** v0.1.0 assumes the driver owns the bus exclusively (no bus lock - deferred, see `DOCs/plans/PUNCH-LIST.md`). No other device may share these pins during bring-up.

---

## 1. Automated gates (run first - green before any manual step)

### G1 - Compile-clean baseline

- **Verifies:** spec section 7.3; tasks «#1»-«#10» build clean.
- **Targets:** none (compiler only; either environment).
- **Setup:** clean working tree.
- **Action:**
  ```
  pnut-ts -l src/isp_wondercam.spin2
  pnut-ts -l src/test_wondercam.spin2
  pnut-ts -d src/demo_wondercam.spin2
  ```
- **Expected:** all three compile with **0 warnings / 0 errors**.
- **Pass/Fail:** [ ]   **Finding:** ______________________

### G2 - Automated regression top on hardware

- **Verifies:** the automatable L0-L4 subset (spec section 7.2; task «#10»). This is the gate for every manual exercise below.
- **Targets:** 1 board + camera + host.
- **Setup:** P-1..P-3 done; camera powered and booted.
- **Action:**
  ```
  cd src && pnut-term-ts -r test_wondercam.bin -b 2000000
  ```
  (compile first with `pnut-ts test_wondercam.spin2` if `.bin` is stale.)
- **Expected:** the log ends with `OVERALL: PASS (automatable L0-L4 subset)` and `fail=0`. The `SKIP`/`GAP` lines are expected and name what stays manual. The printed `L1 version string` is human-sane ASCII (e.g. `v0.6.5`).
- **On red:** read which check failed (each FAIL prints `expected=` vs `actual=`). Drop to the matching manual layer below to diagnose, fix the constant, re-run G1+G2.
- **Pass/Fail:** [ ]   **Finding:** ______________________

> If G2 is fully green, L0/L1/L3 and the L4 summary-shape/guard are already proven automatically. The manual exercises below for those layers are **diagnostic fallbacks** (run only if the matching G2 check is red) - except L2's LED eyeball and all of L5, which are manual by nature and always run.

---

## 2. L0 - Bus presence (diagnostic fallback)

### L0.1 - Device ACKs at 0x32

- **Verifies:** spec 7.1 L0; the I2C address. Closes nothing new if G2 passed (G2's `L0: bus ACK at 0x32` covers it); run only if that check is red.
- **Targets:** 1 board + camera (+ logic analyzer if available).
- **Setup:** camera powered, booted.
- **Action:** run G2; observe the `L0` line. If red, scope SDA/SCL: confirm pull-ups, wiring, and that the camera finished booting before `start()`.
- **Expected:** `start()` returns `E_OK` (device acknowledged `CAM_ADDR_WR = $64`).
- **Update on finding:** if the address differs, correct `CAM_ADDR_7BIT` ($32) in `src/isp_wondercam.spin2`. (Closes the "0x32 is code-only / PDF-omitted" single-sourced item.)
- **Pass/Fail:** [ ]   **Finding:** ______________________

---

## 3. L1 - Register read + 16-bit framing + address byte order

### L1.1 - Firmware version reads as sane ASCII

- **Verifies:** spec 7.1 L1. **Closes Q1 (address byte order).**
- **Targets:** 1 board + camera.
- **Setup:** as G2.
- **Action:** run G2; read the `L1 version string = '...'` log line (and the `printable ASCII` check).
- **Expected:** a recognizable version like `v0.6.5` - printable, not byte-swapped garbage. Garbage / reversed-looking bytes are the classic **address-byte-order-reversed** symptom.
- **Update on finding:** if reversed, flip `ADDR_LOW_FIRST` (TRUE -> FALSE) in the FR-7 tunable block of `src/isp_wondercam.spin2`; re-run. (`sendRegAddr()` honors this in one place.) Confirm with a logic analyzer that the 16-bit register address goes out **low byte first** (code default).
- **Pass/Fail:** [ ]   **Finding:** ______________________

---

## 4. L2 - Register write + echo

### L2.1 - LED fill-light responds (EYEBALL - always manual)

- **Verifies:** spec 7.1 L2; the write path, visually. This is the named coverage gap the automated top cannot see.
- **Targets:** 1 board + camera, observed by eye.
- **Setup:** any mode active.
- **Action:** drive `cam.setLed(TRUE)` then `cam.setLed(FALSE)` (the demo's `l` key toggles it; or a scratch top calling the two in sequence with a `waitms(1000)` between).
- **Expected:** the fill light visibly turns on, then off. (`setLed` returns the byte count on success.)
- **Update on finding:** if the write is NAK'd, revisit `REG_LIGHT` ($0030); if it writes but no light, that is a wiring/firmware observation to note, not a driver constant.
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L2.2 - Mode write + echo round-trip (automated by G2)

- **Verifies:** spec 7.1 L2/L4; the `setMode` -> `currentMode` echo. Diagnostic fallback if G2's `L2/L4` block is red.
- **Targets:** 1 board + camera.
- **Action:** G2 writes every func 1..11 and checks the echo. If a specific mode is red, drive that `cam.setMode(func)` alone and read `cam.currentMode()`.
- **Expected:** each written func id is echoed back within the bounded poll (`MODE_POLL_MAX`; worst case ~4 s).
- **Update on finding:** see L4.1 (a mode that never echoes may be a contested func number).
- **Pass/Fail:** [ ]   **Finding:** ______________________

---

## 5. L3 - Chunked read > 32 bytes (the chunk strategy gates every big read)

### L3.1 - Large-read integrity (automated by G2)

- **Verifies:** spec 7.1 L3. **Closes Q2 (chunk auto-increment)** and confirms `READ_CHUNK`.
- **Targets:** 1 board + camera (+ logic analyzer for the deep dive).
- **Action:** G2's `L3` checks read a `2 * READ_CHUNK` region two ways (one big read vs two stitched chunk reads) and require byte-equality, plus the known 16-byte version at the front. Run only the deep dive if that check is red.
- **Expected:** the two reads agree byte-for-byte -> the device auto-increments its read pointer across the 32-byte boundary.
- **Update on finding:** if they disagree, the device does **not** auto-increment across STOP-separated chunks. Set `CHUNK_AUTOINC = FALSE` in the FR-7 block (the driver then re-addresses per `READ_CHUNK` chunk). Re-run. Confirm the chunk size the firmware actually tolerates and adjust `READ_CHUNK` if needed. (See also L5.8 - a known-payload QR is the strongest real-data confirmation of this.)
- **Pass/Fail:** [ ]   **Finding:** ______________________

---

## 6. L4 - Mode select + summary latch + readiness

### L4.1 - All 11 modes select and latch a summary (automated by G2)

- **Verifies:** spec 7.1 L4. **Closes Q15 (enum drift)** - the driver fixes its own 1..11 numbering. Diagnostic fallback if G2's `L4` block is red.
- **Targets:** 1 board + camera.
- **Action:** G2 sets each func 1..11, calls `updateResult()`, checks the summary read size matches the plan (classification 128, feature 64, else 48) and the per-mode accessor returns a non-error, and that a wrong-mode accessor returns `E_MODE`.
- **Expected:** all 11 modes latch a correctly-sized summary; the guard rejects cross-mode reads.
- **Update on finding:** a mode that will not echo/latch may have a wrong func number - see Q5/Q8 (color=5, number=10, landmark=11) confirmed in L5.3/L5.10/L5.11.
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L4.2 - Readiness after a mode switch (manual - needs timing)

- **Verifies:** spec 7.1 L4 readiness. **Closes Q13 (stale summary while the model spins up).**
- **Targets:** 1 board + camera, with a known target in frame.
- **Setup:** start in a fast mode; have a face in frame.
- **Action:** `cam.setMode(cam.FUNC_FACE)`, then immediately loop `cam.updateResult()` + `cam.numFaces()` every ~100 ms for ~3.5 s, logging the count each poll.
- **Expected:** `setMode` returns `E_OK` only after the echo settles; the first few `updateResult()` calls may report 0/stale until the model finishes loading (mode change up to ~3 s), then a stable nonzero count.
- **Update on finding:** if early polls return stale data after the echo already matched, document the additional settle delay needed; callers must poll, not trust the first frame. (Confirms the `MODE_SETTLE_MS`/`MODE_POLL_*` envelope is adequate.)
- **Pass/Fail:** [ ]   **Finding:** ______________________

---

## 7. L5 - Per-application decode (manual; needs known targets)

These are the heart of bring-up: known objects in frame, decoded through the high-level API, confirming each contested fact and each fixed vendor bug. Set the mode, put the target in frame, `cam.updateResult()`, then read.

### L5.1 - Face (Q9; unlearned-count + 0-based-index bug fixes)

- **Verifies:** plan section 6; tasks «#5»,«#6». **Closes Q9 (face id-list width cap).**
- **Targets:** 1 board + camera; several faces, at least one **learned** (id-bearing) and several **unlearned**.
- **Action:** in `FUNC_FACE`, `updateResult()`, then read `numFaces()`, `numLearned()`, `numUnlearned()`, `faceIdDetected(id)`, `getFaceById(id, @rec)`, and `getUnlearnedFace(0, @rec)` / `getUnlearnedFace(1, @rec)`.
- **Expected:** counts match what is in frame; `numUnlearned()` returns the **byte** count (not a huge pointer-cast number - vendor bug 1 fixed); `getUnlearnedFace(0,..)` returns the **first** unlearned face (0-based - vendor bug 3 fixed); box `x,y,w,h` plausibly frames each face.
- **Update on finding:** if more than 29 faces are ever reported, raise `IDLIST_CAP` (29) toward the PDF's 38. Note the spatial `x/y/w/h` coordinate range to set the demo's `CAM_RES_W/H` (320/240 assumed).
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L5.2 - Object (Q6; off-the-end + 0-based-index bug fixes)

- **Verifies:** plan section 6. **Closes Q6 (object class 20 "Monitor").**
- **Targets:** known objects including a **monitor**; ideally two objects of the same class.
- **Action:** in `FUNC_OBJECT`, read `numObjects()`, `objectIdDetected(id)`, `numObjectsOfId(id)`, `getObject(id, 0, @rec)` and `getObject(id, 1, @rec)`.
- **Expected:** a monitor reports class id **20** (confirms the device emits it though the PDF lists only 19); `getObject` indexing is 0-based and never runs off the end (vendor bug 2 fixed); two same-class objects are reachable at index 0 and 1.
- **Update on finding:** record the real class-id range; if class 20 never appears, note the PDF's 19-class list governs.
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L5.3 - Color (Q5)

- **Verifies:** plan section 6. **Closes Q5 (color function number = 5).**
- **Targets:** a learned color card.
- **Action:** `cam.setMode(cam.FUNC_COLOR)` (writes func 5); confirm the echo, then `updateResult()`, `anyColor()`, `numColors()`, `getColor(id, @rec)`.
- **Expected:** func 5 is accepted and echoed (confirms color=5 in firmware, which the PDF omits); the color box decodes from `BASE_COLOR` ($1000).
- **Update on finding:** if func 5 is not color, correct `FUNC_COLOR` / `BASE_COLOR` and the `summaryReadPlan` mapping.
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L5.4 - Line follow (Q7)

- **Verifies:** plan section 6. **Closes Q7 (line fields: true endpoints vs a box).**
- **Targets:** a single line/track in frame at a known angle and offset.
- **Action:** in `FUNC_LINE`, `getLine(id, @rec)`; inspect `start_x,start_y,end_x,end_y` and the normalized `angle`/`offset`.
- **Expected:** decide empirically whether the first four int16 are **segment endpoints** (Arduino interpretation) or **x,y,w,h of a box** (Python). Move the line and watch which interpretation tracks reality. Confirm the raw angle range/zero-reference and offset sign before trusting the normalization.
- **Update on finding:** annotate the `LINE_*` interpretation in `src/isp_wondercam.spin2` (the `LINE_ANGLE_WRAP/PERIOD/OFFSET_CENTER` normalization) and the demo's line view; pick the interpretation that tracks.
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L5.5 - AprilTag (Q3, Q4, Q10; tag-stride bug fix)

- **Verifies:** plan section 6. **Closes Q3 (tag stride), Q4 (count off-by-one), Q10 (pose units).**
- **Targets:** **two AprilTags of the same id** in frame (so index 1 is reachable), at a known distance/orientation.
- **Action:** in `FUNC_APRILTAG`, `numTags()`, `numTagsOfId(id)`, `getTag(id, 0, @rec)` **and** `getTag(id, 1, @rec)`; read the 6 pose floats from the second record.
- **Expected:** `getTag(id, 1, ..)` returns the **second** tag's record - proving the per-index advance is `TAG_REC_STRIDE` (32), **not** the vendor's 0x32=50 typo (vendor bug 5 fixed). The count matches the number of tags (resolving whether it lives at 0x1E01 or 0x1E02). Pose floats are finite and change sensibly as the tag moves.
- **Update on finding:** if index-1 reads garbage, the stride is wrong - correct `TAG_REC_STRIDE`. If the count is off by one, adjust the AprilTag summary offset. Record the pose units/frame handedness (currently undocumented).
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L5.6 - Image classification (Q11; probability representation)

- **Verifies:** plan section 7. **Closes Q11 (class counts)** and the probability-representation punch-list item.
- **Targets:** subjects for two or more known classes spanning a range of class ids.
- **Action:** in `FUNC_CLASSIFY`, `classTopId()`, `classTopProb()`, `classProbOfId(id)` for a high id.
- **Expected:** top id matches the subject; probability is a **scaled integer 0..10000** (`raw/PROB_DIVISOR` = 0.0..1.0); `classProbOfId` works for the highest id of interest within the 128-byte summary.
- **Update on finding:** if the highest class id of interest falls outside 128 bytes, the summary read size must grow. Confirm the scaled-int contract reads naturally for integrators (punch-list: int vs float return).
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L5.7 - Feature learning

- **Verifies:** plan section 7.
- **Targets:** an object to learn as a feature id.
- **Action:** in `FUNC_FEATURE`, learn a feature, then `featureTopId()`, `featureTopProb()`, `featureProbOfId(id)`.
- **Expected:** the learned id reports the top probability; the 64-byte summary covers the id table at `BASE_FEATURE + 0x10`.
- **Update on finding:** note any learn/save register the driver does not yet expose (feeds Q14).
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L5.8 - QR code (Q2 confirmation via a KNOWN payload)

- **Verifies:** plan section 7. **Strongest real-data confirmation of Q2 (chunk auto-increment)** - a QR payload longer than 32 bytes is a *known* byte pattern that must read back intact across chunk boundaries.
- **Targets:** a QR code whose text payload you know and is **> 32 bytes** (to span at least two chunks).
- **Action:** in `FUNC_QRCODE`, `qrDetected()`, `qrLength()`, `qrData(@buf)`; compare `buf` against the known string.
- **Expected:** length and bytes match the printed payload exactly, including bytes past the 32-byte boundary - proving `CHUNK_AUTOINC` end-to-end on real data.
- **Update on finding:** any corruption past byte 32 reconfirms an L3 chunk-strategy problem; fix `CHUNK_AUTOINC`/`READ_CHUNK` and re-run L3 + this step.
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L5.9 - Barcode (KNOWN payload)

- **Verifies:** plan section 7.
- **Targets:** a barcode with a known numeric payload.
- **Action:** in `FUNC_BARCODE`, `barcodeDetected()`, `barcodeLength()`, `barcodeData(@buf)`; compare to the known value.
- **Expected:** payload matches; reads from `BASE_BARCODE` ($1C00) length/data offsets.
- **Update on finding:** none expected (code-corroborated); note any deviation.
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L5.10 - Number recognition (Q8; UNVERIFIED - Python-only)

- **Verifies:** plan section 7. **Closes Q8 (number base 0x0D00 + per-id stride).** This path has **no vendor C source**; it is authored from the Python reference and is unverified until now.
- **Targets:** printed digits in frame.
- **Action:** `cam.setMode(cam.FUNC_NUMBER)` (func 10); confirm the echo, `updateResult()`, `numberTopId()`, `numberTopProb()`.
- **Expected:** a recognized digit reports a plausible top id + probability read from `BASE_NUMBER` ($0D00).
- **Update on finding:** if the echo or decode is wrong, correct `FUNC_NUMBER`/`BASE_NUMBER` and the per-id stride (assumed 4 B). If the mode does not exist in this firmware, mark number recognition unsupported. **This step flips number-rec from UNVERIFIED to verified-or-removed.**
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L5.11 - Landmark / road-sign (Q8; UNVERIFIED - Python-only; id=1 sentinel)

- **Verifies:** plan section 7. **Closes Q8 (landmark base 0x0D80)** and the landmark id-map ambiguity.
- **Targets:** road-sign cards, plus an **empty** frame to probe the no-detection sentinel.
- **Action:** `cam.setMode(cam.FUNC_LANDMARK)` (func 11); confirm the echo, `updateResult()`, `landmarkTopId()`, `landmarkTopProb()`; then read with **no sign** in frame.
- **Expected:** a sign reports a plausible id; with no sign, resolve whether **id 1 means "none"** (Python) or is a valid sign (Arduino) - gate on `landmarkTopProb()` confidence to disambiguate.
- **Update on finding:** record the real id-to-meaning map and the no-detection sentinel; correct `FUNC_LANDMARK`/`BASE_LANDMARK` if the echo/decode is wrong. **Flips landmark-rec from UNVERIFIED to verified-or-removed.**
- **Pass/Fail:** [ ]   **Finding:** ______________________

### L5.12 - Exploratory raw-register sweep (Q12, Q14)

- **Verifies:** **Closes Q14 (undocumented config registers)** and informs **Q12 (max write payload)**.
- **Targets:** 1 board + camera.
- **Action:** using the raw API `cam.readReg(addr, @buf, len)`, sweep candidate register ranges beyond $0000/$0030/$0035 (e.g. resolution/exposure/threshold/learn/save) and log non-zero responses. Note the largest single-transaction write the firmware accepts if any multi-byte write is attempted.
- **Expected:** discovery only - this names whether writable config registers exist beyond the three known ones.
- **Update on finding:** document any discovered registers as new capabilities (next-sprint candidates, `DOCs/plans/PUNCH-LIST.md`). No v0.1.0 constant changes.
- **Pass/Fail:** [ ]   **Finding:** ______________________

---

## 8. Coverage matrix (doc-review self-check)

### 8.1 Every open question maps to a step

| Theory section 8 open question | Closed/addressed by |
| --- | --- |
| Q1 Address byte order | L1.1 (+ G2 L1) |
| Q2 Chunk auto-increment | L3.1 (+ G2 L3); reconfirmed on known data by L5.8 |
| Q3 AprilTag tag stride (32 vs 50) | L5.5 (`getTag` index 1) |
| Q4 AprilTag summary off-by-one | L5.5 (count vs tags in frame) |
| Q5 Color function number = 5 | L5.3 (+ L4.1 echo) |
| Q6 Object class 20 (Monitor) | L5.2 |
| Q7 Line endpoints vs box | L5.4 |
| Q8 Number/landmark bases + stride | L5.10, L5.11 |
| Q9 Face id-list width cap | L5.1 |
| Q10 AprilTag pose units/frame | L5.5 (pose floats) |
| Q11 Classification/feature class counts | L5.6 (+ L5.7) |
| Q12 Max write payload | L5.12 (exploratory) |
| Q13 Readiness/stale after mode switch | L4.2 |
| Q14 Undocumented config registers | L5.12 (raw sweep) |
| Q15 Enum drift (APPLICATION_MAX) | L4.1 (all 11 echo; driver owns its 1..11) |

### 8.2 Every FR-7 tunable has a confirming step

| FR-7 tunable (`src/isp_wondercam.spin2`) | Default | Confirming step |
| --- | --- | --- |
| `ADDR_LOW_FIRST` | TRUE (low byte first) | L1.1 |
| `READ_CHUNK` | 32 | L3.1 |
| `CHUNK_AUTOINC` | TRUE | L3.1 (+ L5.8 on known payload) |
| `TAG_REC_STRIDE` | 32 (not 0x32=50) | L5.5 |
| `FUNC_COLOR` = 5 (contested) | 5 | L5.3 |
| `FUNC_NUMBER` = 10 (contested) | 10 | L5.10 |
| `FUNC_LANDMARK` = 11 (contested) | 11 | L5.11 |

### 8.3 Confirmed vendor-bug fixes exercised (theory section 7.3)

| Vendor bug (now fixed in the driver) | Exercised by |
| --- | --- |
| `numOfTotalUnlearnedFaceDetected` returned a pointer, not the byte | L5.1 (`numUnlearned`) |
| `objDetected` ran off the end / decremented only on match | L5.2 (`getObject` index 0/1) |
| `getFaceOfIndex` 1-based pre-decrement | L5.1 (`getUnlearnedFace(0)`) |
| `tagId` 1-based pre-decrement | L5.5 (`getTag(id,0)`) |
| AprilTag stride 0x32=50 vs record 32 | L5.5 (`getTag(id,1)`) |

### 8.4 Doc-review checklist

- [ ] Every Q1-Q15 appears in 8.1 with a numbered step.
- [ ] Every FR-7 tunable appears in 8.2 with a confirming step.
- [ ] Automated gates (G1, G2) precede all manual exercises.
- [ ] Each L5 step names the target props and the constant to update on a finding.
- [ ] The UNVERIFIED modes (number, landmark) each have a step that flips them to verified-or-removed.

---

*On sprint archive, move this playbook to `DOCs/plans/archive/`. Results recorded here are read by `sprint-closeout` to report hardware-verification state.*
