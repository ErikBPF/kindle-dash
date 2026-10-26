# kindle-dash — renders a grayscale dashboard PNG for a jailbroken Kindle.
# Pulls time, optional Home Assistant data (weather/forecast/sun/calendar) and
# optional Claude usage, and serves it at GET /dash.png for the device to fetch.
# Digest-pinned: this job publishes signed images, and a mutable tag can be
# repointed. Renovate bumps the digest (python:3.14-slim).
FROM python:3.14-slim@sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8

# tzdata: local time/date on the dashboard. fonts-dejavu-core: TTFs Pillow draws
# with (slim ships none). Both are tiny.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

# State (Claude OAuth tokens + usage cache) lives here; mount a volume to persist.
RUN mkdir -p /data
ENV DASH_STATE_DIR=/data

EXPOSE 8080
CMD ["python", "app.py"]
