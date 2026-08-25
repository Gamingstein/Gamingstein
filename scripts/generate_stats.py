#!/usr/bin/env python3
"""
Generates three self-contained SVG stat cards (stats / top-languages / streak)
using GitHub's GraphQL API, in the same monochrome + JetBrains Mono style as
the rest of the profile README. No third-party rendering service involved --
this script runs the numbers and draws the SVG itself.

Requires env var GH_TOKEN (a PAT with `read:user` + `public_repo`, or the
default GitHub Actions token) and STATS_USERNAME.
"""
import os, sys, base64, datetime, json, urllib.request
from xml.etree import ElementTree
from xml.sax.saxutils import escape

USERNAME = os.environ.get("STATS_USERNAME", "Gamingstein")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
OUT_DIR = os.environ.get("OUT_DIR", "assets")
FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "fonts")

if not TOKEN:
    sys.exit("Missing GH_TOKEN / GITHUB_TOKEN environment variable")

API_URL = "https://api.github.com/graphql"

# ---------------------------------------------------------------- palette --
BG, BORDER = "#0a0a0a", "#262626"
TEXT_HI, TEXT_MD, TEXT_LO, ACCENT = "#f5f5f5", "#a3a3a3", "#5c5c5c", "#ffffff"


def gql(query, variables=None):
    req = urllib.request.Request(
        API_URL,
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": USERNAME,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


# ---------------------------------------------------------- fetch profile --
PROFILE_Q = """
query($login:String!) {
  user(login:$login) {
    createdAt
    followers { totalCount }
    repositories(first:100, ownerAffiliations:[OWNER], isFork:false, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first:10, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

profile = gql(PROFILE_Q, {"login": USERNAME})["user"]
created_at = datetime.datetime.fromisoformat(profile["createdAt"].replace("Z", "+00:00"))
followers = profile["followers"]["totalCount"]
repos = profile["repositories"]["nodes"]
public_repo_count = profile["repositories"]["totalCount"]
total_stars = sum(r["stargazerCount"] for r in repos)

lang_bytes = {}
for r in repos:
    for edge in r["languages"]["edges"]:
        name = edge["node"]["name"]
        color = edge["node"]["color"] or "#888888"
        lang_bytes[name] = lang_bytes.get(name, [0, color])
        lang_bytes[name][0] += edge["size"]
        lang_bytes[name][1] = color

top_langs = sorted(lang_bytes.items(), key=lambda kv: kv[1][0], reverse=True)[:6]
total_lang_bytes = sum(v[0] for _, v in top_langs) or 1

# --------------------------------------------------- fetch contributions ---
CONTRIB_Q = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      totalCommitContributions
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

now = datetime.datetime.now(datetime.timezone.utc)
all_days = {}
total_commits = 0
year_start = created_at
while year_start < now:
    year_end = min(year_start + datetime.timedelta(days=365), now)
    data = gql(CONTRIB_Q, {
        "login": USERNAME,
        "from": year_start.strftime("%Y-%m-%dT00:00:00Z"),
        "to": year_end.strftime("%Y-%m-%dT23:59:59Z"),
    })["user"]["contributionsCollection"]
    total_commits += data["totalCommitContributions"]
    for week in data["contributionCalendar"]["weeks"]:
        for day in week["contributionDays"]:
            all_days[day["date"]] = day["contributionCount"]
    year_start = year_end

sorted_dates = sorted(all_days.keys())
longest = current = 0
today_str = now.strftime("%Y-%m-%d")
streak = 0
# longest streak across full history
run = 0
for d in sorted_dates:
    if all_days[d] > 0:
        run += 1
        longest = max(longest, run)
    else:
        run = 0
# current streak: walk backwards from today (allow today to be 0 if day not over)
for d in reversed(sorted_dates):
    if d > today_str:
        continue
    if all_days[d] > 0:
        streak += 1
    else:
        if d == today_str:
            continue  # today might just not have activity yet
        break
current = streak

# ============================================================ SVG BUILDER ==
def font_face_block(weights):
    blocks = []
    for w in weights:
        path = os.path.join(FONT_DIR, f"JBM-{w}.woff2")
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        blocks.append(f"""@font-face {{
        font-family: 'JBM{w}';
        src: url(data:font/woff2;base64,{b64}) format('woff2');
      }}""")
    return "\n".join(blocks)


def write_svg(path, content):
    """Write a UTF-8 SVG and parse it immediately to catch malformed output."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    ElementTree.fromstring(content)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def card_shell(
    width,
    height,
    body,
    title="GitHub profile metric",
    description="A self-hosted metric generated from GitHub data.",
    weights=("Regular", "ExtraBold", "Bold"),
):
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="svg-title svg-desc">
  <title id="svg-title">{escape(title)}</title>
  <desc id="svg-desc">{escape(description)}</desc>
  <defs>
    <style>
      {font_face_block(weights)}
      .title {{ font-family:'JBMExtraBold',monospace; font-size:16px; fill:{TEXT_HI}; letter-spacing:1px; }}
      .label {{ font-family:'JBMRegular',monospace; font-size:12px; fill:{TEXT_MD}; }}
      .value {{ font-family:'JBMBold',monospace; font-size:12px; fill:{TEXT_HI}; }}
      .small {{ font-family:'JBMRegular',monospace; font-size:11px; fill:{TEXT_LO}; }}
    </style>
  </defs>
  <rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="10" fill="{BG}" stroke="{BORDER}"/>
  {body}
</svg>"""


# ---- 1. stats.svg --------------------------------------------------------
rows = [
    ("public repos", str(public_repo_count)),
    ("total stars", str(total_stars)),
    ("followers", str(followers)),
    ("commits (all-time)", str(total_commits)),
]
row_svg = ""
for i, (label, value) in enumerate(rows):
    y = 56 + i * 26
    row_svg += f'<text x="24" y="{y}" class="label">{label}</text>'
    row_svg += f'<text x="276" y="{y}" text-anchor="end" class="value">{value}</text>'
stats_body = f'<text x="24" y="30" class="title">STATS</text>{row_svg}'
write_svg(
    os.path.join(OUT_DIR, "stats.svg"),
    card_shell(
        300,
        190,
        stats_body,
        title="GitHub statistics",
        description="Public repositories, total stars, followers, and all-time commits.",
    ),
)

# ---- 2. langs.svg ---------------------------------------------------------
bar_y = 52
lang_rows = ""
for name, (size, color) in top_langs:
    pct = size / total_lang_bytes * 100
    lang_rows += f'<circle cx="30" cy="{bar_y-4}" r="5" fill="{color}"/>'
    lang_rows += f'<text x="44" y="{bar_y}" class="label">{name}</text>'
    lang_rows += f'<text x="276" y="{bar_y}" text-anchor="end" class="small">{pct:.1f}%</text>'
    bar_w = 252
    filled = max(2, bar_w * pct / 100)
    lang_rows += f'<rect x="24" y="{bar_y+6}" width="{bar_w}" height="4" rx="2" fill="{BORDER}"/>'
    lang_rows += f'<rect x="24" y="{bar_y+6}" width="{filled}" height="4" rx="2" fill="{color}"/>'
    bar_y += 30
langs_body = f'<text x="24" y="30" class="title">TOP LANGUAGES</text>{lang_rows}'
write_svg(
    os.path.join(OUT_DIR, "langs.svg"),
    card_shell(
        300,
        bar_y + 10,
        langs_body,
        title="Top programming languages",
        description="The top programming languages by repository size.",
    ),
)

# ---- 3. streak.svg --------------------------------------------------------
streak_body = f"""
  <text x="150" y="34" text-anchor="middle" class="title">STREAK</text>
  <text x="70" y="80" text-anchor="middle" class="value" style="font-size:26px">{current}</text>
  <text x="70" y="100" text-anchor="middle" class="small">current</text>
  <line x1="150" y1="55" x2="150" y2="105" stroke="{BORDER}"/>
  <text x="230" y="80" text-anchor="middle" class="value" style="font-size:26px">{longest}</text>
  <text x="230" y="100" text-anchor="middle" class="small">longest</text>
"""
write_svg(
    os.path.join(OUT_DIR, "streak.svg"),
    card_shell(
        300,
        120,
        streak_body,
        title="GitHub contribution streak",
        description="Current and longest contribution streak.",
    ),
)

print(f"generated stats for {USERNAME}: repos={public_repo_count} stars={total_stars} "
      f"followers={followers} commits={total_commits} streak={current}/{longest}")
