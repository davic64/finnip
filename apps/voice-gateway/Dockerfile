FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt
COPY voice_gateway ./voice_gateway
# Bake the STT model into the image (readable by the runtime user) so start-up needs no download.
ENV HF_HOME=/app/models
RUN python -c "import onnx_asr; onnx_asr.load_model('nemo-parakeet-tdt-0.6b-v3', quantization='int8')"
RUN useradd --uid 10001 --no-create-home vgateway && mkdir -p /app/static
USER vgateway
ENV STATIC_DIR=/app/static HF_HUB_OFFLINE=1
EXPOSE 8765
CMD ["uvicorn", "voice_gateway.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8765"]
