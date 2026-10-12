FROM python:3.12-alpine
# ping for the "availability" driver, ssh + sshpass for the SSH driver, iperf3 for speed tests; everything else is the Python standard library
RUN apk add --no-cache iputils tzdata openssh-client sshpass iperf3
# Speedtest CLI by Ookla for the scheduled internet speed test (optional: without it Rack Live measures via Cloudflare)
RUN case "$(uname -m)" in x86_64) a=x86_64;; aarch64) a=aarch64;; armv7l) a=armhf;; *) a="";; esac; \
    [ -z "$a" ] || wget -qO- "https://install.speedtest.net/app/cli/ookla-speedtest-1.2.0-linux-$a.tgz" | tar xz -C /usr/local/bin speedtest || true
WORKDIR /app
COPY rackd ./rackd
COPY web/index.html web/styles.css web/app.js web/agent.py web/icon.svg web/icon-512.png web/icon-192.png web/apple-touch-icon.png web/manifest.json ./web/
COPY web/vendor ./web/vendor
ENV RL_DATA=/data RL_WEB=/app/web RL_PORT=8080 PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s CMD wget -qO- http://127.0.0.1:${RL_PORT}/api/state >/dev/null || exit 1
CMD ["python", "-m", "rackd"]
