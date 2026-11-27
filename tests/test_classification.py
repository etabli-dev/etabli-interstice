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
        for title in ["Email | Example | Rechnung herunterladen", "Example: Manuskript schreiben"]:
            result = infer_metadata(title, config=self.config)
            self.assertEqual(result["person"], "Alex Example")
            self.assertNotEqual(result["category"], "discussion")
            self.assertEqual(result["communication_mode"], "")
        self.assertEqual(infer_metadata("Email | Antwort senden; CC: Example", config=self.config)["person"], "")
        result = infer_metadata("Antwort senden", "History: Next action: Mit Example abstimmen", config=self.config)
        self.assertEqual(result["person"], "")
        self.assertEqual(result["communication_mode"], "")

    def test_documentation_is_not_conversation(self):
        result = infer_metadata("Email | Example | Gesprächsnotiz zum Treffen dokumentieren", "Nächster Schritt: Mit Example sprechen", config=self.config)
        self.assertEqual(result["category"], "writing")
        self.assertEqual(result["person"], "Alex Example")
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

    def test_project_people_do_not_change_work_category_or_mode(self):
        config = {"projects": [{"aliases": ["P123", "Project Atlas"], "related_people": [
            {"name": "Morgan Sample", "role": "corresponding_author", "provenance": {"file": "private/article.md", "line": 4}},
            {"name": "Taylor Reader", "role": "last_author"}]}]}
        before = copy.deepcopy(config)
        for title, expected in (("P123 | Analyse erstellen", "research"), ("Project Atlas | Manuskript schreiben", "writing"), ("P123 | Code implementieren", "software")):
            result = infer_metadata(title, config=config)
            self.assertEqual(result["person"], "Morgan Sample; Taylor Reader")
            self.assertEqual(result["category"], expected)
            self.assertEqual(result["communication_mode"], "")
            Task(title=title, **result)
        self.assertEqual(config, before)
        self.assertEqual(infer_metadata("P1234 | Analyse erstellen", config=config)["person"], "")
        self.assertEqual(infer_metadata("Analyse erstellen", "History: P123", config=config)["person"], "")

    def test_direct_recipient_then_explicit_name_then_project(self):
        config = copy.deepcopy(self.config)
        config["people"].append({"name": "Jamie Reader", "aliases": ["Reader"]})
        config["projects"] = [{"aliases": ["P123"], "related_people": [{"name": "Morgan Sample", "role": "prior_contact"}]}]
        self.assertEqual(infer_metadata("Email | P123 Example | Mit Reader abstimmen", config=config)["person"], "Jamie Reader")
        self.assertEqual(infer_metadata("P123 Example | Manuskript schreiben", config=config)["person"], "Alex Example")
        self.assertEqual(infer_metadata("P123 | Manuskript schreiben", config=config)["person"], "Morgan Sample")
        explicit = {"person": "Manually chosen"}
        self.assertEqual({**infer_metadata("P123 | Manuskript schreiben", config=config), **explicit}["person"], "Manually chosen")

    def test_ambiguous_aliases_initials_and_placeholders_are_excluded(self):
        config = {"people": [{"name": "Alex Example", "aliases": ["Example", "AE"]}, {"name": "Jamie Example", "aliases": ["Example"]}],
                  "projects": [{"aliases": ["P123"], "related_people": [{"name": "TBD"}, {"name": "[Last author]"}, {"name": "Unverified Person", "confidence": "low"}]}]}
        for title in ("Mit Example abstimmen", "AE | Manuskript schreiben", "P123 | Analyse erstellen"):
            self.assertEqual(infer_metadata(title, config=config)["person"], "")
        self.assertEqual(infer_metadata("Mit Alex Example abstimmen", config=config)["person"], "Alex Example")

    def test_project_alias_collisions_and_person_bound(self):
        config = {"projects": [{"aliases": ["Atlas"], "related_people": [{"name": "Alex Example"}]}, {"aliases": ["Atlas"], "related_people": [{"name": "Jamie Reader"}]}]}
        self.assertEqual(infer_metadata("Atlas | Analyse erstellen", config=config)["person"], "")
        config = {"projects": [{"aliases": ["P123"], "related_people": [{"name": "A" * 120 + " Person"}, {"name": "B" * 120 + " Person"}]}]}
        self.assertEqual(infer_metadata("P123 | Analyse erstellen", config=config)["person"], "")

    def test_surname_does_not_replace_different_explicit_first_name(self):
        self.assertEqual(infer_metadata("Taylor Example | Manuskript schreiben", config=self.config)["person"], "")
        self.assertEqual(infer_metadata("Alex Example | Manuskript schreiben", config=self.config)["person"], "Alex Example")
        self.assertEqual(infer_metadata("Prof. Example | Manuskript schreiben", config=self.config)["person"], "Alex Example")
