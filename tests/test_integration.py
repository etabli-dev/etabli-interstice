# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.store import Store


class IntegrationTests(unittest.TestCase):
    def test_compatibility_scope_classification_and_retry(self):
        for mode in ('shadow', 'production'):
            with tempfile.TemporaryDirectory() as directory:
                app = create_app({'data': directory, 'mode': mode, 'public_url': 'http://testserver',
                    'clients': [{'id': 'writer', 'role': 'admin', 'token': 'a' * 40},
                                {'id': 'reader', 'role': 'read', 'token': 'b' * 40}]})
                with TestClient(app) as client:
                    path = '/api/v1/compat/flowsavvy/call'
                    headers = {'Authorization': 'Bearer ' + 'a' * 40, 'Idempotency-Key': 'create-one'}
                    body = {'tool': 'create_task', 'arguments': {'title': 'Rechnung bezahlen', 'durationMinutes': 30}}
                    self.assertEqual(client.get('/api/v1/compat/flowsavvy/tools').status_code, 401)
                    self.assertEqual(client.post(path, json=body, headers={**headers, 'Authorization': 'Bearer ' + 'b' * 40}).status_code, 403)
                    response = client.post(path, json=body, headers=headers)
                    if mode == 'shadow':
                        self.assertEqual(response.status_code, 403)
                        self.assertEqual(app.state.store.tasks(), [])
                        continue
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()['category'], 'administration')
                    self.assertTrue(response.json()['url'].startswith('http://testserver/?task=etabli%3A'))
                    self.assertEqual(client.post(path, json=body, headers=headers).json(), response.json())
                    self.assertEqual(len(app.state.store.tasks()), 1)
                    native = client.post('/api/v1/tasks', json={'title': 'Rechnung bezahlen', 'category': 'other', 'person': ''},
                        headers={**headers, 'Idempotency-Key': 'native'})
                    self.assertEqual(native.status_code, 200, native.text)
                    self.assertEqual(native.json()['category'], 'other')
                    self.assertEqual(native.json()['person'], '')

    def test_concurrent_plans_share_one_calculation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory + '/tasks.sqlite')
            now = datetime(2026, 11, 27, 8, tzinfo=timezone.utc)
            with patch('app.store.run_job', return_value={'blocks': [], 'shortages': []}) as run:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    results = list(pool.map(lambda _: store.plan(now), range(4)))
                self.assertEqual(run.call_count, 1)
                self.assertTrue(all(r['inputs_revision'] == results[0]['inputs_revision'] for r in results))

    def test_native_events_are_part_of_planner_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app({'data': directory, 'public_url': 'http://testserver',
                'clients': [{'id': 'writer', 'role': 'admin', 'token': 'a' * 40}]})
            store = app.state.store
            with store.db() as db:
                before = store._snapshot(db)[2]
            event = {'id': 'meeting', 'title': 'Meeting', 'start': '2026-11-27T09:00:00+00:00',
                     'end': '2026-11-27T10:00:00+00:00', 'busy': True}
            with patch.object(store.compat, 'events', return_value=[event]):
                with store.db() as db:
                    self.assertNotEqual(store._snapshot(db)[2], before)
                with patch('app.store.run_job', return_value={'blocks': [], 'shortages': []}) as run:
                    store.plan()
                    self.assertIn(event, run.call_args.args[1]['events'])
