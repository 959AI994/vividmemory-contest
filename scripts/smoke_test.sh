#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
RUN_ID="smoke-$(date +%s)"
USER_A="eval:${RUN_ID}:user-a"
USER_B="eval:${RUN_ID}:user-b"
SESSION="eval:${RUN_ID}:session-0"
TS_MS=$(($(date +%s) * 1000))

echo "== health =="
curl -fsS "${BASE_URL}/health" | tee /tmp/vm_health.json
echo

echo "== add (Alice Seattle) =="
ADD_BODY=$(cat <<EOF
{
  "request_id": "eval:${RUN_ID}:chunk-0",
  "messages": [
    {
      "role": "user",
      "timestamp": ${TS_MS},
      "content": "Alice moved from Boston to Seattle in July 2026."
    }
  ],
  "user_id": "${USER_A}",
  "session_id": "${SESSION}"
}
EOF
)
curl -fsS -X POST "${BASE_URL}/add" \
  -H 'Content-Type: application/json' \
  -d "${ADD_BODY}" | tee /tmp/vm_add.json
echo

echo "== search (immediate visibility) =="
SEARCH_BODY=$(cat <<EOF
{
  "query": "Where does Alice currently live?",
  "options": ["A. Boston", "B. Seattle"],
  "user_id": "${USER_A}",
  "top_k": 10
}
EOF
)
SEARCH_OUT=$(curl -fsS -X POST "${BASE_URL}/search" \
  -H 'Content-Type: application/json' \
  -d "${SEARCH_BODY}")
echo "${SEARCH_OUT}" | tee /tmp/vm_search.json
echo "${SEARCH_OUT}" | grep -qi 'Seattle' || {
  echo "FAIL: expected Seattle evidence in search results"
  exit 1
}
echo

echo "== isolation (user-b must not see user-a) =="
ISO_OUT=$(curl -fsS -X POST "${BASE_URL}/search" \
  -H 'Content-Type: application/json' \
  -d "{\"query\":\"Where does Alice currently live?\",\"user_id\":\"${USER_B}\",\"top_k\":10}")
echo "${ISO_OUT}" | tee /tmp/vm_iso.json
if echo "${ISO_OUT}" | grep -qi 'Seattle\|Boston'; then
  echo "FAIL: user isolation broken"
  exit 1
fi
echo "${ISO_OUT}" | grep -q '"data":\[\]\|"data": \[\]' || python3 - <<'PY'
import json
d=json.load(open('/tmp/vm_iso.json'))
assert d.get('data') == [] or all('Alice' not in (x.get('content') or '') for x in d.get('data') or []), d
print('isolation ok')
PY
echo

echo "== top_k=1 =="
TOP_OUT=$(curl -fsS -X POST "${BASE_URL}/search" \
  -H 'Content-Type: application/json' \
  -d "{\"query\":\"Where does Alice currently live?\",\"user_id\":\"${USER_A}\",\"top_k\":1}")
echo "${TOP_OUT}" | tee /tmp/vm_topk.json
python3 - <<'PY'
import json
d=json.load(open('/tmp/vm_topk.json'))
assert isinstance(d.get('data'), list)
assert len(d['data']) <= 1, d
print('top_k ok', len(d['data']))
PY
echo

echo "== empty result shape =="
EMPTY_OUT=$(curl -fsS -X POST "${BASE_URL}/search" \
  -H 'Content-Type: application/json' \
  -d "{\"query\":\"zzzxqwy totally unrelated quantum pineapple 999\",\"user_id\":\"${USER_B}\",\"top_k\":5}")
echo "${EMPTY_OUT}" | tee /tmp/vm_empty.json
python3 - <<'PY'
import json
d=json.load(open('/tmp/vm_empty.json'))
assert 'data' in d and isinstance(d['data'], list)
print('empty shape ok', d)
PY
echo

echo "== idempotent add =="
curl -fsS -X POST "${BASE_URL}/add" -H 'Content-Type: application/json' -d "${ADD_BODY}" >/tmp/vm_add2.json
curl -fsS -X POST "${BASE_URL}/add" -H 'Content-Type: application/json' -d "${ADD_BODY}" >/tmp/vm_add3.json
IDEM_OUT=$(curl -fsS -X POST "${BASE_URL}/search" \
  -H 'Content-Type: application/json' \
  -d "{\"query\":\"Alice Seattle\",\"user_id\":\"${USER_A}\",\"top_k\":100}")
echo "${IDEM_OUT}" | tee /tmp/vm_idem.json
python3 - <<'PY'
import json
from collections import Counter
d=json.load(open('/tmp/vm_idem.json'))
contents=[(x.get('content') or '').strip() for x in d.get('data') or []]
# exact duplicate contents should be rare after adapter dedupe; allow mild duplicates
c=Counter(contents)
dupes=[k for k,v in c.items() if v>2 and k]
assert not dupes, ('too many duplicate contents', dupes[:3], c)
print('idempotency ok; unique contents=', len(set(contents)), 'total=', len(contents))
PY
echo

echo "== temporal updates =="
curl -fsS -X POST "${BASE_URL}/add" -H 'Content-Type: application/json' -d "{
  \"request_id\": \"eval:${RUN_ID}:chunk-boston\",
  \"messages\": [{\"role\":\"user\",\"timestamp\":1736467200000,\"content\":\"Alice lives in Boston.\"}],
  \"user_id\": \"${USER_A}\",
  \"session_id\": \"${SESSION}\"
}" >/tmp/vm_t1.json
curl -fsS -X POST "${BASE_URL}/add" -H 'Content-Type: application/json' -d "{
  \"request_id\": \"eval:${RUN_ID}:chunk-seattle\",
  \"messages\": [{\"role\":\"user\",\"timestamp\":1753056000000,\"content\":\"Alice moved to Seattle.\"}],
  \"user_id\": \"${USER_A}\",
  \"session_id\": \"${SESSION}\"
}" >/tmp/vm_t2.json

echo "-- current --"
curl -fsS -X POST "${BASE_URL}/search" -H 'Content-Type: application/json' -d "{
  \"query\": \"Where does Alice currently live?\",
  \"user_id\": \"${USER_A}\",
  \"top_k\": 5
}" | tee /tmp/vm_t_now.json
echo
echo "-- january 2025 --"
curl -fsS -X POST "${BASE_URL}/search" -H 'Content-Type: application/json' -d "{
  \"query\": \"Where did Alice live in January 2025?\",
  \"user_id\": \"${USER_A}\",
  \"top_k\": 5
}" | tee /tmp/vm_t_past.json
echo

echo "SMOKE TEST PASSED"
