# WonderCam overlay - p2-dev-cycle

## Augments §0 / §2 / §3 - Environment capability gating (compile in container, flash on host)

The working tree is shared between a Linux dev container and a macOS host
(see CLAUDE.md and .claude/skill-conventions.md). Tool availability differs:
- Container (usual default): pnut-ts ONLY. No pnut-term-ts, no flexspin, no USB.
- macOS host: pnut-ts + pnut-term-ts + flexspin; the only place flash/run happens.

- §0 First-session checks: `pnut-term-ts -n` works only on the host. In the
  container the binary is ABSENT (a "command not found", not a "zero devices"
  report). Do not read an absent binary as a hardware fault - recognize the
  compile-only environment and skip §0. Run §0 only on the host.
- §2 Compatibility compile: {{P2_COMPAT_COMPILE_COMMAND}} (flexspin) is
  HOST-ONLY. Skip in the container; run on the host.
- §3 Flash to RAM and run: pnut-term-ts is HOST-ONLY. The cycle CANNOT reach §3
  in the container. A compile-only stop after §1 is the only valid in-container
  outcome; hand flash/run to a host-native session and name that in the hand-back.

A missing pnut-term-ts / flexspin in the container is EXPECTED, not a
misconfiguration - never "fix" it by installing or by bit-banging around it.

## Augments §1 - Compile gate: SPIN2-AUTHORING-GUIDE conformance

Before a compile counts as clean, source MUST conform to
DOCs/policy/SPIN2-AUTHORING-GUIDE.md (a hard requirement - several rules prevent
silent pnut-ts miscompiles). Highest-impact gates: ASCII-only in
code/strings/signatures (box-drawing allowed only in comments); >= vs =>;
case-insensitive identifier collisions (cogId/string/send/bool); no method
overloading; pointer/type-bracket semantics; API methods return error codes;
single exit; quit not return; no magic numbers. Project-specific verified
pnut-ts gotchas accumulate in this section as discovered.
