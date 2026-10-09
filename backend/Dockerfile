FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    WEB_CONCURRENCY=3
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER 1000:1000
EXPOSE 8000
CMD ["sh", "-c", "exec gunicorn --bind \"0.0.0.0:${PORT}\" --workers \"${WEB_CONCURRENCY}\" --access-logfile - --error-logfile - wsgi:app"]
