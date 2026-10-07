#!/usr/bin/env bash
# chime.sh — plays a short notification sound.
# Used as a Claude Code hook command. Uses only OS-builtin sounds/players,
# so there's nothing to download and nothing to keep track of.
#
# Usage: chime.sh [kind]
#   kind: "attention" (default) — Claude needs input/permission
#         "done"                — Claude finished a response
#
# Exits 0 always so it never blocks or fails a hook chain.

kind="${1:-attention}"

play() {
  # $1 = macOS sound name, $2 = linux freedesktop sound path,
  # $3 = linux alsa fallback path, $4 = Windows SystemSounds name
  if command -v afplay >/dev/null 2>&1; then
    afplay "/System/Library/Sounds/$1.aiff" >/dev/null 2>&1 &
  elif command -v paplay >/dev/null 2>&1 && [ -f "$2" ]; then
    paplay "$2" >/dev/null 2>&1 &
  elif command -v aplay >/dev/null 2>&1 && [ -f "$3" ]; then
    aplay "$3" >/dev/null 2>&1 &
  elif command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "[System.Media.SystemSounds]::$4.Play()" >/dev/null 2>&1 &
  elif command -v paplay >/dev/null 2>&1; then
    # last-resort linux path guess
    paplay /usr/share/sounds/freedesktop/stereo/complete.oga >/dev/null 2>&1 &
  fi
}

case "$kind" in
  done)
    play "Glass" \
      "/usr/share/sounds/freedesktop/stereo/complete.oga" \
      "/usr/share/sounds/alsa/Front_Center.wav" \
      "Asterisk"
    ;;
  attention|*)
    play "Ping" \
      "/usr/share/sounds/freedesktop/stereo/dialog-information.oga" \
      "/usr/share/sounds/alsa/Front_Center.wav" \
      "Exclamation"
    ;;
esac

exit 0
