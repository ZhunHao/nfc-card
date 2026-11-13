#!/usr/bin/env bash
# Single green/red gate for the whole project.
# Exit 0 = everything passes. Any non-zero = something is broken.
#
# Runs, in order:
#   ERC + DRC on each KiCad project  (SKIP until the design files exist)
#   Schematic parity + board thickness on each board
#   Closed copper loops inside the coil on each board (scripts/check_loops.py)
#   Firmware host tests, AVR builds, memory and instruction checks (SKIP until sources exist)
#
# Every check runs even if an earlier one failed, so one invocation reports
# every problem. Hence `set -uo pipefail` and NOT `set -e`.
#
# kicad-cli is located by this script rather than inherited from PATH, so the
# gate behaves identically from a shell, a Makefile, or CI. Override with:
#   KICAD_CLI=/path/to/kicad-cli ./scripts/check.sh
# The resolved binary must report KiCad 10.x -- Konnect and the project's file
# format require it, and this machine has more than one kicad-cli on PATH.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

readonly KICAD_CLI_FALLBACK="/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
# check_loops.py needs pcbnew, which only KiCad's bundled Python has. Override with
# KICAD_PYTHON=/path/to/python3.
readonly KICAD_PYTHON_FALLBACK="/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
# Largest supply loop allowed inside the coil, mm². Caps are near-shorts at 13.56 MHz, so
# each supply loop is a shorted turn; 100 mm² is ~3 % of a mean coil turn (~3,500 mm²).
# Rev B: Terminal 91.7 (C3-U1), Orbit 45.6 (C4-U1).
readonly MAX_SUPPLY_LOOP_MM2="100"
readonly KICAD_REQUIRED_MAJOR="10"
readonly REPORT_DIR="build/reports"
# 0.8 mm, 2 layers: bank-card thickness (ISO/IEC 7810 ID-1 is 0.76 mm). Was 1.0 mm,
# inherited from NTUAS. The build scripts set it through scripts/board_thickness.py,
# which must agree with this value.
readonly BOARD_THICKNESS_MM="0.8"

STATUS=0
mkdir -p "$REPORT_DIR"

# Resolution order: explicit KICAD_CLI override, then PATH, then the standard
# Homebrew/KiCad.app location. Prints the path on success, returns 1 on failure.
# Note: the script has already cd'd to REPO_ROOT, so a *relative* KICAD_CLI is
# resolved relative to REPO_ROOT, not the caller's working directory. Pass an
# absolute path unless you specifically want repo-relative behaviour.
resolve_kicad_cli() {
  if [ -n "${KICAD_CLI:-}" ]; then
    if [ -x "$KICAD_CLI" ]; then
      printf '%s' "$KICAD_CLI"
      return 0
    fi
    return 1
  fi

  local from_path
  from_path="$(command -v kicad-cli 2>/dev/null)"
  if [ -n "$from_path" ]; then
    printf '%s' "$from_path"
    return 0
  fi

  if [ -x "$KICAD_CLI_FALLBACK" ]; then
    printf '%s' "$KICAD_CLI_FALLBACK"
    return 0
  fi

  return 1
}

KICAD_CLI_BIN="$(resolve_kicad_cli)" || KICAD_CLI_BIN=""
readonly KICAD_CLI_BIN

# `kicad-cli version` is run exactly once, here, and the answer cached -- the
# per-check helpers below must never shell out for it. Empty string means either
# no CLI was resolved or `version` itself failed to run, both of which are
# treated as "cannot be trusted".
KICAD_CLI_VERSION=""
if [ -n "$KICAD_CLI_BIN" ]; then
  KICAD_CLI_VERSION="$("$KICAD_CLI_BIN" version 2>/dev/null | head -n 1)" || KICAD_CLI_VERSION=""
fi
readonly KICAD_CLI_VERSION

# True only when the cached version string starts with the required major.
kicad_cli_version_ok() {
  case "$KICAD_CLI_VERSION" in
    "${KICAD_REQUIRED_MAJOR}".*) return 0 ;;
    *) return 1 ;;
  esac
}

# A design file that cannot be checked is a failure, not a skip -- silently
# passing an unchecked board is exactly the bug this gate exists to prevent.
report_missing_cli() {
  local kind="$1" name="$2"
  echo "FAIL ${kind}:${name} (kicad-cli not found - set KICAD_CLI=/path/to/kicad-cli, or install KiCad 10.x at ${KICAD_CLI_FALLBACK})"
  STATUS=1
}

# Same rule for a CLI of the wrong vintage: a KiCad 9 binary may refuse or,
# worse, misread a KiCad 10 design, so it is a FAIL and never a SKIP or PASS.
report_bad_version() {
  local kind="$1" name="$2"
  local found="${KICAD_CLI_VERSION:-unknown (version command failed)}"
  echo "FAIL ${kind}:${name} (${KICAD_CLI_BIN} reports version ${found}; KiCad ${KICAD_REQUIRED_MAJOR}.x is required - set KICAD_CLI=/path/to/kicad-cli, e.g. KICAD_CLI=${KICAD_CLI_FALLBACK})"
  STATUS=1
}

# Returns 0 when the resolved CLI is safe to run against a real design file.
# Emits the appropriate FAIL line and returns 1 when it is not.
kicad_cli_usable() {
  local kind="$1" name="$2"
  [ -n "$KICAD_CLI_BIN" ] || { report_missing_cli "$kind" "$name"; return 1; }
  kicad_cli_version_ok || { report_bad_version "$kind" "$name"; return 1; }
  return 0
}

run_erc() {
  local sch="$1" name="$2"
  [ -f "$sch" ] || { echo "SKIP erc:$name (no schematic yet)"; return 0; }
  kicad_cli_usable erc "$name" || return 0

  "$KICAD_CLI_BIN" sch erc \
    --exit-code-violations \
    --severity-error \
    --format report \
    -o "${REPORT_DIR}/${name}-erc.rpt" \
    "$sch"
  local rc=$?

  if [ "$rc" -eq 0 ]; then
    echo "PASS erc:$name"
  else
    echo "FAIL erc:$name (exit $rc) -> ${REPORT_DIR}/${name}-erc.rpt"
    STATUS=1
  fi
}

# Schematic parity, checked in its own pass.
#
# KiCad files every schematic-parity finding at *warning* severity. The DRC run
# in run_drc uses --severity-error, which strips all of them, so the
# --schematic-parity flag there enforces nothing at all -- a board that does not
# match its schematic sailed straight through this gate. Parity therefore needs
# a --severity-all run. That run also surfaces cosmetic warnings (silk_overlap,
# silk_over_copper); those must NOT fail the gate, because a gate that cries
# about silkscreen aesthetics is a gate people learn to ignore. So the parity
# verdict comes from the reported parity *count*, never from this run's exit
# code, and the error-severity run above remains the only thing that can fail on
# a DRC violation.
#
# The count is read from kicad-cli's stdout summary ("Found N schematic parity
# issues") and deliberately NOT from the report body's "** Found N Footprint
# errors **" header. When the schematic cannot be loaded, kicad-cli writes
# "** Found 0 Footprint errors **" into the report -- a false green -- while
# printing "Failed to fetch schematic netlist for parity tests." on stderr and
# omitting the stdout summary line entirely. So a missing summary line means
# parity was never evaluated, which is a FAIL, not a pass. stderr is left
# unredirected so that kicad-cli's own explanation reaches the operator.
run_parity() {
  local pcb="$1" name="$2"
  local report="${REPORT_DIR}/${name}-drc-all.rpt"

  local out
  out="$("$KICAD_CLI_BIN" pcb drc \
    --severity-all \
    --schematic-parity \
    --format report \
    -o "$report" \
    "$pcb")"
  local rc=$?

  if [ "$rc" -ne 0 ]; then
    echo "FAIL parity:$name (kicad-cli exit $rc) -> $report"
    STATUS=1
    return 0
  fi

  local count
  count="$(printf '%s\n' "$out" \
    | sed -n 's/.*Found \([0-9][0-9]*\) schematic parity issues.*/\1/p' \
    | tail -n 1)"

  if [ -z "$count" ]; then
    echo "FAIL parity:$name (parity not evaluated - schematic missing or unannotated) -> $report"
    STATUS=1
  elif [ "$count" -ne 0 ]; then
    echo "FAIL parity:$name ($count schematic parity issues) -> $report"
    STATUS=1
  else
    echo "PASS parity:$name"
  fi
}

# Prints the board thickness in mm, or nothing when it cannot be determined.
# The value lives in the top-level `(general (thickness N))` block; the bare
# token `thickness` also appears inside every `(font ...)`, so the scan is
# anchored to the general block and abandoned at its closing paren.
board_thickness_mm() {
  awk '
    /\(general/ { in_general = 1 }
    in_general && match($0, /\(thickness[ \t]+[0-9.]+/) {
      print substr($0, RSTART + 10, RLENGTH - 10) + 0
      exit
    }
    in_general && /^[ \t]*\)[ \t]*$/ { exit }
  ' "$1"
}

# Prints the sum of every layer thickness in the `(stackup ...)` block, or nothing.
stackup_thickness_mm() {
  awk '
    /\(stackup/ { in_stackup = 1 }
    in_stackup && match($0, /\(thickness[ \t]+[0-9.]+/) {
      sum += substr($0, RSTART + 10, RLENGTH - 10); seen = 1
    }
    in_stackup && /\(copper_finish/ { if (seen) printf "%g\n", sum; exit }
  ' "$1"
}

# Konnect exposes no board-thickness tool and hand-editing a .kicad_pcb is
# forbidden by the project's Global Constraints, so this asserts and never
# repairs. An unreadable or absent thickness is a FAIL: an unchecked board must
# never look green.
check_board_thickness() {
  local pcb="$1" name="$2"

  local found
  found="$(board_thickness_mm "$pcb")"

  if [ -z "$found" ]; then
    echo "FAIL thickness:$name (no (general (thickness ...)) block in $pcb)"
    STATUS=1
    return 0
  fi

  # The stackup layers feed the gerber job file, so they must add up to the same value.
  local stackup
  stackup="$(stackup_thickness_mm "$pcb")"

  if ! awk -v f="$found" -v want="$BOARD_THICKNESS_MM" \
       'BEGIN { d = f - want; exit !(d < 0.0005 && d > -0.0005) }'; then
    echo "FAIL thickness:$name (board declares ${found} mm, Global Constraints require ${BOARD_THICKNESS_MM} mm) -> $pcb"
    STATUS=1
  elif [ -z "$stackup" ] || ! awk -v s="$stackup" -v want="$BOARD_THICKNESS_MM" \
       'BEGIN { d = s - want; exit !(d < 0.0005 && d > -0.0005) }'; then
    echo "FAIL thickness:$name (stackup layers sum to ${stackup:-nothing} mm, board declares ${found} mm) -> $pcb"
    STATUS=1
  else
    echo "PASS thickness:$name (${found} mm, stackup ${stackup} mm)"
  fi
}

run_drc() {
  local pcb="$1" name="$2"
  [ -f "$pcb" ] || { echo "SKIP drc:$name (no board yet)"; return 0; }
  kicad_cli_usable drc "$name" || return 0

  "$KICAD_CLI_BIN" pcb drc \
    --exit-code-violations \
    --severity-error \
    --schematic-parity \
    --format report \
    -o "${REPORT_DIR}/${name}-drc.rpt" \
    "$pcb"
  local rc=$?

  if [ "$rc" -eq 0 ]; then
    echo "PASS drc:$name"
  else
    echo "FAIL drc:$name (exit $rc) -> ${REPORT_DIR}/${name}-drc.rpt"
    STATUS=1
  fi

  # Both run unconditionally: the gate aggregates, it does not stop at the
  # first red.
  run_parity "$pcb" "$name"
  check_board_thickness "$pcb" "$name"
}

# Skip while firmware/src is empty; verify host and AVR behavior once sources exist.
run_firmware_tests() {
  [ -f firmware/Makefile ] || { echo "SKIP firmware:verify (no Makefile yet)"; return 0; }

  # -maxdepth 1 matches the flat firmware/src/ layout in the plan's File
  # Structure table (charlieplex/animation/hal_avr/main all sit directly in
  # firmware/src). If sources are ever nested into subdirectories, raise or
  # drop -maxdepth or this gate will silently SKIP real code.
  local src_count
  src_count="$(find firmware/src -maxdepth 1 -name '*.c' -type f 2>/dev/null | wc -l | tr -d '[:space:]')"
  if [ "${src_count:-0}" -eq 0 ]; then
    echo "SKIP firmware:verify (no C sources yet)"
    return 0
  fi

  if make -C firmware verify BOARD="$FW_BOARD"; then
    echo "PASS firmware:$FW_BOARD"
  else
    echo "FAIL firmware:$FW_BOARD"
    STATUS=1
  fi
}

# Both cards must keep the NTUAS circuit; only layout and artwork may change.
run_netlist_match() {
  local sch="$1" name="$2"
  [ -f "$sch" ] || return 0
  kicad_cli_usable netlist "$name" || return 0
  local out="${REPORT_DIR}/${name}-netlist.xml"
  if "$KICAD_CLI_BIN" sch export netlist --format kicadxml -o "$out" "$sch" >/dev/null \
     && python3 scripts/check_netlist.py "$out"; then
    echo "PASS netlist:$name (matches fab/reference/card-netlist.xml)"
  else
    echo "FAIL netlist:$name (differs from the NTUAS reference circuit)"
    STATUS=1
  fi
}

# No closed copper loop in any net, and every supply loop under MAX_SUPPLY_LOOP_MM2.
# A missing KiCad Python is a FAIL, like a missing kicad-cli.
run_loops() {
  local pcb="$1" name="$2"
  [ -f "$pcb" ] || return 0
  local py="${KICAD_PYTHON:-$KICAD_PYTHON_FALLBACK}"
  if [ ! -x "$py" ]; then
    echo "FAIL loops:$name (KiCad Python not found - set KICAD_PYTHON=/path/to/python3)"
    STATUS=1
    return 0
  fi
  local report="${REPORT_DIR}/${name}-loops.txt"
  # pcbnew prints wx debug noise on stderr; keep it out of the gate output.
  if "$py" scripts/check_loops.py "$pcb" --max-supply-mm2 "$MAX_SUPPLY_LOOP_MM2" >"$report" 2>/dev/null; then
    echo "PASS loops:$name ($(tail -n 1 "$report"))"
  else
    echo "FAIL loops:$name -> $report"
    grep 'problem:' "$report"
    STATUS=1
  fi
}

for board_dir in hardware/*/; do
  name="$(basename "$board_dir")"
  [ "$name" = "lib" ] && continue
  run_erc "${board_dir}${name}.kicad_sch" "$name"
  run_drc "${board_dir}${name}.kicad_pcb" "$name"
  run_loops "${board_dir}${name}.kicad_pcb" "$name"
  run_netlist_match "${board_dir}${name}.kicad_sch" "$name"
done

# Every firmware/boards/<name> animation is built and tested against the shared core.
for fw_board in firmware/boards/*/; do
  FW_BOARD="$(basename "$fw_board")" run_firmware_tests
done
[ "$STATUS" -eq 0 ] && echo "=== ALL GREEN ===" || echo "=== FAILURES ABOVE ==="
exit "$STATUS"
