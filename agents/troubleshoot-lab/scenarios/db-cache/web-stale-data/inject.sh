#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
nginx_location items-cache <<'EOF'
location = /api/items {
    rewrite ^ /items break;
    proxy_pass http://$api_host;
    proxy_cache lab;
    proxy_cache_valid 200 10m;
    proxy_ignore_headers Cache-Control Expires;
    add_header X-Cache-Status $upstream_cache_status always;
}
EOF
# Reload is graceful: old workers answer for a moment. Wait until the cached location is live
# and holds an entry, so the next POST is really hidden behind the cache.
cached() { curl -s -o /dev/null -D - --max-time 3 localhost:8080/api/items | grep -qi '^x-cache-status: hit'; }
wait_until 30 cached
name="stale-$(rand_token)"
curl -s -o /dev/null -X POST -H 'Content-Type: application/json' -d "{\"name\":\"$name\"}" localhost:8080/api/items
stale() { ! curl -s localhost:8080/api/items | grep -q "$name"; }
wait_until 10 stale
