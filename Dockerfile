FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY claudebot ./claudebot

# Conversation history, memories and reminders live here; mount a volume to keep them.
ENV CLAUDEBOT_DATA_DIR=/data
VOLUME /data

CMD ["python", "-m", "claudebot"]
