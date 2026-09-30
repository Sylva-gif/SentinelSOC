FROM python:3.12.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv

WORKDIR /srv
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip==25.0.1 && pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY tests ./tests
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
RUN mkdir -p /srv/data/evidence && chown -R app:app /srv
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]