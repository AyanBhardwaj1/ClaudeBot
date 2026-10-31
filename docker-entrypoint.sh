#!/bin/sh
# Volumes on Fly.io, Railway and older ClaudeBot images are owned by root. Fix that, then run
# ClaudeBot as an unprivileged user.
set -e
DATA="${CLAUDEBOT_DATA_DIR:-/data}"
if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DATA"
  chown -R claudebot:claudebot "$DATA"
  exec setpriv --reuid=claudebot --regid=claudebot --init-groups "$@"
fi
exec "$@"
