FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py db.py security.py parsing.py grading.py llm.py auth_util.py questions_service.py import_pipeline.py ./
COPY blueprints ./blueprints
COPY static ./static

RUN useradd -u 1000 -m appuser && mkdir -p /app/data && chown -R appuser:appuser /app/data
USER appuser

EXPOSE 8000
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
