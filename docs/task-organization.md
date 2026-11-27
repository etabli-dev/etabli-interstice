# Lists, categories and discussion details

Lists remain work areas. Categories describe the action and do not replace lists or timer-history categories in Focus.

The nine category choices are Discussion; Writing & review; Research & analysis; Software & systems; Administration & planning; Security & accounts; Learning & teaching; Errands & practical work; and Other. New and older unclassified tasks default to Other. Existing titles do not trigger automatic classification.

Tasks can additionally carry a person, a communication mode (unspecified, meeting, phone, email, video or message), and up to twenty topic tags. These are optional descriptive fields: they neither book meetings nor send messages. A discussion item can be prepared before a person or mode is known. Tags are trimmed and deduplicated without changing their displayed spelling.

The web workspace creates and edits list/category/person/mode/tags, filters by category, and searches across title and these details. Edits use task revisions and persistent idempotent receipts. Focus displays and searches the same fields on desktop, Android and iOS and retains them in its device-local task cache. The Focus candidate includes an Edit details form for these fields, with durable revision-checked saves. Editing requires a writable installation; shadow mode remains protected. A failed schedule calculation does not hide the task list.

List consolidation is explicit during import: `python -m app.migration export.json --database new.sqlite --list-map list-map.json`. The JSON object maps source names to target names; unmapped lists are retained. Task and recurring-template lists change together, while the exact source archive and credited progress remain intact. Import always requires a new database. Keep a backup and review counts before selecting the new database.

Example mapping: `{"PhD":"Forschung","Habil":"Forschung","Personal":"Privat","Famille":"Privat","Shop":"Privat"}`. The web list suggestions are Lehre, Klinik, Forschung, Ausbildung, Firma, Bw and Privat; other existing list names remain usable.
