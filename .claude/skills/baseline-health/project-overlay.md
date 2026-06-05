# WonderCam overlay - baseline-health

## Augments §1-§4 - No behavioral suite: the compile-clean sweep IS the baseline gate

This project has no host-runnable behavioral test suite (hardware-only
execution; see the dual-environment note in skill-conventions.md). Map the
central steps onto a compile sweep:

- §1 Clean build: {{BUILD_COMMAND}} compiles the demo top - zero warnings/errors.
  The flexspin compat compile is host-only (see p2-dev-cycle overlay) and is not
  part of the in-container gate.
- §2 "Run the full test suite": there is no behavioral runner. {{TEST_COMMAND}}
  compiles the regression top src/test_wondercam.spin2. The unit of a "failing
  test" is a NON-COMPILING object; the test target is the test top.
- §3 Never allow skips: a "skip" is any .spin2 object excluded from the compile
  sweep. Every object intended to ship must be reachable from a compiled top
  (demo or test). Name any object not covered.
- §4 Group by cause: group compile errors by shared cause (e.g. one renamed CON
  breaking many call sites) and fix by group.

Behavioral health (does the driver actually talk to the camera) is verified OUT
OF BAND via an on-hardware test playbook on the macOS host. baseline-health here
asserts COMPILE health only.
