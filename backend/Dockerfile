FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r requirements.txt
COPY backend/ .
COPY ml/ /app/ml
COPY routing/ /app/routing
COPY models/ /app/models
COPY data/ /app/data
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.demo_seed && gunicorn --bind 0.0.0.0:8000 --workers 2 --access-logfile - --error-logfile - app.wsgi:app"]
