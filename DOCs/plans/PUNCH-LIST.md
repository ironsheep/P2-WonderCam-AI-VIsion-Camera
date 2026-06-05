# WonderCam Driver - Punch List

Active outstanding items. Confirmed-done items are swept to a dated archive by the
`punch-list-maintenance` skill at sprint closeout.

## Open

- [ ] **Optional I2C bus-locking for shared-bus deployments.** Deferred from v0.1.0
  (decision 2026-06-05). The v1 driver assumes the WonderCam sits on its OWN
  dedicated I2C bus with no other devices, so no lock is needed. If a future
  deployment shares the bus, add a caller-supplied lock acquired/released around
  each transaction in `src/isp_wondercam.spin2` (`writeToAddr`/`readFromAddr`) plus
  a `lockId` parameter on `start()`. Relates to spec FR-5 (shared-bus readiness),
  which v1 partially satisfies (own-instance object) minus the lock.

- [ ] **Front-panel demo polish (deferred from `#9`, 2026-06-05).** Two cosmetic enhancements the
  §9 per-mode views skipped to stay clean/compiling: (a) floating per-box id labels inside the
  camera view need a SECOND font-strip row rendered on the dark VIEW_BG (the analog-meter
  stacked-row trick) so the labels do not show the PANEL_BG cell background as a seam on the dark
  view - v1 lists detected ids/values in the side INFO panel instead; (b) AprilTag 6-DoF pose
  (the 6 IEEE-754 float LONGs in tag_result_t) is not shown numerically (would need float
  formatting) - v1 draws the tag box + count only. Both are demo-only niceties, not v0.1.0 blockers.

- [ ] **Confirm probability return representation (Stephen's call).** The
  classification-style `*TopProb` / `*ProbOfId` methods in `src/isp_wondercam.spin2`
  currently return a SCALED INTEGER `0..PROB_DIVISOR` (raw, divide by 10000 for
  0.0..1.0), with negatives reserved for error codes (E_MODE / E_ARG). This keeps the
  driver float-free and lets the return double as value-or-error, matching the driver's
  integer idiom and the raw-float-passthrough used for AprilTag pose. The vendor C/Python
  return a `float` (raw / 10000.0). If a float return is preferred, it is a localized change
  to those methods (and the `#9` demo / `#10` regression readouts). Decide before v0.1.0
  ships. Introduced by task `#7` (2026-06-05).
