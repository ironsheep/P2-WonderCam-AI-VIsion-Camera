# WonderCam Driver - Punch List Archive (2026-06-05)

Confirmed-done punch-list items swept from `DOCs/plans/PUNCH-LIST.md` at the
`wc-driver-v1` sprint closeout (2026-06-05). Completed items only - this file is
not re-edited after writing.

- [x] **Fold concrete reserved-identifier collisions into the authoring guide.** DONE in
  `#13` (2026-06-05). Added `wc` (PASM2 carry flag, as an object alias), `step` (the
  `repeat ... step` keyword, as a parameter), `neg` (PASM2 instruction, as a local) AND the
  collisions hit later building the regression top - `skip`/`skipf` (PASM2 instructions) and
  the `pa`/`pb`/`ptra`/`ptrb`/`dira` register family - to the `SPIN2-AUTHORING-GUIDE.md` §1.3
  known-hazards table as concrete examples, with a note that every one was a real this-project
  collision.
