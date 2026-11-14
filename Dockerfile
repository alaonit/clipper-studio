FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPEN_BROWSER=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg unzip \
    && curl -fsSL https://github.com/denoland/deno/releases/download/v2.3.3/deno-x86_64-unknown-linux-gnu.zip -o /tmp/deno.zip \
    && unzip -q /tmp/deno.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/deno \
    && rm /tmp/deno.zip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY clipper.py web_app.py ./

EXPOSE 8765
CMD ["python", "web_app.py"]
