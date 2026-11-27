# Automatic task metadata

`app.classification.infer_metadata(title, notes, config=...)` returns four Task-compatible suggestions: category, person, communication_mode and tags. It performs bounded local text matching with no model, network calls or state changes. Call it on creation before validation, then overlay explicitly supplied metadata fields, including deliberately empty values and `category: other`. Do not apply it unconditionally to edits or imported historical tasks.

The action after the final `|` takes priority over source prefixes: an email invoice download is administration, and a meeting note to document is writing. Notes contribute only a labelled current next action when the title is otherwise unknown. Unknown actions become other. Person suggestions use three priorities: a direct current discussion recipient (for example `mit Example abstimmen`), an explicit configured name or unique alias in the task title, then contacts documented in a matching private project configuration. Related people apply to research, writing, software and other work too; they do not change the category or imply a meeting, email or other communication mode. CC-only mentions and names found only in historical notes remain excluded. Conflicting explicit communication channels remain blank.

Private configuration is a JSON object with `people`, `topics` and optional `projects` arrays:

Set `INTERSTICE_CLASSIFICATION_FILE` to a private, read-only mounted JSON file. Native REST and MCP creation and the legacy compatibility creation route all apply these rules. The browser defaults to automatic suggestions; disabling that option sends explicit metadata instead. Updates preserve existing metadata unless a caller explicitly changes it.

```json
{
  "people": [{"name": "Alex Example", "aliases": ["Example"], "roles": ["Vorgesetzter"]}],
  "topics": [{"tag": "Project Atlas", "aliases": ["Atlas"]}],
  "projects": [{
    "aliases": ["P123", "Project Atlas"],
    "related_people": [{
      "name": "Morgan Sample",
      "role": "corresponding_author",
      "provenance": {"file": "private/manuscript.md", "line": 4}
    }]
  }]
}
```

Aliases and roles are literal strings, not regular expressions. Store personal names, organization-specific roles and project aliases outside the repository. The caller loads trusted configuration; the classifier performs no file access. Tags come only from explicit project identifiers or configured topic aliases in the title, are deduplicated and bounded to twenty entries of eighty characters. Person strings are bounded to two hundred characters; overly long combined identities are omitted rather than truncated.

These are conservative suggestions, not semantic guarantees. In particular ambiguous initials should remain unconfigured, and historical references in unstructured titles cannot always be distinguished. Preserve manual corrections on subsequent edits. Tests cover action precedence, direct recipients, documentation, historical notes, bounds and explicit-field overlay semantics.

Project evidence can identify corresponding or last authors and previously contacted collaborators. Roles, provenance and evidence excerpts stay in the private configuration; returned task metadata contains only names. The caller is responsible for reviewing that evidence before enabling a project rule. Entries marked `confidence: low`, `unverified` or `unknown`, name placeholders, ambiguous aliases and initials are excluded. A project alias must match a complete literal phrase or identifier in the title; `P123` does not match `P1234`. An alias shared by different projects is ignored. Explicit task names take priority over project defaults; direct discussion recipients take priority over both. Roles such as supervisor are used only with a direct discussion construction. Combined person values exceeding 200 characters remain blank rather than being truncated.

The classifier neither reopens completed work nor applies these suggestions to existing tasks automatically. A separate reviewed metadata update must preserve explicit recipients and corrections already made by the user.
