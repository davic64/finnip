import unittest

from voice_gateway import text as T


class SplitterTest(unittest.TestCase):
    def test_emits_sentences_as_they_close(self):
        s = T.SentenceSplitter()
        self.assertEqual(s.feed("Hola, se"), [])
        self.assertEqual(s.feed("ñor. Hoy es lu"), ["Hola, señor."])
        self.assertEqual(s.feed("nes! ¿Algo más?"), ["Hoy es lunes!"])
        self.assertEqual(s.flush(), ["¿Algo más?"])
        self.assertEqual(s.flush(), [])

    def test_first_chunk_may_end_at_a_comma(self):
        s = T.SentenceSplitter()
        self.assertEqual(s.feed("Sí, claro"), [])  # comma too early
        self.assertEqual(s.feed(", hoy es domingo 8 de noviembre de 2026, señor"),
                         ["Sí, claro, hoy es domingo 8 de noviembre de 2026,"])
        self.assertEqual(s.feed(", y mañana, lunes. Fin"), ["señor, y mañana, lunes."])  # later commas don't cut
        self.assertEqual(s.flush(), ["Fin"])

    def test_cuts_long_text_at_a_space(self):
        s = T.SentenceSplitter()
        out = s.feed("palabra " * 60)
        self.assertTrue(out and all(len(p) <= T.MAX_SENTENCE for p in out))
        self.assertFalse(out[0].endswith(" "))


class HeardTest(unittest.TestCase):
    SENTENCES = ["Tienes tres pendientes.", "Primero, pagar la luz.", "Segundo, llamar a mamá."]

    def test_full_sentences_and_cut_one(self):
        heard = T.heard_text(self.SENTENCES, 1, 700)  # ~2 words of the second sentence
        self.assertEqual(heard, "Tienes tres pendientes. Primero, pagar…")

    def test_cut_before_any_word(self):
        self.assertEqual(T.heard_text(self.SENTENCES, 1, 0), "Tienes tres pendientes.")

    def test_note_only_when_interrupted(self):
        self.assertEqual(T.with_heard_note("hola", None), "hola")
        note = T.with_heard_note("¿cuál era el segundo?", "Tienes tres pendientes.")
        self.assertIn('solo alcanzó a oír: "Tienes tres pendientes."', note)
        self.assertTrue(note.endswith("¿cuál era el segundo?"))


class EchoTest(unittest.TestCase):
    SPOKEN = ["Listo, señor.", "Las luces de la sala están apagadas y la temperatura es de veintidós grados."]

    def test_own_voice_is_echo(self):
        self.assertTrue(T.is_echo("las luces de la sala estan apagadas", self.SPOKEN))
        self.assertTrue(T.is_echo("Luces de la sala están apagadas y la temperatura", self.SPOKEN))
        self.assertTrue(T.is_echo("", self.SPOKEN))

    def test_user_speech_is_not_echo(self):
        self.assertFalse(T.is_echo("no espera, mejor apaga la lámpara", self.SPOKEN))
        self.assertFalse(T.is_echo("¿qué hora es?", self.SPOKEN))


if __name__ == "__main__":
    unittest.main()
