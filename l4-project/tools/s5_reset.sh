#!/bin/bash
# S5 study: give the next participant a fresh Ami on port 4000.
# Orders, long-term memory and the answer cache live in memory, so a restart
# resets them (cancelled hub / started return come back). Saved chat sessions
# are moved aside so the next person can't see the last person's chat.
# Usage: tools/s5_reset.sh P2      (label = the participant about to start)
set -e
LABEL=${1:-next}
REPO="$(cd "$(dirname "$0")/../bhargava-code" && pwd)"
PORT=${PORT:-4000}

pid=$(lsof -ti tcp:$PORT -sTCP:LISTEN || true)
[ -n "$pid" ] && { kill $pid; sleep 1; echo "stopped app (pid $pid)"; }

if [ -f "$REPO/state/sessions.json" ]; then
  mv "$REPO/state/sessions.json" "$REPO/state/sessions.before-$LABEL.$(date +%H%M%S).json"
  echo "saved sessions moved aside"
fi

cd "$REPO"
PORT=$PORT nohup .venv/bin/python web.py > "../runs/s5_web_$LABEL.log" 2>&1 &
for i in $(seq 1 20); do
  curl -s -o /dev/null "http://localhost:$PORT/" && { echo "Ami ready for $LABEL: http://localhost:$PORT  (log in demo1@cofy.ai / demo123)"; exit 0; }
  sleep 1
done
echo "app did not start — see runs/s5_web_$LABEL.log"; exit 1
