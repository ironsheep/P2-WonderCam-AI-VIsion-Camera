# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Parallax Propeller 2 (P2) Spin2 driver for the **Hiwonder WonderCam AI Vision Camera**, an I2C smart camera that runs on-device vision models (face/object/color detection, line following, AprilTag, QR/barcode, image classification, feature learning).

This began as a **greenfield port** of the published WonderCam protocol from the vendor's reference SDKs. As of v0.1.0 the driver, its front-panel demo, and a regression top exist in `src/` and compile clean under `pnut-ts`; what remains is the host-only hardware bring-up (see the status in `README.md` and the bring-up playbook in `DOCs/plans/`).

## Dual environment: compile here, flash on the host

The working tree is **shared between a macOS host and this Linux dev container**. The two environments are not equivalent:

| Environment | Tooling | Can do | Cannot do |
|---|---|---|---|
| **Linux dev container** (where you usually run) | `pnut-ts` only | compile / lint / listings | flash, download, or run on hardware (no `pnut-term-ts`, no USB); flexspin compat compile (no `flexspin`) |
| **macOS host** (native) | `pnut-ts` + `pnut-term-ts` + `flexspin` | compile, flexspin compat compile, flash + run on a P2 board | — |

So: **anything that downloads to or runs on hardware — and the flexspin compat compile — must happen in a host-native session, not in the container.** Inside the container the `pnut-term-ts` flash/run step and the `flexspin` compat compile fail because those tools are absent — that is expected, not a misconfiguration. Hand that work off to the host. The canonical slot values and skill behavior for this split live in `.claude/skill-conventions.md` (see its dual-environment header).

## Build / compile

The compiler is **`pnut-ts`** (PNut-TS, the TypeScript Spin2 compiler, at `/usr/local/bin/pnut-ts`). No Makefile or build script — compile the top-level `.spin2` file directly (it pulls in `OBJ`-referenced children automatically):

```bash
pnut-ts -l src/demo_wondercam.spin2      # compile the demo top + emit .lst listing
pnut-ts -l -m src/demo_wondercam.spin2   # also emit .map memory map
pnut-ts -d src/demo_wondercam.spin2      # compile with DEBUG enabled
```

Source layout (Iron Sheep naming): driver object `src/isp_wondercam.spin2` (composing the provided `src/isp_i2c_singleton.spin2`), demo top `src/demo_wondercam.spin2`, regression top `src/test_wondercam.spin2`. The driver carries a `VERSION` CON. There is no host-side unit-test runner — "tests" in the Spin2 sense are P2 programs run on hardware (host-only; see Part 6 of the authoring guide); the in-repo `TEST_COMMAND` is a compile-clean check.

## Mandatory: the Spin2 Authoring Guide

**`DOCs/policy/SPIN2-AUTHORING-GUIDE.md` is a hard requirement for every `.spin2` file in this repo.** Read it before writing or editing Spin2. It is not style advice — many rules prevent silent miscompiles in pnut-ts. The highest-impact rules:

- **ASCII only** — no Unicode in code/strings/signatures (em dashes, curly quotes, ellipsis all forbidden). Box-drawing chars are allowed *only inside comments*.
- **`>=` is comparison; `=>` is a case-range separator** — they are not interchangeable and the compiler will not warn.
- **Identifiers are case-insensitive** — avoid collisions with built-ins (`cogId`→`COGID`, `string`→`STRING()`, `send`→`SEND`, `bool` is reserved in pnut-ts ≥1.52). Locals must not shadow PUB/PRI/DAT/VAR names.
- **No method overloading** — every method name is unique regardless of arity.
- **Pointers are not C** — dereference with type brackets (`BYTE[ptr]`), struct fields use `.` not `->`, typed pointers need a version directive.
- **API methods return error codes, not booleans**; single exit point per method; exit loops with `quit`, never `return`; no magic numbers.

When in doubt about P2 silicon, PASM2, or Spin2 syntax, use the **p2kb-mcp** tools (`p2kb_get`, `p2kb_find`) rather than web search — web results conflate P1 and P2.

## Source of truth for the protocol: REF-NO-COMMIT/

`REF-NO-COMMIT/` holds vendor reference material and is **not committed** (the folder name is the instruction). Port *from* it; do not commit it.

- `Specification.pdf`, `Register list.pdf` — the WonderCam I2C register map.
- `3. Multi-Controller Communication Tutorial/3.x .../` — working driver implementations per feature, in Arduino C++ (`WonderCam.h` / `WonderCam.cpp` / `*.ino`), ESP32 Arduino, and MicroPython (`WonderCam.py`). These are the canonical behavior to replicate in Spin2.

### Protocol essentials (from the reference `WonderCam.cpp`)

- **I2C address `0x32`**. Registers are addressed by a **16-bit little-endian address** sent as two bytes (low, high) before each read/write.
- Reads are chunked in 32-byte I2C transactions.
- **`0x0035`** selects the active vision application (the `APPLICATION` enum: face, object, classification, feature-learning, color, line, AprilTag, QR, barcode). Writing it switches modes.
- Each application publishes results in its own memory region read via `updateResult()` + per-feature getters: e.g. face `0x0400`, object `0x0800`, classification `0x0C00`, feature `0x0E00`, color `0x1000`, line `0x1400`, AprilTag `0x1E00`, QR `0x1800`, barcode `0x1C00`. A per-region summary header (offset 0) carries the detection count; individual results are fixed-size structs at `region + 48 + index*stride`.
- Result structs (`WonderCamFaceDetectResult`, `...ColorDetectResult`, `...LineResult`, `...AprilTagResult`, etc.) are packed; mirror their field order and widths exactly when defining Spin2 `STRUCT`s. AprilTag results include `float` pose fields — handle endianness/width deliberately.

The reference `WonderCam` class API (in the `.h`) is the feature surface to mirror: version queries, `changeFunc`/`currentFunc`, `setLed`, `updateResult`, and the `anyXDetected` / `numOfX` / `getXOfId` family per application.

## Environment

Development runs in the `.devcontainer` (VS Code Dev Containers / docker-compose). The container's `postCreateCommand` installs `pnut-ts` from the bundled `.devcontainer/pnut-ts-*.zip` and `libtesseract5`. Editor settings enforced for this repo: LF line endings, tab size 4, trim trailing whitespace.
