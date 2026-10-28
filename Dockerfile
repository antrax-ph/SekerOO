FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app

# System deps for Playwright Chromium are already in this image.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install chromium

COPY . .

ENV PYTHONUNBUFFERED=1 \
    OUT_ROOT=/data/results
RUN mkdir -p /data/results

EXPOSE 8000
CMD ["uvicorn", "ml_checker.api:app", "--host", "0.0.0.0", "--port", "8000"]