# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
import concurrent.futures
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from app.domain import Task, schedule
from app.store import Store, Conflict
from app.work import run_job, WorkLimit, _slots
from app.manage import checked_backup

NOW = datetime(2026, 11, 23, 7, 59, tzinfo=timezone.utc)


class InvariantTests(unittest.TestCase):
    def test_seeded_schedules_conserve_effort_and_respect_busy_time(self):
        for seed in range(80):
            rng=random.Random(seed)
            tasks=[dict(Task(title=str(i),minutes=rng.randrange(1,200),min_block=rng.randrange(1,40),
                buffer=rng.randrange(0,10),split=rng.choice([True,False]),priority=rng.randrange(4),
                due=NOW+timedelta(hours=30)).model_dump(mode='json'),id=str(i),progress=0) for i in range(12)]
            events=[{'start':'2026-11-23T10:00:00+00:00','end':'2026-11-23T11:00:00+00:00'}]
            plan=schedule(tasks,events,now=NOW)
            from app.validation import validate_plan
            validate_plan(tasks,events,plan)
            for task in tasks:
                blocks=[b for b in plan['blocks'] if b['task_id']==task['id']]
                missing=sum(s['minutes'] for s in plan['shortages'] if s['task_id']==task['id'])
                self.assertEqual(sum(b['minutes'] for b in blocks)+missing,task['minutes'])
                for block in blocks:
                    self.assertLessEqual(datetime.fromisoformat(block['end']),datetime.fromisoformat(task['due']))
                    self.assertTrue(block['end']<=events[0]['start'] or block['start']>=events[0]['end'])
            for a,b in zip(plan['blocks'],plan['blocks'][1:]):
                self.assertLessEqual(a['end'],b['start'])

    def test_validator_rejects_corrupt_solver_output(self):
        from app.validation import validate_plan
        tasks=[dict(Task(title='test').model_dump(mode='json'),id='one',progress=0)]
        plan=schedule(tasks,[],now=NOW)
        plan['blocks'].append(dict(plan['blocks'][0]))
        with self.assertRaises(ValueError):validate_plan(tasks,[],plan)

    def test_subprocess_timeout_and_capacity_recover(self):
        with self.assertRaises(WorkLimit):
            run_job('schedule',{},timeout=0.000001)
        _slots.acquire()
        try:
            with self.assertRaises(WorkLimit):
                run_job('schedule',{})
        finally:
            _slots.release()
        result=run_job('schedule',{'tasks':[],'events':[],'now':NOW.isoformat()})
        self.assertEqual(result['blocks'],[])

    def test_invalid_worker_input_is_sanitized(self):
        with self.assertRaisesRegex(ValueError,'Invalid calendar'):
            run_job('calendar',{'data':'private invalid text','method':'GET','source':{'id':'test'}})


class DurabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'data.sqlite'
        self.store=Store(self.path)
        self.task=self.store.mutate('owner','create','create',Task(title='Work').model_dump(mode='json'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_connections_retry_one_receipt(self):
        other=Store(self.path)
        def write(i):
            return (self.store if i%2 else other).mutate('device','same','progress',
                {'session_id':'focus','minutes':25},ident=self.task['id'])
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            rows=list(pool.map(write,range(20)))
        self.assertTrue(all(t['progress']==25 for t in rows))
        self.assertEqual(self.store.tasks()[0]['progress'],25)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0],1)

    def test_plan_persists_and_invalidates_on_mutation(self):
        first=self.store.plan(now=NOW)
        with patch('app.store.run_job',side_effect=AssertionError('must use persisted plan')):
            again=Store(self.path).plan(now=NOW+timedelta(seconds=10))
        self.assertEqual(first['blocks'],again['blocks'])
        self.store.mutate('owner','finish','complete',{},ident=self.task['id'],revision=1)
        self.assertFalse(self.store.plan(now=NOW)['blocks'])

    def test_input_change_during_computation_never_publishes_old_plan(self):
        original=run_job
        def calculate(*args,**kwargs):
            self.store.mutate('owner','finish','complete',{},ident=self.task['id'],revision=1)
            return original(*args,**kwargs)
        with patch('app.store.run_job',side_effect=calculate):
            with self.assertRaises(Conflict):
                self.store.plan(now=NOW)

    def test_source_configuration_and_stale_state(self):
        self.store.configure_sources(['one'])
        self.assertFalse(self.store.plan(now=NOW)['calendar_inputs_ready'])
        self.store.source_result('one',[])
        self.assertTrue(self.store.plan()['calendar_inputs_ready'])
        future=datetime.now(timezone.utc)+timedelta(hours=1)
        self.assertFalse(self.store.plan(now=future)['calendar_inputs_ready'])
        self.store.configure_sources(['two'])
        self.assertEqual([s['id'] for s in self.store.plan()['sources']],['two'])

    def test_backup_restore_and_overwrite_refusal(self):
        backup=Path(self.tmp.name)/'backup.sqlite'
        receipt=checked_backup(self.path,backup)
        self.assertEqual(receipt['integrity'],'ok')
        self.assertEqual(backup.stat().st_mode & 0o777,0o600)
        self.assertEqual(Store(backup).tasks(),self.store.tasks())
        with self.assertRaises(ValueError):
            checked_backup(self.path,backup)
        with self.assertRaises(sqlite3.OperationalError):
            checked_backup(Path(self.tmp.name)/'missing',Path(self.tmp.name)/'bad')

class DiscoveryTests(unittest.TestCase):
    def test_credential_destination_rules(self):
        from app.discovery import allowed_url
        self.assertEqual(allowed_url('https://p01-caldav.icloud.com/path',['*.icloud.com']),'https://p01-caldav.icloud.com/path')
        for url in ('http://cloud.example/path','https://cloud.example.evil.test/path','https://user@cloud.example/path','https://cloud.example:8443/path'):
            with self.assertRaises(ValueError):
                allowed_url(url,['cloud.example'])

    def test_cross_origin_redirect_never_receives_credentials(self):
        import asyncio,httpx
        from app.discovery import discover
        original=httpx.AsyncClient
        calls=[]
        def respond(request):
            calls.append(str(request.url))
            return httpx.Response(302,headers={'Location':'https://untrusted.example/steal'})
        with patch('app.discovery.httpx.AsyncClient',side_effect=lambda **kw: original(transport=httpx.MockTransport(respond),**kw)):
            with self.assertRaises(ValueError):
                asyncio.run(discover('https://cloud.example/','user','secret',['cloud.example']))
        self.assertEqual(calls,['https://cloud.example/'])


if __name__=='__main__':
    unittest.main()
