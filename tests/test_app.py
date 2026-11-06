import unittest
from unittest.mock import patch
import io
import json

from app import create_app
from services.parser import parse_whatsapp_text, anonymize_messages
from services.stylometrics import compute_stats
from services.assembler import build_system_prompt, build_character_card

SAMPLE_IOS_CHAT = """[10/06/2026, 18:32:05] Mogu: Halo apa kabar?
[10/06/2026, 18:32:45] Pais: Halo juga, baik kok!
[10/06/2026, 18:33:10] Mogu: Mau makan bareng ga nanti malam wkwk 😂
[10/06/2026, 18:33:30] Pais: Boleh banget!
[10/06/2026, 18:34:00] Mogu: oke ntar gw kabarin lagi yaaa
"""

SAMPLE_ANDROID_CHAT = """10/06/2026, 18.32 - Mogu: Halo bro
10/06/2026, 18.33 - Pais: Yo apa kabar?
10/06/2026, 18.34 - Mogu: santai aja bro wkwk
"""


class PersonaClonerServicesTestCase(unittest.TestCase):
    def test_parse_whatsapp_text_ios(self):
        df, media_counts, participants = parse_whatsapp_text(SAMPLE_IOS_CHAT)
        self.assertEqual(len(df), 5)
        self.assertEqual(len(participants), 2)
        names = [p["name"] for p in participants]
        self.assertIn("Mogu", names)
        self.assertIn("Pais", names)

    def test_parse_whatsapp_text_android(self):
        df, media_counts, participants = parse_whatsapp_text(SAMPLE_ANDROID_CHAT)
        self.assertEqual(len(df), 3)
        self.assertEqual(len(participants), 2)

    def test_anonymize_messages(self):
        df, _, _ = parse_whatsapp_text(SAMPLE_IOS_CHAT)
        df_anon, target = anonymize_messages(df, target_name="Mogu", char_name="Fossetta")
        self.assertEqual(target, "Mogu")
        self.assertIn("TARGET", df_anon["sender"].values)
        self.assertIn("LAWAN", df_anon["sender"].values)

    def test_compute_stats(self):
        df, _, _ = parse_whatsapp_text(SAMPLE_IOS_CHAT)
        df_anon, _ = anonymize_messages(df, target_name="Mogu")
        stats = compute_stats(df_anon)
        self.assertIn("n_pesan_target", stats)
        self.assertEqual(stats["n_pesan_target"], 3)
        self.assertIn("kata_per_pesan_rata2", stats)
        self.assertIn("pesan_beremoji_persen", stats)

    def test_build_system_prompt_and_card(self):
        df, _, _ = parse_whatsapp_text(SAMPLE_IOS_CHAT)
        df_anon, _ = anonymize_messages(df, target_name="Mogu")
        stats = compute_stats(df_anon)
        profile = {
            "big_five": {
                "openness": {"skor": 70, "bukti": ["makan bareng"]},
                "conscientiousness": {"skor": 60, "bukti": []},
                "extraversion": {"skor": 75, "bukti": ["wkwk"]},
                "agreeableness": {"skor": 80, "bukti": []},
                "neuroticism": {"skor": 30, "bukti": []},
            },
            "dimensi_gaya": {
                "formalitas": {"skor": 20, "bukti": []},
                "humor": {"skor": 75, "bukti": []},
            },
            "ringkasan_kepribadian": "Orang yang santai dan ramah.",
            "cara_bicara": "Sering memakai wkwk dan huruf diperpanjang.",
            "pola_respon": [{"situasi": "diajak makan", "respon_khas": "antusias"}],
            "topik_favorit": ["kuliner"],
            "hal_yang_dihindari": ["politik"],
            "fakta_personal_aman": ["suka makan"],
        }
        examples = [{"konteks": "Halo juga", "balasan": ["Mau makan bareng ga"]}]

        prompt = build_system_prompt(profile, stats, examples)
        self.assertIn("Kamu adalah {{char}}", prompt)
        self.assertIn("Orang yang santai dan ramah.", prompt)

        card = build_character_card("Fossetta", profile, stats, examples)
        self.assertEqual(card["data"]["name"], "Fossetta")
        self.assertEqual(card["spec"], "chara_card_v2")


class PersonaClonerAppRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    def test_index_route(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Persona Cloner", res.data)

    def test_health_check(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "ok")

    def test_default_models(self):
        res = self.client.get("/api/default-models")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("openrouter", data)
        self.assertIn("openai", data)
        self.assertIn("fireworks", data)

    def test_parse_chat_file_upload(self):
        data = {
            "file": (io.BytesIO(SAMPLE_IOS_CHAT.encode("utf-8")), "chat.txt"),
        }
        res = self.client.post("/api/parse-chat", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertTrue(json_data["success"])
        self.assertEqual(json_data["total_messages"], 5)
        self.assertEqual(len(json_data["participants"]), 2)

    def test_parse_chat_empty(self):
        res = self.client.post("/api/parse-chat", json={"chat_text": ""})
        self.assertEqual(res.status_code, 400)

    @patch("app.test_connection")
    def test_test_connection_route(self, mock_test):
        mock_test.return_value = (True, "Connection OK")
        res = self.client.post("/api/test-connection", json={
            "provider": "openrouter",
            "api_key": "test-key",
            "model": "deepseek/deepseek-v4.1-flash",
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])

    @patch("app.call_llm")
    def test_chat_route(self, mock_call):
        mock_call.return_value = "Halo juga! Ada apa?"
        res = self.client.post("/api/chat", json={
            "message": "Halo",
            "system_prompt": "Kamu adalah {{char}}.",
            "char_name": "Fossetta",
            "provider": "openrouter",
            "api_key": "dummy",
            "model": "dummy-model",
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["reply"], "Halo juga! Ada apa?")

    @patch("services.assembler.call_llm")
    def test_generate_persona_pipeline_streaming(self, mock_llm):
        mock_llm.return_value = json.dumps({
            "big_five": {
                "openness": {"skor": 70, "bukti": ["makan bareng"]},
                "conscientiousness": {"skor": 60, "bukti": []},
                "extraversion": {"skor": 75, "bukti": ["wkwk"]},
                "agreeableness": {"skor": 80, "bukti": []},
                "neuroticism": {"skor": 30, "bukti": []},
            },
            "dimensi_gaya": {
                "formalitas": {"skor": 20, "bukti": []},
                "humor": {"skor": 75, "bukti": []},
            },
            "ringkasan_kepribadian": "Orang santai.",
            "cara_bicara": "Sering wkwk.",
            "pola_respon": [{"situasi": "makan", "respon_khas": "gas"}],
            "topik_favorit": ["kuliner"],
            "hal_yang_dihindari": [],
            "fakta_personal_aman": [],
            "tingkat_keyakinan": "tinggi",
            "catatan_keterbatasan": "none",
        })

        res = self.client.post("/api/generate-persona", json={
            "chat_text": SAMPLE_IOS_CHAT,
            "target_name": "Mogu",
            "char_name": "Fossetta",
            "provider": "openrouter",
            "api_key": "dummy-key",
            "model": "deepseek/deepseek-v4.1-flash",
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "text/event-stream")
        data = res.get_data(as_text=True)
        self.assertIn("parsing", data)
        self.assertIn("stylometrics", data)
        self.assertIn("llm_extraction", data)
        self.assertIn("assembling", data)
        self.assertIn("Persona successfully generated!", data)


if __name__ == "__main__":
    unittest.main()
