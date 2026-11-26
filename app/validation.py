# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""Independent hard-constraint checks before accepting a computed plan."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from .domain import instant


def validate_plan(tasks, events, plan):
    by_id={t['id']:t for t in tasks}
    allocated={t['id']:[] for t in tasks}
    now=instant(plan['calculated_at'])
    horizon=now+timedelta(days=plan['horizon_days'])
    zone=ZoneInfo(plan['time_zone'])
    reserved=[]
    for block in plan['blocks']:
        task=by_id[block['task_id']]
        start,end=instant(block['start']),instant(block['end'])
        minutes=(end-start).total_seconds()/60
        if not task['scheduled'] or task['completed'] or not (now<=start<end<=horizon) or minutes!=block['minutes']:
            raise ValueError('Invalid planned interval')
        if (task['due'] and end>instant(task['due'])) or (task['earliest'] and start<instant(task['earliest'])):
            raise ValueError('Task date constraint violated')
        if task['fixed_start']:
            if start!=instant(task['fixed_start']):raise ValueError('Fixed block moved')
        else:
            a,b=start.astimezone(zone),end.astimezone(zone)
            finish=b.hour*60+b.minute+(1440 if b.date()>a.date() else 0)
            if a.weekday() not in task['weekdays'] or a.hour*60+a.minute<task['hours_start']*60 or finish>task['hours_end']*60:
                raise ValueError('Working window violated')
        pad=timedelta(minutes=task['buffer'])
        for event in events:
            if event.get('busy',True) and start-pad<instant(event['end']) and end+pad>instant(event['start']):
                raise ValueError('Calendar conflict')
        allocated[task['id']].append((start,end,minutes))
        reserved.append((start-pad,end+pad))
    reserved.sort()
    for a,b in zip(reserved,reserved[1:]):
        if a[1]>b[0]:raise ValueError('Task blocks overlap')
    shortages={}
    for item in plan['shortages']:
        if item['task_id'] not in by_id or item['minutes']<=0:raise ValueError('Invalid shortage')
        shortages[item['task_id']]=shortages.get(item['task_id'],0)+item['minutes']
    for task in tasks:
        blocks=allocated[task['id']]
        remaining=max(0,task['minutes']-task.get('progress',0))
        if task['scheduled'] and not task['completed'] and sum(b[2] for b in blocks)+shortages.get(task['id'],0)!=remaining:
            raise ValueError('Remaining effort was lost or duplicated')
        if not task['split'] and len(blocks)>1:raise ValueError('Unsplit task fragmented')
        for _,_,duration in blocks:
            if not task['fixed_start'] and duration<min(task['min_block'],remaining):
                raise ValueError('Block below minimum duration')
        for predecessor in task['dependencies']:
            before=by_id[predecessor]
            if not blocks or before['completed'] or before.get('progress',0)>=before['minutes']:continue
            earlier=allocated[predecessor]
            if not earlier or shortages.get(predecessor) or max(b[1] for b in earlier)>min(b[0] for b in blocks):
                raise ValueError('Dependency not completed before task')
    return plan
