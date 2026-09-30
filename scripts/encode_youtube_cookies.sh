#!/usr/bin/env bash
# Encode a Netscape cookies.txt to one line of base64 for Render env YOUTUBE_COOKIES_B64.
# Does not write the secret into the repo. Do not commit the cookies file or the output.
#
# Usage:
#   ./scripts/encode_youtube_cookies.sh /path/to/cookies.txt
#
# Then on Render (service slim-music-miniapp, srv-dau87r2d0e5s73elrs2g):
#   Environment -> add YOUTUBE_COOKIES_B64 = <the printed line>
#   Leave YOUTUBE_ENABLED=1
# Saving the env var restarts the service. On startup the app writes
# /tmp/youtube_cookies.txt and passes it to yt-dlp as --cookies.
set -euo pipefail

if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "Usage: $0 /path/to/cookies.txt" >&2
  echo "Prints base64 for Render env YOUTUBE_COOKIES_B64. Do not commit it." >&2
  exit 1
fi

base64 -w 0 "$1"
echo
echo "Paste the line above into Render -> slim-music-miniapp -> Environment -> YOUTUBE_COOKIES_B64." >&2
echo "Keep YOUTUBE_ENABLED=1. Do not commit the cookies file or this value." >&2
