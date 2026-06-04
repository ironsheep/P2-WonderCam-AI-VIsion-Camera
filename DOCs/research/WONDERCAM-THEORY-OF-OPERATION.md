# Hiwonder WonderCam AI Vision Camera - Theory of Operation

Reference document for authoring a Parallax Propeller 2 (P2) Spin2 I2C driver.

This document synthesizes multiple research sources:

- The vendor's C++ Arduino driver (`WonderCam.cpp` / `WonderCam.h`), treated as the
  authoritative runtime behavior.
- The vendor `Register list.pdf` register map.
- A vendor "Master-Slave Communication Principle" PDF (which, as noted below, turned out to
  describe a DIFFERENT product and is NOT a source for this camera).
- Per-feature usage studies of all vision applications (Arduino + Raspberry Pi Python + ESP32
  MicroPython demos).
- A driver-drift analysis across several shipped copies of the C++ driver.
- A code-vs-PDF cross-validation that ground-truthed both maps against the actual repo files.

Where the code and the PDF disagree, the disagreement is surfaced explicitly. Throughout this
document, "code is authoritative" means the C++ driver is what actually runs on hardware; the
PDF is a documentation artifact that contains several confirmed typos.

All addresses are 16-bit register/memory addresses in the device's flat address space unless
otherwise noted.

---

## 1. Overview and Purpose

The WonderCam is a self-contained "AI vision module": a camera plus an on-board neural
processor that runs one vision application at a time and exposes its results to a host
microcontroller over I2C.

### 1.1 Hardware (from Specification.pdf)

| Attribute | Value |
| --- | --- |
| Processor | Kendryte K210 |
| Image sensor | OV2640 (2.0 MP, "200W pixel") |
| Display | 2.0-inch IPS, 320 x 240 |
| Power | 5V, typical 300 mA (face mode, 100% backlight, fill light off) |
| Host interface | I2C ("IIC"), 100 kHz (Standard) or 400 kHz (Fast); 400 kHz recommended |
| Product size | 52 x 44.5 mm; screen 41 x 31 mm; weight 24 g |

### 1.2 Host <-> Camera model

- The host MCU is the I2C MASTER; the WonderCam is the I2C SLAVE at 7-bit address 0x32.
- The camera does ALL the vision work internally. It does not stream images over I2C. The
  320 x 240 frame is shown only on the camera's own IPS display. Neither vendor PDF documents
  any image / frame-buffer transfer register; results are delivered ONLY as structured
  per-application registers.
- Operating cycle, at a high level:
  1. Host selects a vision application by writing a function number to register 0x0035.
  2. Host periodically "refreshes" results by reading the active application's base/refresh
     register (which also latches the latest result into the register file).
  3. Host reads a fixed 48-byte summary header, then optionally reads per-detection detail
     records on demand.
- The camera is essentially a pull-model results server: the host polls; there is no
  interrupt line, no ready flag (other than the mode-echo readback), and no host-issued
  "capture" command in the studied driver.

### 1.3 Note on the "Master-Slave Communication Principle" PDF (do not use)

One research source was a PDF filed under "3. Multi-Controller Communication Tutorial / 3.1
Master-Slave Communication Principle" inside the WonderCam repo. That PDF is NOT about the
WonderCam. It documents a "uHand UNO" robotic hand over a UART serial bus (9600 8-N-1, frame
header 0xAA 0x77, one's-complement checksum). None of its framing applies to this camera. It
is called out here only so a future reader does not mistake it for the I2C protocol spec. The
authoritative protocol comes from the C++ driver and `Register list.pdf`.

---

## 2. Electrical / I2C Interface

### 2.1 Address

- 7-bit I2C address 0x32 (`CAM_DEFAULT_I2C_ADDRESS`, `WonderCam.h` line 8). Fixed at compile
  time; there is NO runtime method to change it in the studied driver. Arduino `Wire` takes
  the 7-bit form directly and shifts internally for the R/W bit.
- The Register list PDF does not state the slave address at all; 0x32 is documented only in
  code. (Single-sourced from code, but consistent across every shipped driver variant.)

### 2.2 Register addressing scheme

- Registers live in a single flat 16-bit address space (observed 0x0000..0x1E00+).
- Before every read or write, the host writes the 2-byte register address LOW byte first,
  then HIGH byte (`Wire.write(addr & 0x00FF)`, then `Wire.write((addr >> 8) & 0x00FF)`).
  This is true little-endian on the wire.
- DISCREPANCY (address byte order) - VERIFY: The Register list PDF prose says the address is
  sent "upper-byte ... followed by the lower-byte, that is little-endian", which is both
  self-contradictory (upper-then-lower is big-endian) and contradicts the code. The CODE is
  authoritative (low byte first). Confirm with a logic analyzer, but trust the code.
- Multi-byte DATA payloads inside result structs (int16/uint16/float) are little-endian,
  matching the AVR host. Structs are `#pragma pack(1)` and read raw via `memcpy`.
- Coordinates are 16-bit SIGNED. Confidence / similarity / length values are 16-bit UNSIGNED.

### 2.3 Read transaction

`readFromAddr(uint16_t addr, uint8_t *buf, uint16_t leng)` (`WonderCam.cpp:8-32`):

1. `beginTransmission(0x32)`; write low addr byte; write high addr byte; `endTransmission()`
   (issues a STOP).
2. Read the payload in 32-byte chunks:
   - `ts = leng >> 5` full 32-byte chunks; `ls = leng - (ts << 5)` remainder bytes.
   - Loop `ts` times: `Wire.requestFrom(0x32, 32, true)` and drain via `Wire.read()`.
   - If `ls > 0`: one final `Wire.requestFrom(0x32, ls, true)`.
3. Each `requestFrom` uses `sendStop = true` (a STOP after EACH chunk, NOT a repeated-start).

Key consequence: the start address is sent ONCE, before the chunk loop. The device MUST
auto-increment its internal address pointer across successive STOP-separated `requestFrom`
reads, or any read longer than 32 bytes is corrupt. This auto-increment behavior is assumed by
the driver but is not documented in the PDF - flagged for hardware verification (Section 8).

Max bytes per single I2C transfer = 32 (Arduino AVR `Wire` buffer `BUFFER_LENGTH`). The
chunking exists specifically to respect this limit.

### 2.4 Write transaction

`writeToAddr(uint16_t addr, const uint8_t *buf, uint16_t leng)` (`WonderCam.cpp:34-41`):

1. Single transmission: `beginTransmission(0x32)`; write low addr byte; write high addr byte;
   `Wire.write(buf, leng)`; `endTransmission()` (STOP).
2. No chunking is implemented for writes. On AVR, a write is limited by the 32-byte TX buffer,
   so payload is ~30 bytes max (2 address bytes + payload).

Every write the driver actually performs is 1 byte (mode select at 0x0035, LED at 0x0030). No
multi-byte write is exercised anywhere in the studied code.

### 2.5 Timing

- `delay(50)` ms appears twice in `changeFunc()`: once after writing the new mode (settle
  before first readback), and once per poll iteration where the readback does not yet match.
- `changeFunc()` polls up to ~81 times (`count > 80`) at 50 ms each, i.e. up to ~4 seconds
  before giving up. The PDF says a mode change "may take 0.X to 3 seconds".
- There is NO inter-byte or post-address settle delay in `readFromAddr` / `writeToAddr`, and
  NO repeated-start. There is no handshake/ready flag other than the mode echo at 0x0035.
- `updateResult()` and detail reads have no built-in settle delay; the application is expected
  to poll periodically (demos run 2-20 Hz).

### 2.6 Portability deltas (ESP32 vs AVR)

The driver-drift analysis confirms the ESP32 variant differs from AVR ONLY in I2C bring-up and
C++ pedantry, never in API, addresses, structs, or enums:

- ESP32 uses explicit pins: `#define SDA 17`, `#define SCL 16`, `Wire.begin(SDA, SCL)`.
- ESP32 drops the 3rd `true` (sendStop) arg on `Wire.requestFrom(addr, len)` (core overload
  differs).
- ESP32 adds explicit casts and removes the `TwoWire &wire` member.

A P2 driver should treat pin selection and the requestFrom signature as the only
platform-specific concerns.

---

## 3. Operating Model

### 3.1 Mode selection (register 0x0035)

- `SYS_CURRENT_FUNC` at 0x0035 (1 byte, RW) is the active application selector.
- Read current mode: `currentFunc()` reads 1 byte from 0x0035, stores into `this->current`,
  returns it.
- Change mode: `changeFunc(uint8_t new_func)` writes `new_func` to 0x0035, `delay(50)`, then
  polls `currentFunc()` until readback == `new_func` (success) or `count > 80` (timeout,
  returns false). This is a BLOCKING confirm-and-poll.
- `updateResult()` re-reads 0x0035 into `current` at its start, so result parsing always
  matches the live mode.

Application function numbers:

| Name | Enum value | Func # written to 0x0035 |
| --- | --- | --- |
| APPLICATION_NONE | 0 | 0 |
| APPLICATION_FACEDETECT | 1 | 1 |
| APPLICATION_OBJDETECT | 2 | 2 |
| APPLICATION_CLASSIFICATION | 3 | 3 |
| APPLICATION_FEATURELEARNING | 4 | 4 |
| APPLICATION_COLORDETECT | 5 | 5 (code; PDF omits, see below) |
| APPLICATION_LINEFOLLOW | 6 | 6 |
| APPLICATION_APRILTAG | 7 | 7 |
| APPLICATION_QRCODE | 8 | 8 |
| APPLICATION_BARCODE | 9 | 9 |
| APPLICATION_NUMBER_REC | 10 (0x0A) | 10 (header-superset only; see Section 5.9) |
| APPLICATION_LANDMARK_REC | 11 (0x0B) | 11 (header-superset only; see Section 5.10) |
| APPLICATION_MAX | 10 or 12 (varies by header) | - |

DISCREPANCY (color function number) - VERIFY: The code enum asserts COLORDETECT = 5. The
PDF's function-number list enumerates 1,2,3,4,6,7,8,9 and SKIPS 5. Code value is almost
certainly correct, but the PDF does not confirm it.

Note on enum drift: the base/canonical header has `APPLICATION_MAX = 10`. The number/landmark
"superset" headers insert NUMBER_REC (10) and LANDMARK_REC (11) before MAX, shifting MAX to 12.
Code that iterates to `APPLICATION_MAX` is therefore NOT binary-compatible across header
variants (Section 7).

### 3.2 The updateResult cycle

`updateResult()` (`WonderCam.cpp:512-555`):

1. Read 1 byte from 0x0035 into `current`.
2. Switch on `current` and read that mode's summary/header block into the member buffer
   `result_summ[128]`.

Per-mode summary read sizes:

| Mode (func) | Base | Summary bytes read |
| --- | --- | --- |
| FACEDETECT (1) | 0x0400 | 48 |
| OBJDETECT (2) | 0x0800 | 48 |
| CLASSIFICATION (3) | 0x0C00 | 128 (full buffer) |
| FEATURELEARNING (4) | 0x0E00 | 64 |
| COLORDETECT (5) | 0x1000 | 48 |
| LINEFOLLOW (6) | 0x1400 | 48 |
| APRILTAG (7) | 0x1E00 | 48 |
| QRCODE (8) | 0x1800 | 48 |
| BARCODE (9) | 0x1C00 | 48 |

Notes: the QRCODE and APRILTAG switch cases are out of numeric order in the code (harmless).
The BARCODE case has no `break` before `default`, but `default` is empty (harmless). The
canonical `.cpp` has NO case for NUMBER_REC (0x0A) or LANDMARK_REC (0x0B) - those modes are not
refreshed by the shipped C++ driver (Sections 5.9, 5.10, 7).

Reading the base/refresh register is itself meaningful: per the PDF, reading a function's base
address makes the camera latch/cache the current result into the register file, AND the byte
returned equals the active function number (use it to confirm which mode is live).

Detail records (per-detection geometry / payload) are NOT read by `updateResult()`. They are
read lazily, on demand, when the host calls an accessor like `getFaceOfId` / `colorId` /
`tagId`.

### 3.3 LED control (register 0x0030)

- `setLed(bool new_state)` writes a single byte to 0x0030: 1 = ON, 0 = OFF.
- Header macros: `WONDERCAM_LED_ON = true`, `WONDERCAM_LED_OFF = false`.
- Only one byte is ever written, so this is a simple on/off "fill light". The PDF confirms
  strictly on/off (no brightness/RGB). A dead local `buf[3] = {0x30,0x00,0x00}` in `setLed` is
  unused.

### 3.4 Version queries (register 0x0000)

- `firmwareVersion(char *str)` reads 16 bytes from 0x0000 into the caller's buffer (ASCII,
  e.g. "v0.6.5"). The driver does NOT NUL-terminate; the caller must size >= 16 and terminate.
  Always returns true regardless of I2C result.
- `hardwareVersion(char *)` and `protocalVersion(char *)` (note the header misspells
  "protocal") are DECLARED in the header (lines 112-113) but NOT IMPLEMENTED in the studied
  `.cpp`. Linking a call would fail. The PDF documents no hardware/protocol-version register
  either - only `SYS_FIRMWARE_VERSION` at 0x0000.

---

## 4. Register and Memory Map

### 4.1 System registers

| Name | Addr | Access | Size | Meaning |
| --- | --- | --- | --- | --- |
| SYS_FIRMWARE_VERSION | 0x0000 | R | 16 B | ASCII version string, e.g. "v0.6.5" |
| SYS_LIGHT_STATE | 0x0030 | RW | 1 B | Fill light: 1 = on, 0 = off |
| SYS_CURRENT_FUNC | 0x0035 | RW | 1 B | Active function number; write to select, read to confirm |

These (0x0000, 0x0030, 0x0035) are the only registers the driver writes. No
resolution/exposure/threshold/learn/save registers appear anywhere in the studied code or PDF.

### 4.2 Application result regions (consolidated)

Each application has a BASE address. The byte at BASE is the function-echo / refresh register.
The 48-byte block at BASE is the summary header. Per-detection detail records start at
BASE + 0x30 (= BASE + 48) with a per-mode stride.

| Application | Func | Base | Summary header | Detail base | Stride | Detail size |
| --- | --- | --- | --- | --- | --- | --- |
| Facial Recognition | 1 | 0x0400 | 48 B | 0x0430 | 16 B | 16 B (8 used) |
| Object Recognition | 2 | 0x0800 | 48 B | 0x0830 | 16 B | 16 B (8 used) |
| Image Classification | 3 | 0x0C00 | 128 B read | (per-class table at 0x0C10) | 4 B/class | n/a (no boxes) |
| Feature Learning | 4 | 0x0E00 | 64 B read | (per-id table at 0x0E10) | 4 B/id | n/a (no boxes) |
| Color Recognition | 5 | 0x1000 | 48 B | 0x1030 | 16 B | 16 B (8 used) |
| Visual Line Following | 6 | 0x1400 | 48 B | 0x1430 | 16 B | 16 B (12 used) |
| QR Code | 8 | 0x1800 | 48 B | 0x1830 (payload) | variable | up to 400 B |
| Barcode | 9 | 0x1C00 | 48 B | 0x1C30 (payload) | variable | up to 400 B |
| AprilTag | 7 | 0x1E00 | 48 B | 0x1E30 | 32 B (PDF) / 0x32=50 (code) | 32 B |
| Number Recognition | 10 | 0x0D00 | 48 B (Python only) | (per-id table at 0x0D10) | 4 B/id | n/a |
| Landmark Recognition | 11 | 0x0D80 | 48 B (Python only) | (per-id table at 0x0D90) | 4 B/id | n/a |

Number (0x0D00) and Landmark (0x0D80) bases are corroborated only by the Python driver; the
C++ `.cpp` never reads them (Section 7). They sit between CLASSIFICATION (0x0C00) and
FEATURELEARNING (0x0E00).

### 4.3 Summary-header layouts

Two summary "shapes" exist: a DETECTION shape (count + ID list + boxes) and a CLASSIFICATION
shape (top-id + confidence + per-id confidence table).

DETECTION shape - shared byte layout within `result_summ[]`:

- byte[0] = current/function-echo marker.
- byte[1] = primary count (number of faces / objects / colors / lines / tags this frame).
- ID list follows. For FACE the list starts at byte[4]; for OBJ/COLOR/LINE/TAG it starts at
  byte[2]. (Critical offset difference - see per-app sections.)
- FACE additionally uses byte[2] = learned count, byte[3] = unlearned count.

CLASSIFICATION shape (classification, feature-learning, number, landmark):

- byte[1] = ID of max probability (argmax class), NOT a count.
- uint16 LE at bytes[2..3] = max probability; divide by 10000.0 for a 0.0..1.0 value.
- Per-id table from offset 0x10: prob(id) = uint16 LE at offset 0x10 + (id-1)*4. Stride is 4
  bytes/id; only the first 2 bytes (the uint16 prob) are used. The PDF marks the other 2 bytes
  as reserved (this answers the code's open question about the extra 2 bytes per slot).

### 4.4 Detail-record struct layouts

Face / Object / Color (16-byte record, first 8 bytes meaningful), decode `<hhHH` LE:

| Offset | Field | Type |
| --- | --- | --- |
| +0..+1 | x (origin or center, signed) | int16 |
| +2..+3 | y (signed) | int16 |
| +4..+5 | w (width) | uint16 |
| +6..+7 | h (height) | uint16 |
| +8..+15 | reserved / padding | - |

Line (16-byte record, first 12 bytes meaningful), 6x int16 LE:

| Offset | Field (code: WonderCamLineResult) | Notes |
| --- | --- | --- |
| +0..+1 | start_x | int16 |
| +2..+3 | start_y | int16 |
| +4..+5 | end_x | int16 |
| +6..+7 | end_y | int16 |
| +8..+9 | angle (deflection / theta) | int16, raw |
| +10..+11 | offset | int16, raw |
| +12..+15 | reserved | - |

AprilTag (32-byte record), decode `<hhHHffffff` LE:

| Offset | Field | Type |
| --- | --- | --- |
| +0..+1 | x (center) | int16 |
| +2..+3 | y (center) | int16 |
| +4..+5 | w | uint16 |
| +6..+7 | h | uint16 |
| +8..+11 | x_t (X translation) | float |
| +12..+15 | x_r (X rotation) | float |
| +16..+19 | y_t (Y translation) | float |
| +20..+23 | y_r (Y rotation) | float |
| +24..+27 | z_t (Z translation) | float |
| +28..+31 | z_r (Z rotation) | float |

QR / Barcode summary (struct `WonderCamQrCodeResultSumm`, `#pragma pack(1)`, 48 bytes):
`current(1) + id(1) + reserved[14] + points[4][2] int16 (16 B) + len uint16 + reserved[14]`.
The `len` field lands at struct offset 0x20 (= base + 0x20, i.e. 0x1820 / 0x1C20), confirmed by
both the PDF and the struct math. Payload starts at base + 0x30 (0x1830 / 0x1C30), max 400
bytes.

---

## 5. The Eight (Plus Two) Vision Applications

The vendor PDFs and hardware spec list 8 "core" applications. The code enum and the
feature-usage studies cover those 8 plus two classification variants (Number Recognition,
Landmark/Road-sign Recognition) that are present in the header superset but only fully
implemented in the Python driver. All twelve are documented below; the eight required core
applications are 5.1-5.8.

### 5.1 Facial Recognition (func 1, base 0x0400)

What it does: detects faces in-frame; per face reports whether it is a LEARNED face (ID 1..5)
or UNLEARNED (ID 0xFF), plus a bounding box.

Setup: `changeFunc(APPLICATION_FACEDETECT)`; optionally `setLed(true)`; then poll.

Summary layout at 0x0400:

- byte[0] = func echo; byte[1] = total faces; byte[2] = learned count; byte[3] = unlearned
  count; bytes[4..32] = per-face ID list (up to 29 slots; value 1..5 = learned ID, 0xFF =
  unlearned).

Detail: per-face 16-byte record at 0x0400 + 0x30 + listIndex*16, decode `<hhHH` -> x, y, w, h
(pixels; x,y signed origin, can be negative when clipped at frame edge).

Capabilities: presence test; total/learned/unlearned counts; "is enrolled ID N present";
fetch box by ID or by Nth-unlearned index.

Quirks / enrollment:

- Enrollment (assigning IDs 1..5) is done ON THE CAMERA via its touchscreen/UI. There is NO
  I2C "learn face" command. The host can only read back which slot a detected face matches.
- Learned IDs are limited to 1..5.
- DISCREPANCY (ID-list scan width): the PDF documents ID slots up to 0x0429 (~38 slots); the
  code scans only 29 (`i < 4+29`, ends at 0x0420). Code may miss faces beyond the 29th slot.
- CONFIRMED BUG: `numOfTotalUnlearnedFaceDetected()` returns `(int)result_summ` (the array
  pointer) instead of `result_summ[3]`. Intended value is byte[3].
- `getFaceOfIndex()` uses pre-decrement-then-==0 (implies 1-based index; verify caller
  convention).

### 5.2 Object Recognition (func 2, base 0x0800)

What it does: detects VOC-class objects with bounding boxes.

Summary at 0x0800: byte[0] echo; byte[1] = object count; bytes[2..30] = per-object class IDs
(29 fixed slots scanned).

Detail: 16-byte record at 0x0800 + 0x30 + index*16 -> x, y, w, h.

Class IDs (from code enum `Objects`, 1-based):

DISCREPANCY (object class names/count) - VERIFY: The PDF lists 19 class names; the code enum
lists 20 (VOC-20: Aeroplane=1 ... Monitor=20). IDs 1..19 align (with name spelling differences:
code Diningtable = PDF desk; Motorbike = motorcycle; Person = people; Pottedplant = plant).
Code id 20 (Monitor) is undocumented in the PDF. Verify the device actually emits class 20.

Capabilities: presence test; count; "is class N present"; count of class N; fetch Nth object of
class N.

Quirks:

- CONFIRMED BUG: `objDetected(id, index, *p)` decrements `index` only on an id match but tests
  `index == 0` every iteration, and can fall off the end with no return (undefined behavior).
  Confirm intended semantics against the colorId/lineId pattern before reuse.
- No enrollment; classes are a fixed pretrained model.

### 5.3 Image Classification (func 3, base 0x0C00)

What it does: whole-frame single-label classification. Returns the top class ID and a
per-class confidence table (no bounding boxes). The 3.8 demos repurpose it as a garbage-sorting
classifier by bucketing class-id ranges.

Summary at 0x0C00 (CLASSIFICATION shape):

- byte[1] = top class ID; uint16 LE bytes[2..3] = top confidence (/10000.0 -> 0..1); per-class
  table from 0x0C10, conf(id) = uint16 LE at 0x0C10 + (id-1)*4.

Read sizes differ between drivers: the C++ `updateResult()` reads 128 bytes (covering many
class slots); the Python driver reads only 48 (covers ids up to (48-16)/4 = 8). A host needing
high-numbered class confidences must read enough bytes.

Capabilities: top class + confidence; probability of any specific class id on demand.

Quirks:

- byte[1] is OVERLOADED: in detection modes it is a count; here it is the dominant class id.
- The class set / count is firmware-defined and not enumerated in any studied code. (The
  `Objects` enum belongs to OBJECT DETECTION, not classification.)
- Whether per-class confidences sum to 1.0 is unverified.
- No enrollment; the model is fixed at firmware level (its learnable sibling is Feature
  Learning, func 4).

### 5.4 Feature Learning (func 4, base 0x0E00)

What it does: on-camera trainable classifier-by-ID. Returns the most-probable learned-feature
ID and its confidence. Structurally IDENTICAL to classification (same summary layout, mirrored
driver methods).

Summary at 0x0E00 (CLASSIFICATION shape): byte[1] = best feature ID; uint16 LE bytes[2..3] =
best similarity (/10000.0); per-id table from 0x0E10, stride 4.

`updateResult()` reads 64 bytes here.

Capabilities: top learned ID + confidence; confidence of any specific id.

Quirks / enrollment:

- Despite the name, ENROLLMENT/LEARNING is done ON THE CAMERA (physical buttons/UI). There is
  NO I2C "learn" command in the studied code; the host only consumes already-learned features.
- ID 0 = "no match / unknown".
- Valid learnable ID range is not established by the studied code.

### 5.5 Color Recognition (func 5, base 0x1000)

What it does: detects pre-enrolled color blobs; reports count, per-blob color ID, and bounding
box.

Summary at 0x1000 (DETECTION shape): byte[1] = blob count; bytes[2..2+count) = per-blob color
IDs.

Detail: 16-byte record at 0x1000 + 0x30 + 16*(i-2) -> centerX, centerY, w, h (x,y signed and
are the blob CENTER per the Python study).

Capabilities: presence; count; "is color N present"; fetch box of color N. Python iterates IDs
1..7 (up to 7 distinct colors); the Arduino demo only maps 1/2/3.

Quirks / enrollment:

- Color IDs are 1-based (1..7). Enrollment is done OFF-DEVICE via the WonderCam UI/PC tool; no
  color-learning API exists in the studied code.
- Color ID -> hue mapping is device-side config; the demos' red/green/blue-for-1/2/3 mapping is
  convention, not guaranteed.
- DISCREPANCY: COLORDETECT = func 5 in code, but the PDF function list omits 5 (Section 3.1).

### 5.6 Visual Line Following (func 6, base 0x1400)

What it does: detects up to 3 guide lines per frame, each as a straight segment with an angle
and a lateral offset usable for steering.

Summary at 0x1400 (DETECTION shape): byte[1] = line count; bytes[2..) = per-line IDs (1..3).

Detail: 16-byte record at 0x1400 + 0x30 + 16*(i-2). See the struct in Section 4.4
(start_x, start_y, end_x, end_y, angle, offset).

Driver post-processing in `lineId()`: `angle = (angle > 90) ? angle - 180 : angle` (normalizes
to roughly -90..+90); `offset = abs(offset) - 160` (recenters about image center x = 160, i.e.
lateral deviation from frame center in pixels). The Arduino driver stores RAW angle/offset; the
Python driver applies these transforms.

Capabilities: 1..3 lines with stable IDs; per-line endpoints, heading-error angle, cross-track
offset; presence / specific-ID test. Steering controllers should use the Python-style angle and
offset.

Quirks:

- FIELD-LAYOUT DISAGREEMENT (single-source-conflict, important): the Arduino struct names the
  first four int16 as endpoints (start_x, start_y, end_x, end_y); the Python `get_line()`
  unpacks the SAME bytes as a box (x, y, w, h). Same bytes, different interpretation. Trust the
  Arduino endpoint interpretation for geometry, and the Python angle/offset transforms for
  steering. The two cannot both be literally correct - verify against firmware/live data.
- DISCREPANCY/PDF-ERROR (internal field offsets): the raw PDF prints COLLIDING addresses -
  END_Y and THETA both at 0x1436/0x1437, OFFSET mislabeled THETA at 0x1438/0x1439. The PDF
  table is internally broken. The packed code struct is authoritative: end_y @ +6 (0x1436),
  angle @ +8 (0x1438), offset @ +10 (0x143A), reserved +12..+15.
- No line-learning step; IDs 1..3 are assigned automatically by the camera.

### 5.7 QR Code Recognition (func 8, base 0x1800)

What it does: scans a single QR code and returns its payload as a variable-length byte string.

Summary at 0x1800: byte[1] = result count (max 1); length uint16 LE at 0x1820. Payload at
0x1830, up to 400 bytes.

Driver: `qrCodeDetected()` (count > 0), `qrCodeDataLength()` (the `.len` field),
`qrCodeData(buf)` reads `len` bytes from 0x1830.

Capabilities: present/absent; payload length; payload bytes.

Quirks:

- Max 1 QR result.
- PDF cosmetic typo: QRCODE_LENGTH_H at 0x1821 is mislabeled "lower-byte" (it is the high
  byte). Code reads the length as a LE uint16, so it is correct.

### 5.8 Barcode Recognition (func 9, base 0x1C00)

What it does: scans a single barcode; returns payload as a variable-length byte string.

Summary at 0x1C00: byte[1] = count (max 1); length uint16 LE at 0x1C20. Payload at 0x1C30, up
to 400 bytes.

Capabilities / quirks: same shape as QR.

- PDF cosmetic typo (copy/paste): the BARCODE_DATA description references "0x1830 +
  QRCODE_LENGTH". Code correctly uses 0x1C30 + barcode length. Trust the code.

### 5.9 AprilTag / Tag Recognition (func 7, base 0x1E00)

What it does: detects AprilTag fiducials (TAG36H11 family only on WonderCam Standard v1).
Reports per-tag ID, image-space center + bounding box, and full 6-DoF pose.

Summary at 0x1E00 (DETECTION shape, code view): byte[1] = tag count; bytes[2..) = per-tag IDs.

Detail: 32-byte record (Section 4.4) with x, y, w, h + six pose floats.

Capabilities: presence; count; count of specific ID; per-tag center/box/pose. Multiple
simultaneous tags supported.

Quirks / DISCREPANCIES (two HIGH-priority, single-conflict items):

- STRIDE DISAGREEMENT (highest priority): the PDF says tag records are 32 bytes apart (2nd tag
  at 0x1E50, +0x20). The code uses stride 0x32 = 50 decimal:
  `readFromAddr(0x1E00 + 0x30 + 0x32*(i-2), p, 32)` (`WonderCam.cpp:332`). The struct is 32
  bytes, but the per-index advance is 50 in code. The PDF is internally consistent; the code's
  0x32 looks like a hex/decimal typo for 0x20. The shipped Arduino sketch never calls `tagId()`
  so the bug is latent. The Python driver uses 32-byte stride. Trust 32 (0x20); VERIFY on
  hardware.
- SUMMARY OFF-BY-ONE: the PDF places RESULT_NUM at 0x1E02 with IDs at 0x1E03 (0x1E01
  undocumented). The code treats `result_summ[1]` (device 0x1E01) as the count and `[2..]` as
  IDs. So code count/ID indexing may be shifted by one relative to the PDF for tag mode.
  VERIFY on hardware.
- Pose float units are undocumented (translation likely mm or camera-frame; rotation likely
  radians vs degrees unknown). Coordinate frame handedness/origin undocumented.
- Single-byte ID field caps IDs at 255; TAG36H11 allows 0..586. Demo loops only sweep 0..200,
  so high IDs can be missed.
- No enrollment; tags are recognized purely by family decode.

### 5.10 Number Recognition (func 10 / 0x0A, base 0x0D00 - Python-only, UNVERIFIED) - classification variant

What it does: digit/number classification. CLASSIFICATION shape: byte[1] = most-likely number
id (0 = none); uint16 LE bytes[2..3] = confidence (/10000.0); per-id table from 0x0D10.

Capabilities: top number id + confidence; per-id confidence.

Quirks (IMPORTANT for a clean-room driver):

- The base 0x0D00 is corroborated ONLY by the Python driver. The canonical C++ `.cpp`
  `updateResult()` has NO case for 0x0A and never reads it.
- The `numberWithMaxProb()` / `numberMaxProb()` / `numberProbOfId()` methods are DECLARED in
  the superset header but have ZERO implementations in the bundled `.cpp`. The 3.6 Arduino
  sketch actually CALLS them, so as shipped it would FAIL TO LINK. (Section 7.)
- Demo acceptance thresholds are inconsistent (Arduino 0.5, ESP32/C51 0.4, RPi "id != 0").
- No enrollment; appears to be a fixed pretrained classifier.

### 5.11 Landmark / Road-Sign Recognition (func 11 / 0x0B, base 0x0D80 - Python-only, UNVERIFIED) - classification variant

What it does: whole-frame classification into a small fixed set of road-sign / landmark
classes. CLASSIFICATION shape: byte[1] = most-likely class id; uint16 LE bytes[2..3] =
confidence; per-id table from 0x0D90.

Quirks (IMPORTANT):

- Base 0x0D80 is hard-coded in the Python driver only (no named constant); the C++ `.cpp` never
  reads it and `updateResult()` has no case for 0x0B.
- `landmarkIdWithMaxProb()` / `landmarkMaxProb()` / `landmarkProbOfId()` are DECLARED in the
  superset header but NOT DEFINED in the bundled `.cpp` (same orphan-declaration problem as
  number rec).
- ID-TO-MEANING DISAGREEMENT (single-conflict): the Arduino demo maps id 1..5 (1 = Go, 2 = left,
  3 = right, 4 = back, 5 = stop) treating id 1 as a real sign. The Python demo maps id 1 =
  "no landmark detected" (a sentinel) with real signs at 2..6 (2 = forward, 3 = left, 4 = right,
  5 = U-turn, 6 = stop). They are mutually inconsistent; only one matches firmware. The
  underlying register read is identical - the divergence is purely interpretation.
- No enrollment; fixed-class model.

---

## 6. Capability Inventory - What We Can Build

What the I2C interface EXPOSES to a host (and what it does NOT):

| Capability | Exposed? | How |
| --- | --- | --- |
| Read firmware version | Yes | 16 B @ 0x0000 (ASCII) |
| Read hardware/protocol version | No (in studied driver) | declared but unimplemented; no PDF register |
| Turn fill-light LED on/off | Yes | 1 B @ 0x0030 (0/1) |
| LED brightness / RGB | No | only on/off |
| Select active application | Yes | write func # @ 0x0035 |
| Confirm active application | Yes | read @ 0x0035 (mode echo) |
| Latch/refresh results | Yes | read application base register |
| Face: presence/counts/learned-vs-unlearned | Yes | summary @ 0x0400 |
| Face: per-face box by ID or unlearned index | Yes | detail @ 0x0430 + idx*16 |
| Face: enroll/clear IDs over I2C | No | on-camera UI only |
| Object: presence/count/class/box | Yes | summary @ 0x0800, detail @ 0x0830 |
| Classification: top class + confidence + per-id table | Yes | summary @ 0x0C00 |
| Feature learning: top id + confidence + per-id table | Yes | summary @ 0x0E00 |
| Feature learning: trigger learning over I2C | No | on-camera UI only |
| Color: presence/count/id/box | Yes | summary @ 0x1000, detail @ 0x1030 |
| Color: enroll colors over I2C | No | off-device tool |
| Line: 1..3 lines, endpoints, angle, offset | Yes | summary @ 0x1400, detail @ 0x1430 |
| AprilTag: count/id/box/6-DoF pose | Yes | summary @ 0x1E00, detail @ 0x1E30 |
| QR: present + payload (<=400 B) | Yes | length @ 0x1820, data @ 0x1830 |
| Barcode: present + payload (<=400 B) | Yes | length @ 0x1C20, data @ 0x1C30 |
| Number recognition | Partial | Python-confirmed @ 0x0D00; C++ unimplemented |
| Landmark recognition | Partial | Python-confirmed @ 0x0D80; C++ unimplemented |
| Raw image / frame-buffer over I2C | No | no streaming register exists |
| Resolution / exposure / threshold config | No | no such registers found |
| Interrupt / ready GPIO | No | poll-only model |

Buildable on a P2 host: a complete pull-model client for all 8 core applications (faces,
objects, classification, feature learning, color, line follow, QR, barcode) plus AprilTag pose,
with LED control, mode switching, and version readout. Number/landmark are buildable as
classification variants if the host authors the read logic itself (the base addresses are
single-sourced from Python).

---

## 7. Confidence and Cross-Validation

Overall confidence: HIGH for region bases, strides, offsets, and the QR/length layout - both
the code and the PDF were ground-truthed against the actual repo files, so source attribution is
verified rather than inferred.

### 7.1 Corroborated by MULTIPLE sources (code + PDF, or code + Python + PDF)

- All region base addresses: 0x0000, 0x0030, 0x0035, 0x0400, 0x0800, 0x0C00, 0x0E00, 0x1000,
  0x1400, 0x1800, 0x1C00, 0x1E00. Identical in raw code and raw PDF.
- Function numbers 0,1,2,3,4,6,7,8,9. (Color = 5 is code-only; see below.)
- Detail records begin at base + 0x30; the first 48 bytes are the summary header.
- 16-byte detail stride for face/object/color/line.
- Classification and feature-learning: per-id table at base + 0x10, 4-byte stride, uint16
  prob/10000; reserved 2 bytes/entry (PDF explicitly marks them reserved - answers a code open
  question).
- QR/Barcode: length at base + 0x20, payload at base + 0x30, max 400 bytes.
- Firmware version = 16-byte ASCII @ 0x0000.
- LED @ 0x0030 strictly on/off.
- AprilTag struct = int16 x,y + uint16 w,h + 6 LE floats; field order and types match.
- Multi-byte DATA payloads are little-endian.
- FACE header: total @ +1, learned @ +2, unlearned @ +3, ID list from +4 (0xFF = unlearned).
- Coordinates 16-bit signed; confidence/similarity/length 16-bit unsigned.
- The canonical `.cpp` is byte-identical across the 3.2 / 3.6 / 3.7 copies
  (md5 0c9e1c90a862737999ddaec66261f2d5); ESP32 differs only in portability glue. (Drift check,
  high confidence.)

### 7.2 SINGLE-SOURCED (verify before relying on)

- I2C slave address 0x32: code only (PDF never states it). Consistent across all driver
  variants.
- Color function number = 5: code only; PDF omits it.
- Object class 20 (Monitor): code enum only; PDF lists 19 classes.
- Number-rec base 0x0D00 and Landmark-rec base 0x0D80: Python driver only; the C++ `.cpp` never
  reads them.
- Line-follow box-vs-endpoints interpretation: Arduino (endpoints) vs Python (x,y,w,h) -
  same bytes, conflicting interpretation.
- Landmark id-to-meaning mapping: Arduino (1..5) vs Python (1 = none, 2..6) - conflicting.
- Auto-increment of the device address pointer across STOP-separated chunk reads: assumed by
  the code, not documented anywhere.

### 7.3 Confirmed code bugs (not map conflicts)

- `numOfTotalUnlearnedFaceDetected()` returns `(int)result_summ` instead of `result_summ[3]`.
- `objDetected()` index/loop logic can fall off the end (UB) and decrements `index` only on a
  match.
- `getFaceOfIndex()` / `tagId()` use pre-decrement-then-==0 (implies 1-based index).
- AprilTag `tagId()` advances 0x32 = 50 bytes/index while the record is 32 bytes (likely a
  hex/decimal typo; latent because the shipped sketch never calls it).
- Orphan declarations: number*/landmark* methods are declared in the superset header and CALLED
  by the 3.6 sketch, but have NO implementation in the bundled `.cpp` -> as-shipped link
  failure. The real implementation lives in a newer upstream Hiwonder library or in the Python
  driver. These are almost certainly thin wrappers over the existing classification read path,
  selected by the NUMBER_REC / LANDMARK_REC mode.
- PDF-only cosmetic typos (code is correct): QRCODE_LENGTH_H "lower-byte" mislabel; BARCODE_DATA
  references QR base/length; feature-learning sub-registers mislabeled "CALSSIFICATION";
  line-follow theta/offset colliding addresses.

---

## 8. Open Questions and Risks for the P2 Driver

Items to verify against real hardware (logic analyzer) or against an authoritative/newer PDF
before trusting them in a P2 driver:

1. ADDRESS BYTE ORDER (high priority): confirm the 16-bit register address is sent LOW byte
   first (the code's behavior) and not HIGH byte first (the PDF's contradictory prose). The code
   is authoritative; verify with an analyzer.
2. CHUNK AUTO-INCREMENT (high priority): confirm the device auto-increments its internal read
   pointer across STOP-separated 32-byte `requestFrom` chunks. If it does not, every read > 32
   bytes (classification 128 B, feature 64 B, QR/barcode payloads up to 400 B) is corrupt. A P2
   driver may need to re-send the address per chunk, or use repeated-start.
3. APRILTAG TAG STRIDE (high priority): 32 bytes (PDF, Python) vs 0x32 = 50 bytes (Arduino
   `tagId`). Determine the firmware's actual per-index advance for tag index > 0.
4. APRILTAG SUMMARY OFF-BY-ONE: is the tag count at device 0x1E01 (code) or 0x1E02 (PDF)? What
   is 0x1E01? This shifts count/ID indexing by one.
5. COLOR FUNCTION NUMBER: confirm color = 5 in firmware (PDF omits it).
6. OBJECT CLASS 20: confirm the device emits class id 20 (Monitor); the PDF documents only 19
   classes.
7. LINE-FOLLOW FIELD SEMANTICS: are the first four int16 true segment endpoints (Arduino) or a
   box (Python)? They cannot both be right. Also confirm raw angle range/zero-reference and raw
   offset range/sign before Python's normalization.
8. NUMBER / LANDMARK BASES: confirm 0x0D00 (number) and 0x0D80 (landmark), and supply the
   missing C++ read logic. These are single-sourced from Python. Verify the per-id table stride
   (assumed 4 bytes by analogy) for these two modes.
9. FACE ID-LIST WIDTH: does firmware ever report more than 29 faces (code) up to 38 (PDF)? What
   is the real cap per function for face/object/color/line/tag?
10. APRILTAG POSE UNITS and coordinate-frame handedness/origin: undocumented.
11. CLASSIFICATION / FEATURE class counts: how many class/feature/number/landmark ids exist? A
    P2 driver must read enough summary bytes to cover the highest id of interest.
12. MAX WRITE PAYLOAD: the only writes today are 1 byte. If future firmware adds multi-byte
    config/learn commands, the AVR ~30-byte single-transaction write limit is a constraint to
    rethink on P2 (which has no such buffer limit).
13. RESET / READINESS after mode switch: the only readiness signal is the 0x0035 echo. Confirm
    that the first few `updateResult()` calls after a switch do not return stale/empty summaries
    while the model spins up (mode change can take up to ~3 s).
14. UNDOCUMENTED CONFIG REGISTERS: confirm whether 0x0000/0x0030/0x0035 are truly the only
    writable registers, or whether resolution/exposure/threshold/learn/save registers exist in
    firmware but are absent from the studied driver.
15. ENUM DRIFT: `APPLICATION_MAX` is 10 in the base header and 12 in the number/landmark
    superset. A P2 driver should fix its own canonical numbering and not assume the camera's.

---

## 9. Implications for a P2 Spin2 Driver (Proposed API Surface Shape)

This is a shape proposal only - no Spin2 code. It describes the layers and method groups a P2
driver should expose, derived from the C++ driver's proven structure.

### 9.1 Layering

- LOW LEVEL (private): `readFromAddr(addr, ptr, len)` and `writeToAddr(addr, ptr, len)`. On P2,
  the 32-byte AVR chunk limit does not apply; however, until chunk auto-increment is verified
  (Open Question 2), the safe default is to mirror the C++ behavior - send the 2-byte
  little-endian address once, then read in chunks. A P2 driver SHOULD make the chunking and the
  address re-send strategy explicit and configurable so it can be corrected after hardware
  testing.
- SYSTEM LAYER: `start`/`begin` (I2C pin/baud config; default 400 kHz), `firmwareVersion`,
  `setLed(on)`, `currentFunc`, `changeFunc(func)` (blocking confirm-and-poll with a bounded
  timeout, mirroring the ~3-4 s vendor behavior but with a caller-supplied cap), `updateResult`.
- RESULT LAYER: per-application accessors that read the cached summary plus lazy detail reads.

### 9.2 Mode and result-cache model

- Keep a cached `current` mode (re-read at the top of `updateResult`) and a `summary[]` buffer
  (size at least 128 bytes to cover classification).
- `updateResult` reads the active mode's summary header (48 bytes for most modes; 64 for
  feature; 128 for classification). Detail records are fetched on demand, not in
  `updateResult`.

### 9.3 Proposed accessor groups (one per application)

- Face: `anyFaceDetected`, `numFaces`, `numLearned`, `numUnlearned`, `faceOfIdDetected(id)`,
  `getFaceById(id, @rec)`, `getUnlearnedFace(index, @rec)`. (Fix the unlearned-count and
  index-base bugs; record = x,y,w,h int16/uint16.)
- Object: `anyObject`, `numObjects`, `objectIdDetected(id)`, `numObjectsOfId(id)`,
  `getObject(id, index, @rec)`. (Reimplement the loop correctly; do not port the UB.)
- Classification: `classTopId`, `classTopProb`, `classProbOfId(id)` (prob = raw/10000).
- Feature learning: `featureTopId`, `featureTopProb`, `featureProbOfId(id)`.
- Color: `anyColor`, `numColors`, `colorIdDetected(id)`, `getColor(id, @rec)`.
- Line: `anyLine`, `numLines`, `lineIdDetected(id)`, `getLine(id, @rec)` returning endpoints
  plus the normalized angle and centered offset (apply the >90 wrap and abs()-160 transform; but
  keep the raw struct interpretation question open per Section 5.6).
- AprilTag: `anyTag`, `numTags`, `tagIdDetected(id)`, `numTagsOfId(id)`,
  `getTag(id, index, @rec)` returning x,y,w,h + 6 pose floats. Make the per-index stride a named
  constant (default 32, pending Open Question 3).
- QR: `qrDetected`, `qrLength`, `qrData(@buf)`.
- Barcode: `barcodeDetected`, `barcodeLength`, `barcodeData(@buf)`.
- Number / Landmark (optional, behind a "verified" flag): `numberTopId`/`numberTopProb` and
  `landmarkTopId`/`landmarkTopProb`, reading bases 0x0D00 / 0x0D80 - implement as classification
  variants, clearly labeled single-sourced/unverified until hardware-confirmed.

### 9.4 Design notes carried from the research

- Use named constants for every base, the 0x30 detail offset, the 16/32-byte strides, the 0x10
  per-id-table offset, the 4-byte per-id stride, and the /10000 prob divisor.
- All multi-byte data is little-endian; P2 Spin2 reads bytes explicitly, so assemble
  low-byte-first. Coordinates are signed (sign-extend int16); confidences/lengths are unsigned.
- Do NOT propagate the confirmed C++ bugs (unlearned-face count, objDetected loop, index-base
  off-by-ones, AprilTag 0x32 stride).
- Treat number/landmark as classification-shaped and author the read logic directly; do not
  expect the vendor `.cpp` to be a reference for them.
- Provide a clean separation between "select mode" (slow, blocking, up to ~3 s) and "poll
  result" (fast) so the caller can manage timing.
