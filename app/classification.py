# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""Conservative, local task metadata suggestions; no task or config mutation."""
import html
import re

CATEGORIES = ("discussion", "writing", "research", "software", "administration",
              "security", "learning", "practical", "other")
MODES = ("", "meeting", "phone", "email", "video", "message")


def _plain(value, limit=10000):
    return html.unescape(re.sub(r"<[^>]*>", " ", str(value or "")[:limit]))


def _has(pattern, text):
    return bool(re.search(pattern, text, re.I))


def _items(value, limit):
    return list(value[:limit]) if isinstance(value, (list, tuple)) else []


def _literal(alias, text):
    return bool(alias and re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text, re.I))


_COMM = r"\b(besprechen|abstimmen|anrufen|telefonieren|nachfragen|anfragen|antworten|rückfragen|rückmeldung|nachhalten|einverständnis|zusage|freigabe|unterschreiben lassen|discuss|coordinate|call|reply|ask|approval|follow up)\b"
_WRITING = r"\b(gesprächsnotiz|protokoll|dokumentieren|verschriftlichen|manuskript|manuscript|schreiben|verfassen|glie[d]?erung|write|draft|document|minutes)\b"


def infer_metadata(title, notes="", *, config=None):
    """Return only Task-compatible suggestions; caller preserves explicit fields.

    Config contains people [{name, aliases, roles}] and topics [{tag, aliases}].
    Aliases are literal strings, never executable patterns. Notes contribute only
    the first explicitly labelled next action, never quoted mail or history.
    Unknown or ambiguous recipients and channels remain blank.
    """
    config = config if isinstance(config, dict) else {}
    title = _plain(title, 300)
    parts = [p.strip() for p in title.split("|")]
    action = parts[-1]
    # Notes often contain historical email threads. Only an explicit next-action
    # field in the leading current update may refine an otherwise unknown action.
    leading = _plain(notes)[:2000]
    leading = re.split(r"(?:Früherer Quellenstand|Histor(?:y|ie)|Original message|From:|Von:|Quelle:)", leading, maxsplit=1, flags=re.I)[0]
    match = re.search(r"(?:Nächster[_ ]Schritt|Next action)\s*:\s*([^\n]+)", leading, re.I)
    next_action = match.group(1)[:500] if match else ""
    category = "other"
    # A documentation deliverable is not a fresh conversation, even if a name
    # or communication channel occurs in the old meeting's subject.
    resolved = _has(r"\b(bereits erledigt|bereits gesendet|freigabe (?:bereits )?erteilt|already sent|already completed|approval received)\b", action)
    documentation = _has(r"\b(gesprächsnotiz|protokoll|meeting notes|minutes|dokumentieren|verschriftlichen)\b", action)
    if documentation:
        category = "writing"
    elif _has(r"\b(rechnung|invoice|beleg|quittung)\b", action) and _has(r"\b(download|herunterladen|ablegen|bezahlen|zahlen|pay|file)\b", action):
        category = "administration"
    elif not resolved and (_has(_COMM, action) or _has(r"\b(mail|email|e-mail|nachricht)\b.*\b(senden|send|schicken)\b", action)):
        category = "discussion"
    elif _has(_WRITING, action):
        category = "writing"
    else:
        rules = (
            ("security", r"\b(passwort|password|2fa|sicherheitsüberprüfung|security|zugriffsrecht|berechtigung|vulnerability)\b"),
            ("software", r"\b(code|debug|implementieren|programmieren|deploy|deployment|software|bug|container|api)\b"),
            ("research", r"\b(analysieren|auswerten|analyse|auswertung|experiment|statistik|literaturrecherche|research|analyze|analysis)\b"),
            ("administration", r"\b(antrag|formular|rechnung|invoice|abrechnung|reisekosten|buchen|beantragen|einreichen|verlängern|verwaltung)\b"),
            ("learning", r"\b(lernen|üben|fortbildung|weiterbildung|kurs|study|learn|training)\b"),
            ("practical", r"\b(kaufen|abholen|reparieren|reinigen|einkaufen|montieren|buy|collect|repair|clean)\b"),
        )
        for candidate, pattern in rules:
            if _has(pattern, action):
                category = candidate
                break
        if category == "other" and not resolved and _has(_COMM, next_action):
            category = "discussion"
            action = next_action
        if category == "other":
            prefix = parts[0].strip().casefold()
            category = {"manuscript": "writing", "manuskript": "writing", "research": "research", "software": "software", "lernen": "learning"}.get(prefix, "other")
    person, mode = "", ""
    if category == "discussion":
        # A role or alias must be the direct object/partner of the current
        # action. Merely appearing in a title, CC or author list is insufficient.
        current = re.split(r"\b(?:cc|bcc|kopie|autoren|authors)\s*:", action, maxsplit=1, flags=re.I)[0]
        selected = []
        for entry in _items(config.get("people"), 100):
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            if not name or len(name) > 200:
                continue
            aliases = [name] + _items(entry.get("aliases"), 30) + _items(entry.get("roles"), 20)
            for alias in aliases:
                if not isinstance(alias, str) or not 0 < len(alias) <= 200:
                    continue
                escaped = re.escape(alias)
                direct = (r"\b(?:mit|an|bei|von|with|to|ask|call)\s+(?:(?:dem|der|den|prof\.?|dr\.?)\s+){0,3}" + escaped + r"(?!\w)")
                reverse = r"(?<!\w)" + escaped + r"\s+(?:anrufen|fragen|kontaktieren|um\b|antworten|email|call)"
                if _has(direct, current) or _has(reverse, current):
                    selected.append(name)
                    break
        person = "; ".join(dict.fromkeys(selected))
        if len(person) > 200:
            person = ""  # Do not silently truncate a person's identity.
        channel_text = action
        if len(parts) > 1:
            channel_text = parts[0] + " " + channel_text
        channels = []
        for value, pattern in (
            ("email", r"\b(e-?mail|mail)\b"),
            ("phone", r"\b(anrufen|telefonieren|telefon|phone|call)\b"),
            ("meeting", r"\b(meeting|treffen|persönlich|besprechung)\b"),
            ("video", r"\b(videokonferenz|video call|videocall)\b"),
            ("message", r"\b(chat|whatsapp|signal|text message)\b"),
        ):
            if _has(pattern, channel_text):
                channels.append(value)
        if "video" in channels and "phone" in channels:
            channels.remove("phone")
        if len(channels) == 1:
            mode = channels[0]
    tags = []
    # Only explicit project identifiers and configured topic aliases in the
    # title become tags; historical notes cannot introduce unrelated topics.
    candidates = re.findall(r"\b(?:PRJ-\d{4}-\d{3}|P\d{3}|[A-Z]{2,8}-\d{3})\b", title)
    for entry in _items(config.get("topics"), 100):
        if isinstance(entry, dict) and any(_literal(alias, title) for alias in _items(entry.get("aliases"), 30) if isinstance(alias, str)):
            candidates.append(str(entry.get("tag", "")))
    seen = set()
    for value in candidates:
        value = value.strip()
        if value and len(value) <= 80 and value.casefold() not in seen:
            tags.append(value)
            seen.add(value.casefold())
        if len(tags) == 20:
            break
    return {"category": category, "person": person, "communication_mode": mode, "tags": tags}
