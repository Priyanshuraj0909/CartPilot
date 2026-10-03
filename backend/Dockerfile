FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock.txt && useradd --create-home appuser
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts ./scripts
USER appuser
EXPOSE 8000
CMD ["sh", "scripts/start.sh"]
