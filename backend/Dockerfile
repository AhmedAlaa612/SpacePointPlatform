FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# LibreOffice writer  — docx → PDF (payment letters)
# Cairo + Pango      — cairosvg (SVG ID card templates)
# Carlito            — open-source Calibri clone; LibreOffice maps Calibri → Carlito automatically
# Liberation fonts   — Arial / Times fallbacks for other MS font references
# ffmpeg             — LMS video pipeline (LM1-6): ffprobe + HLS/AES-128 encode.
#                       Shared API+worker image, so the API image grows too — acceptable, no
#                       separate image this week (LMS_EXECUTION_PLAN.md §7 risk 6).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-xlib-2.0-0 \
        libffi-dev \
        fonts-crosextra-carlito \
        fonts-liberation \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# LibreOffice writes lock/temp files to $HOME — /tmp is always writable
ENV HOME=/tmp

EXPOSE 8000

# Apply any pending Alembic migrations (tracked in alembic_version — a no-op
# when already at head), THEN start the app. A failing migration blocks
# startup by design, rather than serving against a half-migrated schema.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
