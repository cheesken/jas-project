#!/bin/bash
# US-NF-01 zero-network-traffic capture. Procedure: tests/acceptance/NETWORK_CAPTURE.md
#   sudo tests/acceptance/zero_network_capture.sh
set -euo pipefail

API="${API_URL:-http://localhost:8000}"
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME="$(eval echo "~$REAL_USER")"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
IFACE="${CAPTURE_IFACE:-$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')}"
OUT="${OUT_DIR:-$REAL_HOME/jas-network-capture-$(date +%Y%m%d-%H%M%S)}"
WORK="$REAL_HOME/.jas-acceptance/network-$$"
APP_PROCS='Electron|ollama|com\.docker|vpnkit|docker|node'
NO_CAPTURE="${NO_CAPTURE:-0}"
TCPDUMP_PID=""
JOBS=()

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$OUT/session.log"; }
as_user() { if [[ $EUID -eq 0 ]]; then sudo -u "$REAL_USER" "$@"; else "$@"; fi; }

if [[ "$NO_CAPTURE" != 1 && $EUID -ne 0 ]]; then
  echo "Capturing packets needs root. Run: sudo $0"
  exit 1
fi
if [[ -z "$IFACE" ]]; then
  echo "No default network interface found. Connect to a network or set CAPTURE_IFACE (e.g. en0)."
  exit 1
fi
if ! curl -sf "$API/health" >/dev/null; then
  echo "The API is not reachable at $API. Start it with: docker compose up -d"
  exit 1
fi

mkdir -p "$OUT"
as_user mkdir -p "$WORK"

cleanup() {
  for id in "${JOBS[@]}"; do curl -s -X DELETE "$API/ingest/$id" >/dev/null || true; done
  rm -rf "$WORK"
  if [[ -n "$TCPDUMP_PID" ]] && kill -0 "$TCPDUMP_PID" 2>/dev/null; then
    kill -INT "$TCPDUMP_PID"
    wait "$TCPDUMP_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

wait_healthy() {
  for _ in $(seq 1 90); do
    curl -sf "$API/health" >/dev/null && return 0
    sleep 2
  done
  log "API did not come back after restart"
  exit 1
}

ingest() {
  local path="$1" type="$2" id status
  id="$(curl -sf -X POST "$API/ingest" -H 'Content-Type: application/json' \
    -d "{\"file_path\": \"$path\", \"file_type\": \"$type\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["job_id"])')"
  JOBS+=("$id")
  for _ in $(seq 1 120); do
    status="$(curl -sf "$API/ingest/$id" | python3 -c 'import sys,json; print(json.load(sys.stdin)["status"])')"
    [[ "$status" == COMPLETED || "$status" == FAILED ]] && break
    sleep 1
  done
  log "Ingested $(basename "$path"): $status"
}

ask() {
  curl -sf -G "$API/query" --data-urlencode "q=$1" -o /dev/null -w "%{http_code} in %{time_total}s" || echo "request failed"
}

if [[ "$NO_CAPTURE" != 1 ]]; then
  tcpdump -i "pktap,$IFACE" -w "$OUT/capture.pcapng" >"$OUT/tcpdump.log" 2>&1 &
  TCPDUMP_PID=$!
  sleep 2
  if ! kill -0 "$TCPDUMP_PID" 2>/dev/null; then
    cat "$OUT/tcpdump.log"
    exit 1
  fi
fi
log "Capture started on $IFACE (writing to $OUT)"

log "Restarting api and worker so model loading is inside the capture"
as_user docker compose -f "$REPO/docker-compose.yml" restart api worker >/dev/null
wait_healthy

as_user sh -c "printf 'Ingrid Solberg booked the Larkspur ferry for Friday at 8:15 AM. Ref $$.\n' > '$WORK/ferry_note_$$.txt'"
as_user cp "$REPO/tests/fixtures/text.png" "$WORK/receipt_$$.png"
ingest "$WORK/ferry_note_$$.txt" txt
ingest "$WORK/receipt_$$.png" image

for q in "When is the Larkspur ferry?" "What is on the receipt?" "Who booked a ferry?"; do
  log "Query \"$q\": $(ask "$q")"
done
curl -sf "$API/graph" -o /dev/null && log "GET /graph ok"
curl -sf "$API/graph/search?q=ingrid" -o /dev/null && log "GET /graph/search ok"
curl -sf "$API/status" -o /dev/null && log "GET /status ok"

if [[ -t 0 && "${NO_PROMPT:-0}" != 1 ]]; then
  log "Now use the desktop app: run a few searches, open Knowledge Graph and Settings, upload a file."
  read -r -p "Press Enter when you are done... "
fi
log "Workload finished"

cleanup
trap - EXIT
[[ "$NO_CAPTURE" == 1 ]] && { log "NO_CAPTURE=1: rehearsal only, no packets recorded"; exit 0; }

tcpdump -nn -k NP -r "$OUT/capture.pcapng" >"$OUT/packets.txt" 2>/dev/null || true
tcpdump -nn -r "$OUT/capture.pcapng" 'port 53' 2>/dev/null \
  | grep -oE '(A|AAAA|HTTPS|SVCB|CNAME)\? [^ ]+' | sort | uniq -c | sort -rn >"$OUT/dns-lookups.txt" || true
grep -iE "$APP_PROCS" "$OUT/packets.txt" >"$OUT/app-packets.txt" || true

total="$(wc -l <"$OUT/packets.txt" | tr -d ' ')"
app="$(wc -l <"$OUT/app-packets.txt" | tr -d ' ')"
{
  echo "US-NF-01 zero network traffic capture"
  echo "Interface: $IFACE"
  echo "Window: $(head -1 "$OUT/session.log" | cut -c2-9) to $(date +%H:%M:%S)"
  echo "Packets leaving or entering this Mac: $total"
  echo "Packets from this app (Electron, Ollama, Docker, Vite): $app"
  echo
  echo "Packets by process:"
  grep -oE 'proc [^,:)]+' "$OUT/packets.txt" | sort | uniq -c | sort -rn || echo "  (no process names recorded)"
  echo
  echo "DNS lookups:"
  cat "$OUT/dns-lookups.txt"
  echo
  if [[ "$app" == 0 ]]; then
    echo "RESULT: PASS. No packet from the app's processes left the machine."
  else
    echo "RESULT: FAIL. The app's processes sent traffic off the machine; see app-packets.txt."
  fi
} | tee "$OUT/report.txt"
chown -R "$REAL_USER" "$OUT"
