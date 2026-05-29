FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway inyecta la variable PORT en tiempo de ejecucion
ENV PORT=8000
EXPOSE 8000

# Usamos shell form para poder expandir $PORT que asigna Railway
CMD uvicorn agent.main:app --host 0.0.0.0 --port ${PORT:-8000}
