FROM python:3.12-alpine
# ping for the "availability" driver, ssh + sshpass for the SSH driver, iperf3 for speed tests; everything else is the Python standard library
RUN apk add --no-cache iputils tzdata openssh-client sshpass iperf3
# tools for Frank in agent mode, in his own working folder (data/frank/work): git to clone a project, curl, Node.js for projects of his own
RUN apk add --no-cache git curl nodejs npm
# Frank's mini browser (rackd/frankbrowser.py): Chromium for pages and screenshots, fonts so Cyrillic is not drawn as squares
RUN apk add --no-cache chromium font-noto
# chromedriver: Frank can also log into web interfaces (rackd/webdrive.py) — fill the form, press, screenshot
RUN apk add --no-cache chromium-chromedriver
# Speedtest CLI by Ookla for the scheduled internet speed test (optional: without it Rack Live measures via Cloudflare)
RUN case "$(uname -m)" in x86_64) a=x86_64;; aarch64) a=aarch64;; armv7l) a=armhf;; *) a="";; esac; \
    [ -z "$a" ] || wget -T 20 -qO- "https://install.speedtest.net/app/cli/ookla-speedtest-1.2.0-linux-$a.tgz" | tar xz -C /usr/local/bin speedtest || true
# Xray core for «Проверка VPN» (a real tunnel from a pasted link), pinned by version and SHA-256. Optional: without it the check says the tunnel was not tested.
RUN case "$(uname -m)" in x86_64) n=64; s=0eec3ed4163c273d8c8bf821f7d219e257921cf584aa3fb970715e458e631978;; aarch64) n=arm64-v8a; s=d1304946c486d98e6b886e9b931eaaaebb23835b30e217638037b7f2721d4e9c;; armv7l) n=arm32-v7a; s=89978508fa2ebb4a1e661f2c6ed51d241c4091b3cd17f4c65fdf20baae7dedac;; *) n="";; esac; \
    if [ -n "$n" ]; then cd /tmp && wget -T 30 -qO x.zip "https://github.com/XTLS/Xray-core/releases/download/v26.10.21/Xray-linux-$n.zip" && echo "$s  x.zip" | sha256sum -c - >/dev/null && unzip -qo x.zip xray -d /usr/local/bin && chmod 755 /usr/local/bin/xray; rm -f x.zip; fi; true
WORKDIR /app
COPY rackd ./rackd
COPY web/index.html web/theme-defaults.json web/styles.css web/app.js web/agent.py web/icon.svg web/icon-graphite.svg web/icon-net.svg web/icon-512.png web/icon-192.png web/apple-touch-icon.png web/manifest.json web/frank.html web/frank-manifest.json web/frank-icon.svg web/frank-icon-graphite.svg web/frank-icon-net.svg web/frank-icon-512.png web/frank-icon-192.png web/frank-apple-touch-icon.png web/speed.html web/speed-manifest.json web/speed-icon.svg web/speed-icon-graphite.svg web/speed-icon-net.svg web/speed-icon-512.png web/speed-icon-192.png web/speed-apple-touch-icon.png web/scan.html web/cards.html web/cards-manifest.json web/cards-icon.svg web/cards-icon-512.png web/cards-icon-192.png web/cards-apple-touch-icon.png web/terminal.html web/terminal-manifest.json web/terminal-icon.svg web/terminal-icon-512.png web/terminal-icon-192.png web/terminal-apple-touch-icon.png web/modeler.html web/modeler-manifest.json web/modeler-manifest-test.json web/modeler-icon.svg web/modeler-icon-512.png web/modeler-icon-192.png web/modeler-apple-touch-icon.png ./web/
COPY web/look-test ./web/look-test/
COPY web/vendor ./web/vendor
COPY web/flags ./web/flags/
COPY web/plan.html web/plan-manifest.json web/plan-icon.svg web/plan-icon-192.png web/plan-icon-512.png web/plan-apple-touch-icon.png ./web/
ENV RL_DATA=/data RL_WEB=/app/web RL_PORT=8080 PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s CMD wget -qO- http://127.0.0.1:${RL_PORT}/api/state >/dev/null || exit 1
CMD ["python", "-m", "rackd"]
