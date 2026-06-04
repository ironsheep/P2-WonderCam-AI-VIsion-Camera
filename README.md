# P2-WonderCam-AI-VIsion-Camera

A Parallax Propeller 2 (P2) Spin2 driver for the **Hiwonder WonderCam** AI vision camera.

## What this is

The WonderCam is an I2C smart camera (Kendryte K210 + OV2640) that runs vision
models on-device and reports results over I2C - no image streaming required of the
host. A host MCU selects one of its applications and polls the result registers.
The vendor ships drivers for Arduino, ESP32, STM32, Raspberry Pi, and C51, but **not
for the Propeller 2**. This project fills that gap: a clean-room Spin2 driver so any
P2 design can use the WonderCam.

## What we're doing

Porting the WonderCam I2C protocol to a P2 Spin2 object, written to the Iron Sheep
P2 driver conventions and the project's mandatory `DOCs/policy/SPIN2-AUTHORING-GUIDE.md`.

We are deliberately working in phases - **understand the device fully before writing
any driver code:**

1. **Research (done)** - studied the vendor reference SDKs (Arduino C++, ESP32,
   MicroPython, register-map PDFs) across all camera applications and produced a
   verified theory of operation: `DOCs/research/WONDERCAM-THEORY-OF-OPERATION.md`.
   It documents the I2C wire protocol, the mode-select model, the per-application
   result memory map, every capability the interface exposes, and - importantly -
   where the vendor's own examples are buggy or single-sourced (so we don't faithfully
   port mistakes).
2. **Requirements (next)** - turn the theory of operation into a driver spec: which
   applications v1 supports, the public API surface, and how we handle the items that
   still need hardware confirmation.
3. **Implementation** - author the Spin2 driver object plus a demo and a regression
   top, iterating with the P2 dev cycle.

## Capabilities the driver targets

A pull-model client for the camera's vision applications: face detection, object
detection, image classification, feature learning, color recognition, visual line
following, AprilTag (with 6-DoF pose), QR and barcode reading, plus the number and
road-sign classification variants - along with LED control, mode switching, and
firmware-version readout. (The interface does **not** expose raw frames, on-device
enrollment, or camera configuration over I2C - see the theory of operation.)

## Build and run environments

The working tree is shared between a Linux dev container and a macOS host, which are
**not** equivalent:

| Environment | Tools | Role |
|---|---|---|
| Linux dev container | `pnut-ts` | compile / lint (no hardware) |
| macOS host (native) | `pnut-ts` + `pnut-term-ts` + `flexspin` | compile, compat-compile, **flash + run** on a P2 board |

Anything that downloads to or runs on hardware happens on the host, not in the
container. See `CLAUDE.md` for details.

## Planned source layout

```
src/isp_wondercam.spin2     driver object (carries a VERSION CON)
src/demo_wondercam.spin2    demo / top
src/test_wondercam.spin2    regression top (compile-clean check)
```

## Key documents

- `CLAUDE.md` - working guide for this repo (build, conventions, dual-environment).
- `DOCs/research/WONDERCAM-THEORY-OF-OPERATION.md` - the device study.
- `DOCs/policy/SPIN2-AUTHORING-GUIDE.md` - mandatory Spin2 coding standard.

## Status

Pre-implementation: research complete, `src/` is intentionally empty. Driver authoring
begins after the requirements spec.

## License

See `LICENSE`.
