FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app

COPY requirements.txt requirements-browser.txt ./
RUN pip install --no-cache-dir -r requirements-browser.txt

COPY . .

ENV PYTHONUNBUFFERED=1
CMD ["sh", "-c", "python browser_startup.py && exec uvicorn browser_fetch_service:app --host 0.0.0.0 --port ${PORT:-10000}"]
