#!/usr/bin/env bash
# Live smoke test — real server, real Gemini key (from .env), full HITL cycle.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "── starting server ──"
uv run python -m ops_copilot > /tmp/opencode/smoke_server.log 2>&1 &
SERVER_PID=$!
# uv spawns the python child — kill the child first, then uv, or the server leaks.
trap 'pkill -P $SERVER_PID 2>/dev/null; kill $SERVER_PID 2>/dev/null; true' EXIT

for i in $(seq 1 30); do
  sleep 1
  if curl -sf http://127.0.0.1:8000/health > /dev/null; then break; fi
  if [ "$i" = "30" ]; then echo "server did not start"; tail -20 /tmp/opencode/smoke_server.log; exit 1; fi
done

echo "── health ──"
curl -s http://127.0.0.1:8000/health | python3 -m json.tool

echo "── launching goal ──"
SID=$(curl -s -X POST http://127.0.0.1:8000/launch \
  -H 'Content-Type: application/json' \
  -d '{"goal": "Launch SSC Foundation Batch next month"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["session_id"])')
echo "session: $SID"

echo "── waiting for durable approval pause ──"
for i in $(seq 1 60); do
  PHASE=$(curl -s "http://127.0.0.1:8000/session/$SID" | python3 -c 'import sys,json; print(json.load(sys.stdin)["phase"])')
  echo "  phase: $PHASE"
  [ "$PHASE" = "awaiting_approval" ] && break
  sleep 2
done
[ "$PHASE" = "awaiting_approval" ] || { echo "never reached approval"; exit 1; }

echo "── plan ──"
curl -s "http://127.0.0.1:8000/plan/$SID" | python3 -c '
import sys, json
p = json.load(sys.stdin)
print("batch:", p["batch_name"])
print("primary faculty:", p["faculty_primary"], f"({p["faculty_primary_status"]})")
print("candidates:", [c["name"] for c in p["booking_candidates"]][:3])
print("readiness:", p["readiness_score"], "| students:", p["expected_students"])'

echo "── approving ──"
curl -s -X POST "http://127.0.0.1:8000/approve/$SID" | python3 -m json.tool

echo "── waiting for completion ──"
for i in $(seq 1 60); do
  PHASE=$(curl -s "http://127.0.0.1:8000/session/$SID" | python3 -c 'import sys,json; print(json.load(sys.stdin)["phase"])')
  echo "  phase: $PHASE"
  [ "$PHASE" = "completed" ] && break
  sleep 2
done

echo "── final state ──"
curl -s "http://127.0.0.1:8000/session/$SID" | python3 -c '
import sys, json
s = json.load(sys.stdin)
print("phase:", s["phase"])
b = s.get("booking_result") or {}
print("booking:", b.get("status"), "| faculty:", b.get("faculty_name"),
      "|", b.get("slots_booked"), "sessions |", b.get("first_class"), "→", b.get("last_class"))'

echo "── stream (replay of buffered events) ──"
curl -s --max-time 10 "http://127.0.0.1:8000/stream/$SID" | grep -c '^data: ' || true

echo "── metrics ──"
curl -s http://127.0.0.1:8000/metrics | python3 -c '
import sys, json
m = json.load(sys.stdin)
print("counters:", json.dumps(m["counters"]))
for n, s in m["nodes"].items():
    print(f"  {n}: p50={s.get("p50_ms")}ms p95={s.get("p95_ms")}ms n={s.get("count")}")'

echo "── double-approve idempotency ──"
curl -s -X POST "http://127.0.0.1:8000/approve/$SID" | python3 -m json.tool

echo "SMOKE TEST PASSED"
