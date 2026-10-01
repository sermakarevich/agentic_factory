"""The cleaner: a Temporal Schedule whose runs delete old closed runs of the
workflow types `[[cleaner.rules]]` names, its own among them.
rules (what a clean returns, and which listed runs one rule deletes), clean
(the activity: list, select, delete), workflow (one scheduled run), schedule
(the cleaner schedule)."""
