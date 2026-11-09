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



class StatsIntentTest(unittest.TestCase):
    def test_server_questions(self):
        self.assertTrue(T.wants_stats("¿Cómo está el servidor?"))
        self.assertTrue(T.wants_stats("cuánta RAM estoy usando"))
        self.assertFalse(T.wants_stats("apaga la lámpara"))
        self.assertFalse(T.wants_stats("¿qué hora es?"))



class WakeWordTest(unittest.TestCase):
    def test_parakeet_variants_wake_up(self):
        # Real Parakeet transcripts of "Finnip, ..." (Edge TTS voices).
        self.assertEqual(T.after_wake_word("Finny, apaga la lámpara."), "apaga la lámpara.")
        self.assertEqual(T.after_wake_word("Cinip, apaga la lámpara."), "apaga la lámpara.")
        self.assertEqual(T.after_wake_word("Finit,¿qué hora es?"), "¿qué hora es?")
        self.assertEqual(T.after_wake_word("Oye FinNip, pon los monitores en rojo."), "pon los monitores en rojo.")
        self.assertEqual(T.after_wake_word("Finnip."), "")
        # The user's own voice, from the gateway log.
        self.assertEqual(T.after_wake_word("Philip."), "")
        self.assertEqual(T.after_wake_word("Finip apar la lámpara."), "apar la lámpara.")
        self.assertEqual(T.after_wake_word("Oye, Finip."), "")

    def test_other_speech_stays_asleep(self):
        for text in ("apaga la lámpara", "fin de semana", "oye, ¿qué hora es?", "", "la TV dice Finnip"):
            self.assertIsNone(T.after_wake_word(text), text)


class RemindersTest(unittest.TestCase):
    def test_intent(self):
        self.assertTrue(T.wants_reminders("¿Qué recordatorios tengo?"))
        self.assertTrue(T.wants_reminders("tengo alguna alarma"))
        self.assertFalse(T.wants_reminders("ponme un recordatorio a las 8"))
        self.assertFalse(T.wants_reminders("cancela la alarma"))
        self.assertFalse(T.wants_reminders("enciende la lámpara"))
        self.assertTrue(T.wants_reminders("qué eventos tengo en mi calendario"))
        self.assertFalse(T.wants_reminders("agenda un evento mañana"))

    def test_calendar_items_in_mexico_time(self):
        from datetime import datetime
        now = datetime.fromisoformat("2026-11-09T12:00:00-06:00")
        events = [
            {"summary": "Pagar", "start": {"dateTime": "2026-11-10T05:30:00+00:00"}},
            {"summary": "Junta", "start": {"dateTime": "2026-11-10T08:00:00-06:00"}},
            {"summary": "Viaje", "start": {"date": "2026-11-20"}},
            {"start": {"date": "2026-11-09"}},
        ]
        self.assertEqual(T.calendar_items(events, now), [
            {"name": "Pagar", "when": "Hoy · 23:30"},
            {"name": "Junta", "when": "Mañana · 08:00"},
            {"name": "Viaje", "when": "vie 20 nov · todo el día"},
            {"name": "Sin título", "when": "Hoy · todo el día"},
        ])
if __name__ == "__main__":
    unittest.main()
