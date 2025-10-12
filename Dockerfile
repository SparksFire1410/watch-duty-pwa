FROM python:3.11-slim

# Install system dependencies for ffmpeg and audio processing
RUN apt-get update && apt-get install -y ffmpeg

# Copy your project files
COPY . /app
WORKDIR /app

# Install UV and dependencies
RUN pip install uv
RUN uv sync --frozen

# Run the app
CMD ["uv", "run", "python", "app.py"]