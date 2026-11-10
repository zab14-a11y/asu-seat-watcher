# ASU seat watcher

Checks ASU's public Class Search every ~10 minutes for the sections in `classes.json`.
When one opens, it creates an issue in this repo, and GitHub emails you. It never logs in and never enrolls you.

- **Change what's watched:** edit `classes.json` (add your SCIT class, or remove a course once you're in).
- **Run a check now:** Actions tab → "Check ASU seats" → Run workflow.
- **Shabbat:** checks pause Friday 4:00 PM through Saturday 9:00 PM (Phoenix time).
- **Stops automatically** after the enrollment deadline in `classes.json` (`stop_after`).
- **Turn it off:** Actions tab → "Check ASU seats" → "..." → Disable workflow.
