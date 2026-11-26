# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from app.domain import Task, schedule
from app.migration import import_snapshot, local_time, prepare, snapshot_items
from app.recurrence import occurrences
from app.store import Store
from app.validation import validate_plan

NOW = datetime(2026, 11, 26, 7, tzinfo=timezone.utc)


def fixture():
    task = dict(id='one', itemType='task', title='Synthetic work', listId='list',
                durationMinutes=60, minLengthMinutes=15, priority='normal', completed=False,
                isAutoScheduled=True, dueDateTime='2026-11-25T18:00:00', timeZone='Europe/Berlin',
                bufferBeforeMinutes=15, bufferAfterMinutes=15, progressMinutes=20)
    return {'format':'flowsavvy-mcp-export-v1', 'finished_at':NOW.isoformat(),
            'list_lists':{'lists':[{'id':'list','title':'Work','schedulingHoursId':'hours'}]},
            'list_scheduling_hours':{'defaultSchedulingHoursId':'hours', 'schedulingHours':[
                {'id':'hours','recurringHours':{'thursday':[{'startTime':'08:00','endTime':'12:00'},
                                                          {'startTime':'13:30','endTime':'18:00'}]}}]},
            'collections':[{'kind':kind, 'completed':completed, 'pages':[{'items':[task] if kind=='task' and not completed else []}]}
                           for kind in ('task','event') for completed in (False,True)]}


class MigrationTests(unittest.TestCase):
    def test_snapshot_rejects_truncation_duplicate_and_changed_items(self):
        for change in ('truncated','duplicate','changed','missing'):
            data=fixture()
            pages=data['collections'][0]['pages']
            if change=='truncated':pages[-1]['nextPageToken']='more'
            if change=='duplicate':pages[0]['items']*=2
            if change=='changed':
                data['collections'][1]['pages'][0]['items']=[dict(pages[0]['items'][0],completed=True)]
            if change=='missing':data['collections'].pop()
            with self.assertRaises(ValueError):snapshot_items(data)

    def test_source_wall_clock_requires_unambiguous_time(self):
        for value in ('2026-03-29T02:30:00','2026-10-25T02:30:00'):
            with self.assertRaises(ValueError):local_time(value,'Europe/Berlin')
        self.assertEqual(local_time('2026-11-26T08:00:00','Europe/Berlin'),'2026-11-26T08:00:00+01:00')

    def test_atomic_archive_preserves_progress_and_refuses_existing_database(self):
        with tempfile.TemporaryDirectory() as temp:
            src,dst=Path(temp)/'export.json',Path(temp)/'shadow.sqlite'
            src.write_text(json.dumps(fixture()))
            report=import_snapshot(src,dst)
            store=Store(dst)
            self.assertEqual(store.tasks()[0]['progress'],20)
            self.assertEqual(report['source_items'],{'task':1})
            with sqlite3.connect(dst) as db:
                self.assertEqual(db.execute('SELECT body FROM migration_snapshot').fetchone()[0],src.read_bytes())
            with self.assertRaises(FileExistsError):import_snapshot(src,dst)
            self.assertEqual(len(store.tasks()),1)

    def test_missing_dependency_and_asymmetric_buffers_fail_before_write(self):
        for field,value in [('blockedByIds',['missing']),('bufferAfterMinutes',10)]:
            data=fixture();data['collections'][0]['pages'][0]['items'][0][field]=value
            with self.assertRaises(ValueError):prepare(data)

    def test_multiple_windows_overrides_and_lateness_are_validated(self):
        _,tasks,_,progress=prepare(fixture())
        tasks[0]['progress']=progress[tasks[0]['id']]
        tasks[0]['earliest']='2026-11-26T12:00:00+01:00'
        plan=schedule(tasks,[],now=NOW)
        validate_plan(tasks,[],plan)
        self.assertEqual(plan['blocks'][0]['start'],'2026-11-26T12:30:00+00:00')
        self.assertEqual(len(plan['late']),1)
        tasks[0]['date_overrides']={'2026-11-26':[]}
        next_plan=schedule(tasks,[],now=NOW)
        self.assertGreater(next_plan['blocks'][0]['start'],'2026-11-26T23:59:59+00:00')

    def test_recurrence_dst_stable_ids_cancellation_and_progress(self):
        template=Task(title='Repeat', minutes=30, due='2026-03-27T18:00:00+01:00',
                      earliest='2026-03-27T08:00:00+01:00',time_zone='Europe/Berlin').model_dump(mode='json')
        series={'id':'series','template':template,'rule':'FREQ=DAILY;COUNT=5',
                'anchor':template['due'],'zone':'Europe/Berlin','cancelled':['2026-03-28']}
        now=datetime(2026,3,27,tzinfo=timezone.utc)
        rows=occurrences(series,now)
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[1][1]['due'],'2026-03-29T18:00:00+02:00')
        self.assertEqual(rows[1][1]['earliest'],'2026-03-29T08:00:00+02:00')
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'data.sqlite')
            with store.db() as db:
                db.execute('INSERT INTO series VALUES(?,?)',(series['id'],json.dumps(series)))
                store._materialize(db,now)
            ident=rows[0][0]
            store.mutate('focus','credit','progress',{'session_id':'session','minutes':25},ident=ident)
            with store.db() as db:
                store._materialize(db,now)
                tasks=store._tasks(db)
            self.assertEqual(len(tasks),4)
            self.assertEqual(next(t['progress'] for t in tasks if t['id']==ident),25)

    def test_forbidden_recurrence_frequencies(self):
        template=Task(title='Repeat',due=NOW).model_dump(mode='json')
        for rule in ('FREQ=SECONDLY','FREQ=DAILY;BYHOUR=1,2'):
            with self.assertRaises(ValueError):occurrences({'id':'x','template':template,'rule':rule,'anchor':NOW.isoformat(),'zone':'UTC'},NOW)

    def test_replanning_keeps_valid_work_and_moves_conflicts(self):
        first=dict(Task(title='Existing',minutes=60).model_dump(mode='json'),id='first',progress=0)
        initial=schedule([first],[],now=NOW)
        urgent=dict(Task(title='New urgent',priority=3,minutes=60).model_dump(mode='json'),id='urgent',progress=0)
        stable=schedule([first,urgent],[],now=NOW,previous=initial['blocks'])
        validate_plan([first,urgent],[],stable)
        self.assertEqual(next(b for b in stable['blocks'] if b['task_id']=='first'),initial['blocks'][0])
        event={k:initial['blocks'][0][k] for k in ('start','end')}
        moved=schedule([first,urgent],[event],now=NOW,previous=stable['blocks'])
        validate_plan([first,urgent],[event],moved)
        self.assertNotEqual(next(b['start'] for b in moved['blocks'] if b['task_id']=='first'),event['start'])

    def test_retained_dependent_moves_when_predecessor_loses_slot(self):
        a=dict(Task(title='Before').model_dump(mode='json'),id='a',progress=0)
        b=dict(Task(title='After',dependencies=['a']).model_dump(mode='json'),id='b',progress=0)
        old=schedule([a,b],[],now=NOW)
        event={'start':old['blocks'][0]['start'],'end':old['blocks'][-1]['end']}
        new=schedule([a,b],[event],now=NOW,previous=old['blocks'])
        validate_plan([a,b],[event],new)
        self.assertGreaterEqual(new['blocks'][0]['start'],event['end'])

    def test_calendar_cache_still_fetches_but_skips_unchanged_expansion(self):
        import asyncio, httpx
        from app.calendars import fetch
        original=httpx.AsyncClient
        body=['BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n']
        calls=[]
        def respond(request):
            calls.append(request.url)
            return httpx.Response(200,text=body[0])
        cache={}
        with patch('app.calendars.httpx.AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(respond),**kw)), patch('app.work.run_job',return_value=[]) as worker:
            source={'id':'calendar','url':'https://calendar.example/test.ics','kind':'ics'}
            asyncio.run(fetch(source,cache));asyncio.run(fetch(source,cache))
            self.assertEqual(len(calls),2)
            self.assertEqual(worker.call_count,1)
            body[0]+='\r\n'
            asyncio.run(fetch(source,cache))
            self.assertEqual(worker.call_count,2)

    def test_shadow_mode_denies_mutations_even_for_admin(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        with tempfile.TemporaryDirectory() as temp:
            token='synthetic-owner-token-of-at-least-32-characters'
            app=create_app({'data':temp,'public_url':'http://testserver','mode':'shadow',
                            'clients':[{'id':'owner','role':'admin','token':token}]})
            with TestClient(app) as client:
                headers={'Authorization':'Bearer '+token,'Idempotency-Key':'create'}
                self.assertEqual(client.get('/api/v1/status',headers=headers).json()['role'],'read')
                self.assertEqual(client.post('/api/v1/tasks',headers=headers,json={'title':'Must not be written'}).status_code,403)
                self.assertEqual(app.state.store.tasks(),[])


if __name__=='__main__':unittest.main()
