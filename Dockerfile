FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Mở port 8080 để Cloud Run có thể check health
EXPOSE 8080

CMD ["python", "run_bot.py"]
