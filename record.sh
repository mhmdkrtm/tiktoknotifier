#!/bin/bash
set -e

URL="https://www.tiktok.com/@x_o_533/live"
OUTDIR="/app/records"
LOGFILE="/app/log.txt"
MAX_GB=10
GDRIVE_PATH="gdrive:tiktok_records"

echo "[INFO] Starting TikTok live monitor..." | tee -a "$LOGFILE"

while true; do
  echo "[INFO] $(date) Checking for live..." | tee -a "$LOGFILE"

  # Record if live appears (wait up to 10 mins)
  yt-dlp --wait-for-video 600 --hls-use-mpegts \
    -f "best[height<=720]" \
    -o "${OUTDIR}/%(uploader)s-%(upload_date)s-%(title)s.%(ext)s" \
    "$URL" 2>&1 | tee -a "$LOGFILE" || true

  # Upload to Google Drive
  echo "[INFO] Uploading to Google Drive..." | tee -a "$LOGFILE"
  rclone copy "$OUTDIR" "$GDRIVE_PATH" --create-empty-src-dirs --progress 2>&1 | tee -a "$LOGFILE" || true

  # Auto-clean when > 10 GB
  TOTAL=$(du -s "$OUTDIR" | awk '{print $1}')
  MAX=$((MAX_GB * 1024 * 1024))
  if [ "$TOTAL" -gt "$MAX" ]; then
    echo "[INFO] Cleaning old files..." | tee -a "$LOGFILE"
    ls -t "$OUTDIR" | tail -n +5 | while read f; do rm -f "$OUTDIR/$f"; done
  fi

  echo "[INFO] Sleeping 60s..." | tee -a "$LOGFILE"
  sleep 60
done
