#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
nginx_location profile-cache <<'EOF'
location = /api/profile {
    rewrite ^ /profile break;
    proxy_pass http://$api_host;
    proxy_cache lab;
    proxy_cache_key "$scheme$host$uri";
    proxy_cache_valid 200 10m;
    proxy_ignore_headers Cache-Control Set-Cookie;
    proxy_hide_header Cache-Control;
    add_header Cache-Control "public, max-age=600" always;
    add_header X-Cache-Status $upstream_cache_status always;
}
EOF
# Reload is graceful: old workers answer for a moment. Only alice's requests until the cached
# location is live, so the first cached response is hers.
live() { curl -s -o /dev/null -D - --max-time 3 --cookie user=alice localhost:8080/api/profile | grep -qiE '^x-cache-status: (miss|hit)'; }
wait_until 30 live
leaked() { curl -s --cookie user=bob localhost:8080/api/profile | grep -q alice; }
wait_until 10 leaked
