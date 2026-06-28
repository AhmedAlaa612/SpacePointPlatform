FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# LibreOffice writer  — docx → PDF (payment letters)
# Cairo + Pango      — cairosvg (SVG ID card templates)
# Carlito            — open-source Calibri clone; LibreOffice maps Calibri → Carlito automatically
# Liberation fonts   — Arial / Times fallbacks for other MS font references
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf2.0-0 \
        libffi-dev \
        fonts-crosextra-carlito \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# LibreOffice writes lock/temp files to $HOME — /tmp is always writable
ENV HOME=/tmp

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
