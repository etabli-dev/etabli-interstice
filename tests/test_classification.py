# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
import copy
import unittest

from app.classification import CATEGORIES, MODES, infer_metadata
from app.domain import Task


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.config = {"people": [{"name": "Alex Example", "aliases": ["Example"], "roles": ["Vorgesetzter"]}], "topics": [{"tag": "Project Atlas", "aliases": ["Atlas"]}]}

    def test_direct_recipient_and_channel(self):
        result = infer_metadata("Email | Atlas P027 | Freigabe mit Example abstimmen", config=self.config)
        self.assertEqual(result, {"category": "discussion", "person": "Alex Example", "communication_mode": "email", "tags": ["P027", "Project Atlas"]})

    def test_role_requires_explicit_partner(self):
        self.assertEqual(infer_metadata("Mit Vorgesetzter abstimmen", config=self.config)["person"], "Alex Example")
        self.assertEqual(infer_metadata("Freigabe abwarten; Vorgesetzter informiert", config=self.config)["person"], "")

    def test_names_and_history_are_not_recipients(self):
        for title in ["Email | Example | Rechnung herunterladen", "Example: Manuskript schreiben", "Email | Antwort senden; CC: Example"]:
            self.assertEqual(infer_metadata(title, config=self.config)["person"], "")
        result = infer_metadata("Antwort senden", "History: Next action: Mit Example abstimmen", config=self.config)
        self.assertEqual(result["person"], "")
        self.assertEqual(result["communication_mode"], "")

    def test_documentation_is_not_conversation(self):
        result = infer_metadata("Email | Example | Gesprächsnotiz zum Treffen dokumentieren", "Nächster Schritt: Mit Example sprechen", config=self.config)
        self.assertEqual(result["category"], "writing")
        self.assertEqual(result["person"], "")
        self.assertEqual(result["communication_mode"], "")

    def test_origin_and_action_precedence(self):
        examples = {"Email | Rechnung herunterladen": "administration", "Email | API implementieren": "software", "Chat | Daten auswerten": "research", "Orga | Passwort ändern": "security", "Orga | Kurs lernen": "learning", "Orga | Gerät reparieren": "practical", "Manuscript | Atlas": "writing", "Unbekannt": "other"}
        for title, category in examples.items():
            self.assertEqual(infer_metadata(title)["category"], category)
        self.assertEqual(len(CATEGORIES), 9)

    def test_note_next_action_only_when_title_unknown(self):
        self.assertEqual(infer_metadata("Atlas", "Nächster Schritt: Mit Example abstimmen", config=self.config)["person"], "Alex Example")
        self.assertEqual(infer_metadata("Analyse erstellen", "Nächster Schritt: Mit Example abstimmen", config=self.config)["category"], "research")

    def test_ambiguous_channel_stays_empty(self):
        self.assertEqual(infer_metadata("Mit Example abstimmen per WhatsApp oder persönlich", config=self.config)["communication_mode"], "")
        self.assertEqual(infer_metadata("Mit Example abstimmen per Video call", config=self.config)["communication_mode"], "video")

    def test_resolved_action_and_malformed_optional_config(self):
        self.assertEqual(infer_metadata("Freigabe bereits erteilt")["category"], "other")
        self.assertEqual(infer_metadata("Mit Example abstimmen", config={"people": None, "topics": None})["person"], "")

    def test_precedence_ready_and_no_mutation(self):
        before = copy.deepcopy(self.config)
        suggestion = infer_metadata("Email | Mit Example abstimmen", config=self.config)
        explicit = {"category": "other", "person": "", "communication_mode": "", "tags": []}
        merged = {**suggestion, **explicit}
        self.assertEqual(merged, explicit)
        self.assertEqual(self.config, before)
        Task(title="Example", **suggestion)

    def test_bounds_literals_and_repeatability(self):
        config = {"people": [{"name": "x" * 201, "aliases": ["Example"]}], "topics": [{"tag": "x" * 81, "aliases": ["Atlas"]}] + [{"tag": str(i), "aliases": ["Atlas"]} for i in range(30)]}
        result = infer_metadata("Atlas P027 | Mit Example abstimmen", config=config)
        self.assertEqual(result["person"], "")
        self.assertEqual(len(result["tags"]), 20)
        self.assertIn(result["communication_mode"], MODES)
        Task(title="Example", **result)
        self.assertEqual(result, infer_metadata("Atlas P027 | Mit Example abstimmen", config=config))
        self.assertEqual(infer_metadata("Mit Example abstimmen", config={"people": [{"name": "Other", "aliases": [".*"]}]})["person"], "")
