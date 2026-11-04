FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY claudebot ./claudebot
COPY docker-entrypoint.sh /usr/local/bin/

# Conversation history, memories, reminders and your Google token live here; mount a volume.
# The entrypoint fixes the volume's owner, then runs ClaudeBot as the unprivileged claudebot user.
RUN useradd --create-home claudebot && mkdir /data && chown claudebot:claudebot /data
ENV CLAUDEBOT_DATA_DIR=/data PYTHONUNBUFFERED=1
EXPOSE 8765
VOLUME /data

# Healthy while the bot's event loop keeps touching /data/alive (once a minute).
HEALTHCHECK --interval=2m --timeout=10s --start-period=2m CMD ["python", "-m", "claudebot", "health"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "claudebot"]
