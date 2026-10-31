FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY claudebot ./claudebot

# Conversation history, memories, reminders and your Google token live here; mount a volume.
RUN useradd --create-home claudebot && mkdir /data && chown claudebot /data
ENV CLAUDEBOT_DATA_DIR=/data PYTHONUNBUFFERED=1
VOLUME /data
USER claudebot

CMD ["python", "-m", "claudebot"]
