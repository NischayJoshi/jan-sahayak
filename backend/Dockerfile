FROM python:3.10-slim

WORKDIR /app

# Install git + ffmpeg (Whisper requires both)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip

# Install CPU-only PyTorch first (no GPU)
RUN pip install --no-cache-dir torch==2.5.1+cpu torchvision==0.20.1+cpu torchaudio==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu

# Install Whisper from GitHub
RUN pip install --no-cache-dir git+https://github.com/openai/whisper.git

# Install remaining requirements
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
