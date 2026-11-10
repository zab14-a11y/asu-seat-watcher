"""
ASU seat watcher.

Checks ASU's public Class Search for the sections listed in classes.json.
When one of them has an open seat, it opens a GitHub issue in this repo
(which emails you). When the seat fills again, it closes that issue, so a
later opening sends a fresh email.

It never logs into My ASU and never enrolls you. It only reads public data.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

PHOENIX = timezone(timedelta(hours=-7))  # Arizona has no daylight saving time
API = "https://eadvs-cscc-catalog-api.apps.asu.edu/catalog-microservices/api/v1/search/classes"
LABEL = "seat-open"


def in_shabbat_pause(now):
    """Pause from Friday 4:00 PM through Saturday 9:00 PM Phoenix time."""
    wd, t = now.weekday(), now.hour * 60 + now.minute  # Mon=0 ... Fri=4, Sat=5
    return (wd == 4 and t >= 16 * 60) or (wd == 5 and t < 21 * 60)


def fetch_course(term, subject, number):
    query = urllib.parse.urlencode({
        "refine": "Y", "campusOrOnlineSelection": "A", "honors": "F", "promod": "F",
        "searchType": "all", "subject": subject, "catalogNbr": number, "term": term,
    })
    req = urllib.request.Request(
        f"{API}?{query}",
        headers={"Authorization": "Bearer null", "User-Agent": "personal-seat-watcher"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("classes", [])


def open_seats(cls):
    info = cls.get("seatInfo") or {}
    c = cls["CLAS"]
    cap = info.get("ENRL_CAP", c.get("ENRLCAP", 0))
    tot = info.get("ENRL_TOT", c.get("ENRLTOT", 0))
    return int(cap) - int(tot)


def check_seats(cfg, fetch=None):
    """Return {class_number: open_seats} for every watched section found."""
    fetch = fetch or fetch_course
    wanted = {s["class_number"] for s in cfg["sections"]}
    courses = {tuple(s["course"].split()) for s in cfg["sections"]}
    found = {}
    for subject, number in sorted(courses):
        for cls in fetch(cfg["term"], subject, number):
            nbr = cls["CLAS"]["CLASSNBR"]
            if nbr in wanted:
                found[nbr] = open_seats(cls)
    return found


class GitHub:
    def __init__(self, repo, token):
        self.base = f"https://api.github.com/repos/{repo}"
        self.token = token

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "personal-seat-watcher",
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r) if r.status != 204 else None

    def open_alerts(self):
        """Map class number -> issue number for open alert issues."""
        issues = self._call("GET", f"/issues?state=open&labels={LABEL}&per_page=100")
        out = {}
        for i in issues:
            title = i["title"]
            if "#" in title:
                out[title.split("#")[1].split()[0]] = i["number"]
        return out

    def create(self, title, body):
        self._call("POST", "/issues", {"title": title, "body": body, "labels": [LABEL]})

    def comment_and_close(self, number, text):
        self._call("POST", f"/issues/{number}/comments", {"body": text})
        self._call("PATCH", f"/issues/{number}", {"state": "closed"})


def main():
    with open(os.path.join(os.path.dirname(__file__), "classes.json")) as f:
        cfg = json.load(f)

    now = datetime.now(PHOENIX)
    stamp = now.strftime("%a %b %d, %I:%M %p")
    if now.date().isoformat() > cfg["stop_after"]:
        print("Past the enrollment deadline; nothing to do.")
        return
    if in_shabbat_pause(now):
        print(f"{stamp}: Shabbat pause, skipping this check.")
        return

    seats = check_seats(cfg)
    by_nbr = {s["class_number"]: s for s in cfg["sections"]}
    for nbr, s in by_nbr.items():
        status = f"{seats[nbr]} open" if nbr in seats else "NOT FOUND"
        print(f"{s['course']} #{nbr} ({s['when']}, {s['instructor']}): {status}")

    missing = [n for n in by_nbr if n not in seats]
    if missing:
        print(f"Warning: sections not found in Class Search: {missing}", file=sys.stderr)

    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not (repo and token):
        print("(No GitHub token: dry run, no emails sent.)")
        return

    gh = GitHub(repo, token)
    alerts = gh.open_alerts()
    for nbr, n_open in seats.items():
        s = by_nbr[nbr]
        if n_open > 0 and nbr not in alerts:
            gh.create(
                f"OPEN SEAT: {s['course']} #{nbr} ({s['when']}, {s['instructor']})",
                f"@{cfg['notify_user']} {n_open} seat(s) just opened in **{s['course']}**, "
                f"class #{nbr}, {s['when']} with {s['instructor']} ({cfg['term_name']}).\n\n"
                f"Spotted {stamp} (Phoenix time). Enroll fast:\n"
                f"1. Go to https://my.asu.edu and open your shopping cart.\n"
                f"2. Check only #{nbr} and enroll.\n\n"
                f"Or message Claude \"enroll me in #{nbr}\" and it will do it in the browser pane.\n\n"
                f"Once you're in, remove the other {s['course']} sections from classes.json "
                f"so you stop getting alerts for them.",
            )
            print(f"Alert sent for #{nbr}")
        elif n_open <= 0 and nbr in alerts:
            gh.comment_and_close(alerts[nbr], f"Seat filled again as of {stamp}. Closing; "
                                              f"you'll get a new email if it reopens.")
            print(f"Closed alert for #{nbr}")


if __name__ == "__main__":
    main()
