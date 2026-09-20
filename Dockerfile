FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 IMOVEL_DB_PATH=/app/data/radar.sqlite3
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home radar
COPY app ./app
COPY web ./web
RUN mkdir -p /app/data && chown -R radar:radar /app
USER radar
EXPOSE 8766
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8766", "--no-access-log"]
