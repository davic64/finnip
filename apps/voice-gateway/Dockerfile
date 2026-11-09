FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt
COPY voice_gateway ./voice_gateway
# Bake the Whisper model into the image (readable by the runtime user) so start-up needs no download.
ENV HF_HOME=/app/models
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
RUN useradd --uid 10001 --no-create-home vgateway && mkdir -p /app/static
USER vgateway
ENV STATIC_DIR=/app/static HF_HUB_OFFLINE=1
EXPOSE 8765
CMD ["uvicorn", "voice_gateway.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8765"]
