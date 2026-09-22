#!/bin/sh
set -eu

# The worker and proxy deliberately share a container: the proxy is the
# existing frontend boundary and only it is exposed to the VM/browser.
wrangler dev --config /app/.output/server/wrangler.json \
  --ip "$FRONTEND_HOST" \
  --port "$FRONTEND_PORT" \
  --local &
worker_pid=$!

stop() {
  kill -TERM "$worker_pid" 2>/dev/null || true
  wait "$worker_pid" 2>/dev/null || true
  exit 0
}
trap stop INT TERM

node /app/vm-proxy.mjs &
proxy_pid=$!

while kill -0 "$worker_pid" 2>/dev/null && kill -0 "$proxy_pid" 2>/dev/null; do
  sleep 2
done

kill -TERM "$worker_pid" "$proxy_pid" 2>/dev/null || true
wait "$worker_pid" "$proxy_pid" 2>/dev/null || true
