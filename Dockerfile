# Base image
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg rclone curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python files
COPY main.py notify.py requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create download directory
RUN mkdir -p /app/downloads

# Environment variable for rclone config
ENV RCLONE_CONFIG=/root/.config/rclone/rclone.conf
RUN mkdir -p /root/.config/rclone

# Set yt-dlp impersonation target globally
ENV YT_DLP_IMPERSONATE="Chrome-100"

# Run the main script
CMD ["python", "main.py"]
