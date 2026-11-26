# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""Private read-only synthetic calendar used only by the test Compose stack."""
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape
from fastapi import FastAPI, Response
from icalendar import Calendar, Event

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def feed():
    cal = Calendar()
    cal.add("prodid", "-//Etabli Interstice//Test calendar//EN")
    cal.add("version", "2.0")
    day = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    e = Event()
    e.add("uid", "interstice-synthetic-meeting")
    e.add("dtstamp", day)
    e.add("dtstart", day)
    e.add("dtend", day + timedelta(minutes=45))
    e.add("summary", "Test calendar · reserved meeting")
    e.add("rrule", {"freq": "daily", "count": 56})
    cal.add_component(e)
    return cal.to_ical()


@app.get("/health")
def health():
    return {"status": "ok", "synthetic": True}


@app.get("/feed.ics")
def ics():
    return Response(feed(), media_type="text/calendar")


@app.api_route("/dav/", methods=["REPORT"])
def dav():
    body = ('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            '<d:response><d:href>/dav/meeting.ics</d:href><d:propstat><d:prop><c:calendar-data>' + escape(feed().decode()) +
            '</c:calendar-data></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>')
    return Response(body, status_code=207, media_type="application/xml")
