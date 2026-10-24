# Diagnostic toolbox: Linux tools that are missing or different on the macOS host.
# Run attached to a target's network and PID namespaces (research R21).
FROM debian:12-slim
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      iproute2 procps sysstat dnsutils curl ca-certificates netcat-openbsd lsof tcpdump \
      iptables openssl postgresql-client redis-tools jq util-linux \
 && rm -rf /var/lib/apt/lists/*
CMD ["sleep", "infinity"]
