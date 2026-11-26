# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
import asyncio
from datetime import datetime, date, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import httpx
import icalendar
import recurring_ical_events
from defusedxml import ElementTree


async def fetch(source):
    """Sources are administrator-mounted configuration, never user-supplied URLs."""
    url = source["url"].replace("webcal://", "https://", 1)
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.fragment or parsed.scheme not in ("http", "https"):
        raise ValueError("Unsupported calendar address")
    if parsed.scheme != "https" and not source.get("allow_private_http", False):
        raise ValueError("HTTPS is required")
    headers, method, body = {"Accept-Encoding": "identity"}, "GET", None
    if source["kind"] == "caldav":
        start = datetime.now(timezone.utc) - timedelta(days=1)
        end = start + timedelta(days=58)
        method = "REPORT"
        headers = {"Depth": "1", "Content-Type": "application/xml; charset=utf-8", "Accept-Encoding": "identity"}
        body = ('<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                '<d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR">'
                '<c:comp-filter name="VEVENT"><c:time-range start="' + start.strftime('%Y%m%dT%H%M%SZ') +
                '" end="' + end.strftime('%Y%m%dT%H%M%SZ') + '"/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
    elif source["kind"] != "ics":
        raise ValueError("Unsupported calendar kind")
    auth = None
    if source.get("password_file"):
        auth = (source["username"], Path(source["password_file"]).read_text().strip())
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
        async with asyncio.timeout(30), client.stream(method, url, headers=headers, content=body, auth=auth) as response:
            response.raise_for_status()
            if response.status_code not in (200, 207):
                raise ValueError("Unexpected calendar response")
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("Compressed calendar responses are not accepted")
            data = bytearray()
            async for part in response.aiter_bytes():
                data.extend(part)
                if len(data) > 2_000_000:
                    raise ValueError("Calendar response exceeds test limit")
    from .work import run_job
    safe_source = {k: source[k] for k in ("id", "time_zone", "all_day_busy") if k in source}
    return await asyncio.to_thread(run_job, "calendar", {
        "data": bytes(data).decode("utf-8-sig"), "method": method, "source": safe_source}, timeout=60)


def decode(data, method, source):
    if method == "REPORT":
        root = ElementTree.fromstring(data)
        if root.tag != "{DAV:}multistatus":
            raise ValueError("Invalid CalDAV response")
        documents = []
        for item in root.findall("{DAV:}response"):
            propstats = item.findall("{DAV:}propstat")
            if item.find("{DAV:}status") is not None or not propstats:
                raise ValueError("Incomplete CalDAV response; retaining prior snapshot")
            found_data = False
            for propstat in propstats:
                if " 200 " not in propstat.findtext("{DAV:}status", ""):
                    raise ValueError("Partial CalDAV failure; retaining prior snapshot")
                node = propstat.find("{DAV:}prop/{urn:ietf:params:xml:ns:caldav}calendar-data")
                if node is not None and node.text:
                    documents.append(node.text)
                    found_data = True
            if not found_data:
                raise ValueError("Missing calendar data; retaining prior snapshot")
        if len(documents) > 200:
            raise ValueError("Too many calendar objects for test instance")
    else:
        documents = [data]
    return parse(documents, source)


def parse(documents, source, now=None):
    now = now or datetime.now(timezone.utc)
    tz = ZoneInfo(source.get("time_zone", "Europe/Berlin"))
    events = []
    for document in documents:
        calendar = icalendar.Calendar.from_ical(document)
        raw_events = calendar.walk("VEVENT")
        if len(raw_events) > 200:
            raise ValueError("Too many raw calendar events")
        for event in raw_events:
            rule = event.get("RRULE")
            if rule and str(rule.get("FREQ", [""])[0]) not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
                raise ValueError("High-frequency recurrence is not supported")
            if rule and any(len(rule.get(part, [])) > 1 for part in ("BYHOUR", "BYMINUTE", "BYSECOND")):
                raise ValueError("Multiple daily recurrence times exceed test limits")
        for event in recurring_ical_events.of(calendar).between(now - timedelta(days=1), now + timedelta(days=57)):
            if str(event.get("STATUS", "")).upper() == "CANCELLED":
                continue
            start = event.decoded("DTSTART")
            all_day = isinstance(start, date) and not isinstance(start, datetime)
            end = event.decoded("DTEND", start + (timedelta(days=1) if all_day else timedelta(minutes=30)))
            if all_day:
                start, end = datetime.combine(start, time(), tz), datetime.combine(end, time(), tz)
            if start.tzinfo is None:
                start = start.replace(tzinfo=tz)
            if end.tzinfo is None:
                end = end.replace(tzinfo=tz)
            if end < start:
                raise ValueError("Invalid event interval")
            events.append({"id": str(event.get("UID", "")), "source": source["id"],
                           "title": str(event.get("SUMMARY", "Busy"))[:300],
                           "start": start.astimezone(timezone.utc).isoformat(), "end": end.astimezone(timezone.utc).isoformat(),
                           "busy": end > start and str(event.get("TRANSP", "OPAQUE")).upper() != "TRANSPARENT" and (not all_day or source.get("all_day_busy", True))})
            if len(events) > 5000:
                raise ValueError("Expanded calendar exceeds test limit")
    return events
