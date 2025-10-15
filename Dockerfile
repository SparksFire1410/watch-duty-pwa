FROM python:3.11
RUN apt-get update && apt-get install -y ffmpeg
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ENV HF_HOME=/app/.cache
RUN mkdir -p /app/.cache && chmod -R 777 /app/.cache
COPY . .
EXPOSE 8080 # Changed from 5000 to 8080 (the common default for $PORT)
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "--workers", "2", "--threads", "4", "app:app"] # Changed to use Gunicorn