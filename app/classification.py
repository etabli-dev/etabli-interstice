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


_PLACEHOLDERS = {"unknown", "unbekannt", "tbd", "tba", "n/a", "none", "author", "autor",
                 "coauthor", "co-author", "last author", "corresponding author",
                 "first author", "et al", "et al.", "name", "placeholder"}


def _name(value):
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not 2 <= len(value) <= 200 or value.casefold() in _PLACEHOLDERS:
        return ""
    if any(c in value for c in ("\n", "\r", ";", "[", "]", "<", ">", "?")):
        return ""
    letters = "".join(c for c in value if c.isalpha())
    if len(letters) < 3 or (len(letters) <= 4 and letters.isupper() and not any(c.isspace() for c in value)):
        return ""
    return value


def _alias(value, *, project=False):
    if not isinstance(value, str):
        return ""
    value = value.strip()
    letters = "".join(c for c in value if c.isalpha())
    if not 3 <= len(value) <= 200 or not letters or value.casefold() in _PLACEHOLDERS:
        return ""
    if project:
        return "" if value.casefold() in {"project", "research", "study", "publication", "manuscript"} else value
    # Initials are not names, even if somebody configured them accidentally.
    if len(letters) <= 2 or (len(letters) <= 4 and letters.isupper() and not any(c.isspace() for c in value)):
        return ""
    return value


def _project_people(project):
    people = []
    for entry in _items(project.get("related_people"), 30):
        if not isinstance(entry, dict) or entry.get("confidence") in ("low", "unverified", "unknown"):
            continue
        name = _name(entry.get("name"))
        if name:
            people.append(name)
    return list(dict.fromkeys(people))


def _person_indexes(config):
    """Only unique literal aliases may identify a person; roles are direct-only."""
    named, direct = {}, {}
    def add(index, alias, name):
        if alias:
            index.setdefault(alias.casefold(), set()).add(name)
    for entry in _items(config.get("people"), 300):
        if not isinstance(entry, dict):
            continue
        name = _name(entry.get("name"))
        if not name:
            continue
        for value in [name] + _items(entry.get("aliases"), 30):
            alias = _alias(value)
            add(named, alias, name)
            add(direct, alias, name)
        for value in _items(entry.get("roles"), 20):
            add(direct, _alias(value), name)
    for project in _items(config.get("projects"), 300):
        if isinstance(project, dict):
            for name in _project_people(project):
                add(named, _alias(name), name)
                add(direct, _alias(name), name)
    return ({a: next(iter(n)) for a, n in named.items() if len(n) == 1 and len(direct.get(a, n)) == 1},
            {a: next(iter(n)) for a, n in direct.items() if len(n) == 1})


def _title_person(alias, name, title):
    for match in re.finditer(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", title, re.I):
        if " " not in alias and " " in name:
            preceding = re.search(r"([\w]+)\s+$", title[:match.start()])
            if preceding:
                word = preceding.group(1)
                if (word[0].isupper() and word.isalpha()
                        and word.casefold() not in {"herr", "frau", "prof", "dr"}
                        and word.casefold() not in name.casefold().split()):
                    # Do not expand a surname inside a different explicit name.
                    continue
        return True
    return False


def _related_people(title, config, named):
    # Explicit subject names are related people, not necessarily recipients.
    # Quoted mail headers are never examined; CC-only mentions remain excluded.
    subject = re.split(r"\b(?:cc|bcc|kopie)\s*:", title, maxsplit=1, flags=re.I)[0]
    explicit = list(dict.fromkeys(name for alias, name in named.items() if _title_person(alias, name, subject)))
    if explicit:
        # A literal short name and its already-matched full name should not
        # produce duplicate related people; this does not expand short names.
        return [name for name in explicit if not any(name.casefold() != other.casefold()
                and (" " + name.casefold() + " ") in (" " + other.casefold() + " ")
                for other in explicit)]
    projects = [p for p in _items(config.get("projects"), 300) if isinstance(p, dict)]
    aliases = {}
    for index, project in enumerate(projects):
        for value in _items(project.get("aliases"), 30):
            alias = _alias(value, project=True)
            if alias:
                aliases.setdefault(alias.casefold(), set()).add(index)
    matches = {next(iter(indices)) for alias, indices in aliases.items()
               if len(indices) == 1 and _literal(alias, subject)}
    return list(dict.fromkeys(name for index in sorted(matches) for name in _project_people(projects[index])))


def _joined_people(names):
    value = "; ".join(dict.fromkeys(names))
    return value if len(value) <= 200 else ""


_COMM = r"\b(besprechen|abstimmen|anrufen|telefonieren|nachfragen|anfragen|antworten|rückfragen|rückmeldung|nachhalten|einverständnis|zusage|freigabe|unterschreiben lassen|discuss|coordinate|call|reply|ask|approval|follow up)\b"
_WRITING = r"\b(gesprächsnotiz|protokoll|dokumentieren|verschriftlichen|manuskript|manuscript|schreiben|verfassen|glie[d]?erung|write|draft|document|minutes)\b"


def infer_metadata(title, notes="", *, config=None):
    """Return only Task-compatible suggestions; caller preserves explicit fields.

    Private config contains people, topics and projects with related_people.
    Direct recipients win, then explicit title names, then project contacts.
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
            ("administration", r"\b(antrag|formular|rechnung|invoice|abrechnung|reisekosten|buchen|beantragen|einreichen|verlängern|verwaltung|abgabenbescheid|widerspruch|adressänderung)\b|\b(?:adresse|mailadresse|e-mail-adresse|email address)\b.*\b(?:umstellen|ändern|aktualisieren|change|update)\b"),
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
    named, direct_names = _person_indexes(config)
    selected = []
    if category == "discussion":
        # A role or alias must be the direct object/partner of the current
        # action. Merely appearing in a title, CC or author list is insufficient.
        current = re.split(r"\b(?:cc|bcc|kopie|autoren|authors)\s*:", action, maxsplit=1, flags=re.I)[0]
        for alias, name in direct_names.items():
            escaped = re.escape(alias)
            direct = (r"\b(?:mit|an|bei|von|with|to|ask|call)\s+(?:(?:dem|der|den|prof\.?|dr\.?)\s+){0,3}" + escaped + r"(?!\w)")
            reverse = r"(?<!\w)" + escaped + r"\s+(?:anrufen|fragen|kontaktieren|um\b|antworten|email|call)"
            if _has(direct, current) or _has(reverse, current):
                selected.append(name)
        person = _joined_people(selected)
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
    if not selected:
        person = _joined_people(_related_people(title, config, named))
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
