# Base image
FROM python:3.11-slim

# Install system dependencies for yt-dlp impersonation + ffmpeg + rclone
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    rclone \
    curl \
    libcurl4-openssl-dev \
    python3-pycurl \
    ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python files + accounts.txt
COPY main.py notify.py requirements.txt accounts.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create download directory
RUN mkdir -p /app/downloads

# Environment variable for rclone config
ENV RCLONE_CONFIG=/root/.config/rclone/rclone.conf
RUN mkdir -p /root/.config/rclone

# Run the main script
CMD ["python", "main.py"]
