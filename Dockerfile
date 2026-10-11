FROM python:3.12-alpine
# ping for the "availability" driver; everything else is the Python standard library
RUN apk add --no-cache iputils tzdata
WORKDIR /app
COPY rackd ./rackd
COPY web/index.html web/styles.css web/app.js web/agent.py web/icon.svg web/icon-512.png web/manifest.json ./web/
COPY web/vendor ./web/vendor
ENV RL_DATA=/data RL_WEB=/app/web RL_PORT=8080 PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s CMD wget -qO- http://127.0.0.1:8080/api/state >/dev/null || exit 1
CMD ["python", "-m", "rackd"]
