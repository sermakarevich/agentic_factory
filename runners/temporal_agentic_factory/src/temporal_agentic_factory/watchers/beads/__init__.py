"""Beads watcher: one long-running workflow whose ticks claim ready beads in
the database af owns and spawn them as job workflows, then close the ones
whose job finished its work and block the rest.
client, shell, home, models, markers (the database and af's comments on it);
front_matter, parameters, mapping, ending, poll, temporal, tick (one tick);
last_check, trim, workflow (the loop); control, legacy (its lifecycle)."""
