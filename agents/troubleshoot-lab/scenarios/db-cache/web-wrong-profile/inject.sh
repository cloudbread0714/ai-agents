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
wait_http localhost:8080/api/profile 200 30
curl -s -o /dev/null --cookie user=alice localhost:8080/api/profile
leaked() { curl -s --cookie user=bob localhost:8080/api/profile | grep -q alice; }
wait_until 10 leaked
