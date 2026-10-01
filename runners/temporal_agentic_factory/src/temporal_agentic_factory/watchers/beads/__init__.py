"""Beads watcher: one long-running workflow whose ticks claim ready beads in
the database af owns and spawn them as job workflows, and close finished ones.
client, shell, home, models (the database); mapping, poll, temporal, tick (one
tick); last_check, trim, workflow (the loop); control, legacy (its lifecycle)."""
