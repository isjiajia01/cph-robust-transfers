FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app

ENV PYTHONUNBUFFERED=1

CMD ["/bin/sh", "-lc", "python -m src.realtime.collector --config configs/pipeline.defaults.toml --stations configs/stations_seed.csv --base-url \"$REJSEPLANEN_BASE_URL\" --once"]
