#!/usr/bin/env python3
"""Draw a contribution activity graph and a streak card as SVGs.

Reads the profile owner's public contribution calendar from the GitHub GraphQL
API (private contributions are included only as counts, and only if
"Include private contributions on my profile" is turned on), then writes:

  <outdir>/activity.svg  - area chart of the last 31 days
  <outdir>/stats.svg     - total contributions, current streak, longest streak

Usage: GITHUB_TOKEN=... python3 stats.py <github-username> <outdir>
Uses only the Python standard library.
"""
import datetime as dt
import json
import os
import sys
import urllib.request

ACCENT = "#22D3EE"
BG = "#0D1117"
BORDER = "#30363D"
TEXT = "#C9D1D9"
MUTED = "#8B949E"
FONT = "'Segoe UI',Helvetica,Arial,sans-serif"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch_calendar(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise SystemExit(f"GitHub API error: {data['errors']}")
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [
        (dt.date.fromisoformat(d["date"]), d["contributionCount"])
        for w in cal["weeks"]
        for d in w["contributionDays"]
    ]
    days.sort()
    return cal["totalContributions"], days


def streaks(days):
    """Return (current, current_start, current_end, longest, longest_start, longest_end)."""
    longest = run = 0
    l_start = l_end = r_start = None
    for date, count in days:
        if count > 0:
            if run == 0:
                r_start = date
            run += 1
            if run > longest:
                longest, l_start, l_end = run, r_start, date
        else:
            run = 0

    # Current streak counts back from today; a quiet "today" doesn't break it yet.
    current = 0
    c_start = c_end = None
    seq = list(days)
    if seq and seq[-1][1] == 0:
        seq = seq[:-1]
    for date, count in reversed(seq):
        if count == 0:
            break
        current += 1
        c_start = date
        c_end = c_end or date
    return current, c_start, c_end, longest, l_start, l_end


def fmt(d):
    return d.strftime("%b %-d") if d else ""


def date_range(a, b):
    if not a:
        return "No streak yet"
    return fmt(a) if a == b else f"{fmt(a)} – {fmt(b)}"


def activity_svg(days):
    last = days[-31:]
    W, H = 1000, 300
    left, right, top, bottom = 50, 20, 50, 40
    pw, ph = W - left - right, H - top - bottom
    peak = max([c for _, c in last] + [4])
    step = max(1, -(-peak // 4))  # ceil(peak / 4)
    ymax = step * 4

    def x(i):
        return left + pw * i / (len(last) - 1)

    def y(c):
        return top + ph - ph * c / ymax

    pts = [(x(i), y(c)) for i, (_, c) in enumerate(last)]
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = f"{left},{top + ph} " + line + f" {left + pw},{top + ph}"

    grid = []
    for k in range(5):
        v = step * k
        gy = y(v)
        grid.append(
            f'<line x1="{left}" y1="{gy:.1f}" x2="{left + pw}" y2="{gy:.1f}" stroke="{BORDER}" stroke-dasharray="3 4"/>'
            f'<text x="{left - 10}" y="{gy + 4:.1f}" text-anchor="end" fill="{MUTED}" font-size="12">{v}</text>'
        )
    labels = []
    for i, (date, _) in enumerate(last):
        if i % 3 == 0 or i == len(last) - 1:
            labels.append(
                f'<text x="{x(i):.1f}" y="{H - 14}" text-anchor="middle" fill="{MUTED}" font-size="12">{date.day}</text>'
            )
    dots = "".join(
        f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="#FFFFFF" stroke="{ACCENT}" stroke-width="2"/>'
        for px, py in pts
    )
    title = f"Contributions · {fmt(last[0][0])} – {fmt(last[-1][0])}"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">
  <defs>
    <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{ACCENT}" stop-opacity=".45"/>
      <stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/>
    </linearGradient>
    <style>
      .line {{ stroke-dasharray: 3000; stroke-dashoffset: 3000; animation: draw 2.2s ease-out forwards; }}
      .area, .dots {{ opacity: 0; animation: show .8s ease-out 1.4s forwards; }}
      @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
      @keyframes show {{ to {{ opacity: 1; }} }}
    </style>
  </defs>
  <rect width="{W}" height="{H}" rx="12" fill="{BG}"/>
  <text x="{W / 2}" y="30" text-anchor="middle" fill="{ACCENT}" font-size="17" font-weight="600">{title}</text>
  {"".join(grid)}
  <polygon class="area" points="{area}" fill="url(#fill)"/>
  <polyline class="line" points="{line}" fill="none" stroke="{ACCENT}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
  <g class="dots">{dots}</g>
  {"".join(labels)}
</svg>
'''


def stats_svg(total, s):
    current, c_start, c_end, longest, l_start, l_end = s
    W, H = 600, 200
    cols = [
        (f"{total:,}", "Total contributions", "Past year", TEXT),
        (str(current), "Current streak", date_range(c_start, c_end), ACCENT),
        (str(longest), "Longest streak", date_range(l_start, l_end), TEXT),
    ]
    parts = []
    for i, (num, label, sub, color) in enumerate(cols):
        cx = W * (2 * i + 1) / 6
        if i == 1:
            parts.append(
                f'<circle cx="{cx}" cy="78" r="40" fill="none" stroke="{ACCENT}" stroke-width="5"/>'
                f'<rect x="{cx - 14}" y="22" width="28" height="30" fill="{BG}"/>'
                f'<path transform="translate({cx} 38)" fill="#F97316" '
                f'd="M0,-14 C6,-7 10,0 7,7 C5,12 -5,12 -7,7 C-10,0 -5,-4 0,-14 Z"/>'
                f'<path transform="translate({cx} 41)" fill="#FDBA74" '
                f'd="M0,-6 C3,-2 4,2 3,4 C2,6 -2,6 -3,4 C-4,2 -2,0 0,-6 Z"/>'
            )
        parts.append(
            f'<text class="pop" x="{cx}" y="90" text-anchor="middle" fill="{color}" font-size="30" font-weight="700">{num}</text>'
            f'<text x="{cx}" y="150" text-anchor="middle" fill="{color}" font-size="15" font-weight="600">{label}</text>'
            f'<text x="{cx}" y="174" text-anchor="middle" fill="{MUTED}" font-size="12">{sub}</text>'
        )
    seps = "".join(
        f'<line x1="{W * k / 3}" y1="30" x2="{W * k / 3}" y2="170" stroke="{BORDER}"/>' for k in (1, 2)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">
  <style>
    .pop {{ opacity: 0; animation: pop .6s ease-out .2s forwards; }}
    @keyframes pop {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
  </style>
  <rect width="{W}" height="{H}" rx="12" fill="{BG}"/>
  {seps}
  {"".join(parts)}
</svg>
'''


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: stats.py <github-username> <outdir>")
    login, outdir = sys.argv[1], sys.argv[2]
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is not set")
    total, days = fetch_calendar(login, token)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "activity.svg"), "w", encoding="utf-8") as f:
        f.write(activity_svg(days))
    with open(os.path.join(outdir, "stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_svg(total, streaks(days)))
    print(f"Wrote activity.svg and stats.svg for {login} ({total} contributions)")


if __name__ == "__main__":
    main()
