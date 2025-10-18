FROM python:3.11-slim

# Install dependencies
RUN apt update && apt install -y ffmpeg curl && \
    pip install -U yt-dlp rclone && \
    mkdir -p /app/records /root/.config/rclone

WORKDIR /app
COPY record.sh .
RUN chmod +x record.sh

CMD ["bash", "record.sh"]
