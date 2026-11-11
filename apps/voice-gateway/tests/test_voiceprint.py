import os
import tempfile
import unittest

import numpy as np

MODEL = os.environ.get("VOICE_MODEL", "")


@unittest.skipUnless(os.path.exists(MODEL), "speaker model only in the image")
class VoiceprintTest(unittest.TestCase):
    def test_enroll_save_and_score(self):
        from voice_gateway.voiceprint import Voiceprint

        rng = np.random.default_rng(1)
        voice = (np.sin(np.arange(16000 * 3) * 0.05) * 8000 + rng.normal(0, 500, 16000 * 3)).astype(np.int16)
        other = rng.normal(0, 8000, 16000 * 3).astype(np.int16)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "voiceprint.json")
            vp = Voiceprint(MODEL, path)
            self.assertFalse(vp.enrolled)
            self.assertIsNone(vp._embed(voice[:8000].tobytes()))  # half a second: too short to tell
            vp.save([vp._embed(voice.tobytes())])
            again = Voiceprint(MODEL, path)  # loaded from disk
            self.assertTrue(again.enrolled)
            same = again.score(again._embed(voice.tobytes()))
            self.assertGreater(same, 0.99)
            self.assertLess(again.score(again._embed(other.tobytes())), same)
