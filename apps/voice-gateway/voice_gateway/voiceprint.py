"""Whose voice is it: phrases that are not the user's (Alexa answering, the TV, a visitor) are ignored.

The voiceprint is the mean speaker embedding (3D-Speaker CAM++ through sherpa-onnx) of the phrases the
user reads aloud after "Finnip, aprende mi voz"; every phrase is compared with it by cosine similarity."""
import asyncio
import json
import os

import numpy as np

MIN_SECONDS = 1.0  # shorter phrases ("sí", "para") pass unchecked: too little voice to tell
# Read aloud one at a time while enrolling. No "Finnip" and no orders: another device listening
# (the Mac) must not act on them.
ENROLL_PHRASES = [
    "Hoy hace un buen día para trabajar en mis proyectos.",
    "Me gusta escuchar rock de los ochenta mientras imprimo piezas.",
    "La impresora tarda casi tres horas en terminar una pieza grande.",
    "Mañana quiero diseñar un soporte nuevo para el escritorio.",
    "Cuando llego a casa, lo primero que hago es poner música.",
]


class Voiceprint:
    def __init__(self, model, path, threshold=0.4):
        import sherpa_onnx  # only in the image; tests use a fake

        self.extractor = sherpa_onnx.SpeakerEmbeddingExtractor(
            sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=model, num_threads=1))
        self.path, self.threshold = path, threshold
        try:
            with open(path) as f:
                self.print = np.array(json.load(f), dtype=np.float32)
        except (OSError, ValueError):
            self.print = None  # not enrolled yet: every phrase passes

    @property
    def enrolled(self):
        return self.print is not None

    def _embed(self, pcm16):
        audio = np.frombuffer(pcm16[: len(pcm16) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768
        if len(audio) < 16000 * MIN_SECONDS:
            return None
        stream = self.extractor.create_stream()
        stream.accept_waveform(sample_rate=16000, waveform=audio)
        stream.input_finished()
        embedding = np.array(self.extractor.compute(stream), dtype=np.float32)
        return embedding / (np.linalg.norm(embedding) or 1)

    async def embed(self, pcm16):
        """Unit-length embedding of a PCM16 16 kHz phrase, or None when it is too short."""
        return await asyncio.to_thread(self._embed, pcm16)

    def score(self, embedding):
        return float(np.dot(self.print, embedding))

    def save(self, embeddings):
        mean = np.mean(embeddings, axis=0)
        mean = mean / (np.linalg.norm(mean) or 1)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(mean.tolist(), f)
        os.replace(tmp, self.path)  # atomic: a crash leaves the previous voiceprint
        self.print = mean.astype(np.float32)
