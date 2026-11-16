#!/usr/bin/env bash
# Timestamp conversion shared by the PITR producers.
#
# A recovery target and a replayed transaction are compared here, so they have
# to be compared in one unit and at one precision. Whole seconds are not that
# unit: PostgreSQL timestamps carry microseconds, and rounding either side to a
# second makes a replay at .800 against a target at .900 look like a miss, and —
# with the opposite rounding — a miss look like a pass. Both producers therefore
# convert to integer microseconds and compare those.
#
# Sourced by infra/scripts/platform/pgbackrest-restore.sh and
# infra/scripts/platform/restore-drill.sh; never executed directly.

# iso_micros prints an ISO8601 timestamp as integer microseconds since the
# epoch, or nothing when the value cannot be parsed. The caller decides what an
# empty answer means; this function never guesses one.
iso_micros() {
  local micros
  micros="$(date -u -d "$1" +%s%6N 2>/dev/null || true)"
  case "$micros" in
    '' | *[!0-9]*) return 0 ;;
    *) printf '%s\n' "$micros" ;;
  esac
}

# format_epoch_micros prints integer microseconds as an ISO8601 UTC timestamp.
# Fractional seconds are kept when there are any and omitted when there are
# none, so an exact-second replay reads the same as it always has.
format_epoch_micros() {
  local micros="$1" sec frac
  case "$micros" in
    '' | *[!0-9-]*) return 1 ;;
    *) : ;;
  esac
  sec=$(( micros / 1000000 ))
  frac=$(( micros % 1000000 ))
  if (( frac < 0 )); then
    frac=$(( frac + 1000000 ))
    sec=$(( sec - 1 ))
  fi
  if (( frac == 0 )); then
    date -u -d "@$sec" +%Y-%m-%dT%H:%M:%SZ
    return 0
  fi
  printf '%s.%06dZ\n' "$(date -u -d "@$sec" +%Y-%m-%dT%H:%M:%S)" "$frac"
}
