# Project skill conventions - WonderCam

Slot values for the central skill set. See `~/.claude/skills-docs/SKILLS-MAINT.md`
for the full schema. Required slots have no default; optional slots fall back to
documented defaults when omitted.

> ## DUAL ENVIRONMENT - READ THIS FIRST
>
> This project's filesystem is SHARED between a macOS host and a Linux dev
> container, on the same working tree. The two environments have DIFFERENT
> capabilities:
>
> | Environment | Tools present | Can do | Cannot do |
> |-------------|---------------|--------|-----------|
> | Linux dev container (default here) | `pnut-ts` ONLY | COMPILE Spin2 (build, lint, listings) | flash / download / run on hardware; flexspin compat compile |
> | macOS host (native) | `pnut-ts` + `pnut-term-ts` + `flexspin` | compile, flexspin compat compile, AND flash / download / run on a P2 board | - |
>
> Consequences:
> - `BUILD_COMMAND` / `TEST_COMMAND` below are COMPILE-CLEAN `pnut-ts` checks -
>   they run in EITHER environment, including this container.
> - The `p2-dev-cycle` flash/run steps (`pnut-term-ts`) are HOST-ONLY. In the
>   container they fail (tool absent) - expected, not a misconfiguration. Hand
>   flash/run work to a host-native session.
> - `P2_COMPAT_COMPILE_COMMAND` (`flexspin`) is likewise HOST-ONLY. The secondary
>   portability compile runs on the host; it cannot run in the container.
> - There is no USB device visible inside the container.

---

## Identity

```yaml
USER_NAME:    Stephen
PROJECT_NAME: WonderCam
```

## Build & test

Compile-clean checks via `pnut-ts`. Runnable in the container (compiler is
present). On-hardware execution is a host-only concern - see the dual-environment
note above and the P2 section below.

```yaml
BUILD_COMMAND:         pnut-ts -l src/demo_wondercam.spin2
TEST_COMMAND:          pnut-ts -l src/test_wondercam.spin2
CANONICAL_TEST_TARGET: pnut-ts compile-clean (Linux arm64 devcontainer); on-hardware runs are host-only via p2-dev-cycle
```

## Build version

Lives as a `VERSION` CON in the driver object. The file is created during
development; this is a forward reference.

```yaml
BUILD_VERSION_LOCATION: src/isp_wondercam.spin2
BUILD_VERSION_KEY:      VERSION
BUILD_VERSION_EXAMPLE:  0.1.0
```

## Doc paths

```yaml
PLAN_DIR:          DOCs/plans/
PLAN_ARCHIVE_DIR:  DOCs/plans/archive/
ANALYSIS_DIR:      DOCs/research/
PUNCH_LIST_DOC:    DOCs/plans/PUNCH-LIST.md
RELEASE_NOTES_DOC: DOCs/RELEASE-NOTES.md
SPEC_DOC:          DOCs/spec/WonderCam-Driver-Requirements.md
```

## Audience & vocabulary

```yaml
RELEASE_NOTES_AUDIENCE: P2 developers integrating the driver
TEST_FLEET_DESCRIPTION: the P2 development board
```

## Tracking-readiness

```yaml
PROJECT_INIT_DATE: 2026-06-04
```

## P2 development cycle

Declarative path (no wrapper scripts). COMPILE (`pnut-ts`) works in the
container; FLASH/RUN (`pnut-term-ts`) and the flexspin COMPAT compile are
HOST-ONLY per the dual-environment note at the top of this file.

```yaml
# --- Required ---
P2_WORK_DIR:    src/                 # cycle cd's here; P2_LOG_DIR defaults to src/logs/
SPIN2_TOP_FILE: demo_wondercam.spin2 # relative to P2_WORK_DIR

# --- Declarative-cycle tuning ---
P2_CLOCK_FREQ:       320_000_000     # canonical _CLKFREQ; pre-flash check compares source against this
P2_DEBUG_BAUD:       2_000_000       # DEBUG serial baud; verified pre-flash against source
RUN_TIMEOUT_SECONDS: 60              # headless-run safety timeout (host)
P2_LOG_DIR:          src/logs/       # cycle log destination
P2_END_MARKER:       DEBUG_END_SESSION   # phrase pnut-term-ts exits on; verified present in source
P2_INCLUDE_PATHS:    []              # driver/demo/test co-located in src/; no extra -I needed

# Secondary portability compile - HOST-ONLY (flexspin absent in container):
P2_COMPAT_COMPILE_COMMAND: flexspin -2 {top}

# P2_USB_DEVICE omitted -> auto-detect (single board; host-only, no device in container).
# P2_DEBUG_MASK omitted -> source-level DEBUG_MASK controls verbosity until channelized debug is adopted.
# P2_COMPILE_COMMAND / P2_FLASH_COMMAND omitted -> declarative path in use (no wrapper scripts).
```
