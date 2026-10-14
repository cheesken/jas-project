"""
Build the labelled benchmark corpus as real files.

    python -m benchmark.corpus --out /tmp/bench --size 500

Writes notes/*.txt, emails/*.txt, docs/*.pdf and browser/History (a Chrome
history SQLite file), plus qrels.json with the graded relevance labels and
manifest.json describing every document. Generation is seeded, so the same size
always produces the same corpus.

Document ids: the file's path relative to the corpus root for files, and
"history:<url>" for browser visits (one History file holds many visits).

Composition at the default size of 500:
- 200 relevant documents from the 50 scenarios (see scenarios.py): per query an
  answer (relevance 2), a hand-written related document (1) and two generated
  mentions of its topic (1).
- 300 distractors on similar everyday themes (other restaurants, other
  appointments, other bills). A distractor containing any scenario's guard word
  is regenerated, so distractors are never relevant to a query.
Type mix overall: 30% notes, 20% emails, 20% PDFs, 30% browser history.
"""
import argparse
import json
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from urllib.parse import quote_plus, urlsplit

from benchmark.scenarios import SCENARIOS

TYPE_SHARE = {"note": 0.30, "email": 0.20, "pdf": 0.20, "history": 0.30}
WEBKIT_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
BASE_TIME = datetime(2026, 9, 30, 18, 0, tzinfo=timezone.utc)
ME = "Jahnavi Kedia <jahnavi@example.com>"

GUARD_WORDS = sorted({g for s in SCENARIOS for g in s["guards"]})
_GUARD_RE = re.compile(r"(?<![\w&'-])(" + "|".join(re.escape(g) for g in GUARD_WORDS) + r")(?![\w&'-])", re.I)


def has_guard_word(text: str) -> bool:
    return bool(_GUARD_RE.search(text))


# ---------------------------------------------------------------- generated mentions

def _mention(scenario: dict, doc_type: str, n: int) -> dict:
    topic = scenario["topic"]
    slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")
    if doc_type == "note":
        templates = [
            f"To-do: follow up on the {topic}. Keep the details somewhere easy to find.",
            f"Don't forget about the {topic} this week. Add it to the calendar.",
            f"Note to self: sort out everything for the {topic} before the weekend.",
        ]
        return {"type": "note", "name": f"todo_{slug}", "text": templates[n % len(templates)]}
    if doc_type == "email":
        return {"type": "email", "name": f"reminder_{slug}", "sender": "Reminders <reminders@calendar.example>",
                "subject": f"Reminder: {topic}",
                "text": f"This is your reminder about the {topic}. Open the original message or your notes for the details."}
    return {"type": "history", "title": f"{topic} - Google Search",
            "url": f"https://www.google.com/search?q={quote_plus(topic)}"}


# ---------------------------------------------------------------- distractors

PEOPLE = ["Kevin Nguyen", "Maria Lopez", "Daniel Kim", "Sofia Rossi", "Omar Haddad", "Grace Liu", "Ben Carter",
          "Nina Petrov", "Lucas Silva", "Hannah Weber", "Yuki Tanaka", "Isabel Cruz", "Ethan Brooks", "Leila Ahmadi",
          "Marco Bianchi", "Chloe Martin", "Meera Nair", "Kabir Singh", "Divya Iyer", "Felix Wagner", "Zara Khan",
          "Owen Park", "Priyanka Rao", "Samuel Okafor"]
FIRST = [p.split()[0] for p in PEOPLE]
RESTAURANTS = ["Sushi Ran", "Tacos Arandas", "Pizzeria Delfina", "Zareen's", "Ramen Nagi", "Tartine Bakery",
               "Burma Superstar", "Kunjip", "Din Tai Fung", "Ettan", "Rangoli", "Oren's Hummus", "Kin Khao",
               "Bun Bo Hue An Nam", "La Taqueria", "Cafe Borrone", "Ike's Sandwiches", "Saravana Bhavan"]
DISHES = ["spicy miso ramen", "al pastor tacos", "margherita pizza", "chicken kebab", "soup dumplings",
          "tea leaf salad", "masala dosa", "shakshuka", "pad see ew", "banh mi", "croissants", "falafel plate"]
CITIES = ["Oakland", "Berkeley", "Sausalito", "Redwood City", "Milpitas", "Los Gatos", "Campbell", "Saratoga",
          "Half Moon Bay", "Palo Alto", "Menlo Park", "Cupertino", "San Mateo", "Walnut Creek", "Livermore"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
PROJECTS = ["the capstone poster", "the data viz assignment", "the CMPE 272 group project", "the volunteering fair",
            "the club newsletter", "the research survey", "the cloud lab", "the ML homework"]
CHORES = ["do laundry", "buy detergent", "clean the fridge", "return the moving boxes", "water the balcony herbs",
          "vacuum the living room", "take out recycling", "fix the squeaky door", "pick up dry cleaning"]
COMPANIES = ["Comcast", "Costco", "Target", "Best Buy", "Uber Eats", "DoorDash", "Lyft", "Instacart", "Etsy",
             "Uniqlo", "REI", "Walgreens", "Home Depot", "Spotify", "Duolingo", "Coursera", "Airbnb", "Expedia"]
PRODUCTS = ["USB-C hub", "desk lamp", "running shoes", "rice cooker", "yoga mat bag", "phone case", "air fryer",
            "standing desk converter", "mechanical keyboard", "water bottle", "backpack", "monitor arm",
            "electric kettle", "noise machine", "throw blanket", "wireless mouse"]
TOPICS = ["photosynthesis", "the French Revolution", "black holes", "the Treaty of Versailles", "machine translation",
          "coral reefs", "the Roman Empire", "plate tectonics", "game theory", "the Silk Road", "quantum computing",
          "the Great Barrier Reef", "Byzantine art", "volcanoes", "the printing press", "honeybees", "sourdough starters",
          "the Apollo program", "bird migration", "renewable energy", "the Mars rovers", "jazz history"]
HOBBIES = ["watercolor painting", "rock climbing", "chess openings", "bread baking", "guitar chords", "birdwatching",
           "film photography", "pickleball", "knitting", "salsa dancing", "bouldering", "origami"]
SITES = [("wikipedia.org", "{t} - Wikipedia"), ("youtube.com", "{t} explained - YouTube"),
         ("medium.com", "Understanding {t} | Medium"), ("reddit.com", "r/AskScience: questions about {t}"),
         ("nytimes.com", "What {t} can teach us - The New York Times"), ("bbc.com", "{t}: a short history - BBC")]


def _date(rng: random.Random) -> str:
    return f"{rng.choice(MONTHS)} {rng.randint(1, 28)}"


def _distractor(doc_type: str, rng: random.Random, i: int) -> dict:
    p, p2 = rng.sample(PEOPLE, 2)
    f = rng.choice(FIRST)
    if doc_type == "note":
        kind = rng.randrange(7)
        if kind == 0:
            text = f"{f} recommended {rng.choice(RESTAURANTS)} in {rng.choice(CITIES)}. Try the {rng.choice(DISHES)}, it's apparently worth the wait."
        elif kind == 1:
            text = f"Meeting notes with {p}: discussed {rng.choice(PROJECTS)} timeline. Next check-in on {rng.choice(DAYS)}. {p2.split()[0]} will send the draft."
        elif kind == 2:
            a, b = rng.sample(CHORES, 2)
            text = f"To-do this week: {a}, {b}, and call {f} about {rng.choice(PROJECTS)}."
        elif kind == 3:
            text = f"Workout log: {rng.randint(20, 60)} minute run around the park, {rng.randint(10, 40)} push-ups, stretched for {rng.randint(5, 15)} minutes."
        elif kind == 4:
            text = f"Idea for {rng.choice(PROJECTS)}: interview {rng.randint(5, 15)} students about {rng.choice(HOBBIES)} and make a short video."
        elif kind == 5:
            text = f"Haircut appointment at the salon in {rng.choice(CITIES)} on {_date(rng)} at {rng.randint(9, 17)}:{rng.choice(['00', '30'])}. Ask {f} for the stylist's name."
        else:
            text = f"Learning {rng.choice(HOBBIES)}: practiced for {rng.randint(15, 90)} minutes. {f} suggested a beginner class in {rng.choice(CITIES)}."
        return {"type": "note", "name": f"note_{i:04d}", "text": text}

    if doc_type == "email":
        company = rng.choice(COMPANIES)
        kind = rng.randrange(5)
        num = rng.randint(100000, 999999)
        if kind == 0:
            subject = f"Your {company} order #{num} has shipped"
            text = f"Good news! Your {rng.choice(PRODUCTS)} is on the way and should arrive by {rng.choice(DAYS)}. Track your package in the app."
        elif kind == 1:
            subject = f"Invoice {num} from {company}"
            text = f"Your {company} invoice for ${rng.randint(12, 240)}.{rng.randint(10, 99)} is ready. It will be charged to your card on {_date(rng)}."
        elif kind == 2:
            subject = f"{p} shared a document with you"
            text = f"{p} invited you to edit a document for {rng.choice(PROJECTS)}. Comments are due by {rng.choice(DAYS)}."
        elif kind == 3:
            subject = f"This week at {company}: deals you'll love"
            text = f"Save up to {rng.randint(10, 50)}% on {rng.choice(PRODUCTS)}s and more. Offer ends {_date(rng)}."
        else:
            subject = f"Re: {rng.choice(PROJECTS)}"
            text = f"Hi! Thanks for the update. I'll review the slides tonight and we can meet {rng.choice(DAYS)} after class. - {p2}"
        sender = f"{company} <updates@{company.lower().replace(' ', '')}.example>" if kind in (0, 1, 3) else f"{p} <{p.split()[0].lower()}@example.com>"
        return {"type": "email", "name": f"email_{i:04d}", "sender": sender, "subject": subject, "text": text}

    if doc_type == "pdf":
        kind = rng.randrange(4)
        company = rng.choice(COMPANIES)
        if kind == 0:
            items = rng.sample(PRODUCTS, 3)
            text = (f"{company} Receipt. Order number {rng.randint(10000000, 99999999)}. Date {_date(rng)}, 2026. "
                    + " ".join(f"{it}: ${rng.randint(8, 120)}.{rng.randint(10, 99)}." for it in items)
                    + f" Subtotal and tax included. Paid with card ending {rng.randint(1000, 9999)}. Returns accepted within 30 days.")
        elif kind == 1:
            t = rng.choice(TOPICS)
            text = (f"Lecture notes on {t}. Key ideas: definitions and historical context of {t}. "
                    f"Section 1 introduces the main concepts. Section 2 covers examples discussed in class on {rng.choice(DAYS)}. "
                    f"Section 3 lists open questions for the discussion board. Reading: chapter {rng.randint(2, 12)} of the course textbook.")
        elif kind == 2:
            t = rng.choice(TOPICS)
            text = (f"Article: a beginner's guide to {t}. Researchers have studied {t} for decades. "
                    f"This overview summarizes what is known, what remains debated, and where to read more. "
                    f"Written by {p} for the campus science magazine, issue {rng.randint(1, 40)}.")
        else:
            text = (f"{company} Membership Terms. Member since {_date(rng)}, 2024. Annual fee ${rng.randint(20, 130)}. "
                    f"Benefits include member pricing and free shipping on eligible orders. "
                    f"Contact support for questions about your account number {rng.randint(100000, 999999)}.")
        return {"type": "pdf", "name": f"doc_{i:04d}", "text": text}

    # history
    kind = rng.randrange(4)
    if kind == 0:
        t = rng.choice(TOPICS + HOBBIES)
        domain, pattern = rng.choice(SITES)
        title = pattern.format(t=t[0].upper() + t[1:])
        url = f"https://www.{domain}/{quote_plus(t)}-{i}"
    elif kind == 1:
        prod = rng.choice(PRODUCTS)
        company = rng.choice(["Best Buy", "Target", "REI", "Costco", "Home Depot"])
        title = f"{prod.title()} {rng.choice(['Pro', 'Plus', 'Mini', 'Max', '2'])} | {company}"
        url = f"https://www.{company.lower().replace(' ', '')}.com/p/{quote_plus(prod)}-{i}"
    elif kind == 2:
        r = rng.choice(RESTAURANTS)
        city = rng.choice(CITIES)
        title = f"{r} - {city} - Menu and Reviews - Yelp"
        url = f"https://www.yelp.com/biz/{quote_plus(r.lower())}-{quote_plus(city.lower())}-{i}"
    else:
        q = f"{rng.choice(['best', 'cheap', 'easy', 'how to', 'top 10'])} {rng.choice(HOBBIES + TOPICS)} {rng.choice(['near me', 'for beginners', 'ideas', 'guide', '2026'])}"
        title = f"{q} - Google Search"
        url = f"https://www.google.com/search?q={quote_plus(q)}&n={i}"
    return {"type": "history", "title": title, "url": url}


# ---------------------------------------------------------------- assembly

def doc_id(doc: dict) -> str:
    if doc["type"] == "history":
        return f"history:{doc['url']}"
    folder, ext = {"note": ("notes", "txt"), "email": ("emails", "txt"), "pdf": ("docs", "pdf")}[doc["type"]]
    return f"{folder}/{doc['name']}.{ext}"


def _page_key(d: dict) -> tuple:
    return urlsplit(d["url"]).netloc, " ".join(d["title"].lower().split())


def build_documents(size: int = 500, seed: int = 295) -> (List[dict], Dict[str, Dict[str, int]]):
    rng = random.Random(seed)
    docs: List[dict] = []
    qrels: Dict[str, Dict[str, int]] = {}
    for n, s in enumerate(SCENARIOS):
        mention_types = [t for t in ("note", "email", "history") if t not in (s["answer"]["type"], s["related"]["type"])]
        while len(mention_types) < 2:
            mention_types.append("note" if "note" not in mention_types else "email")
        mentions = [_mention(s, t, n) for t in mention_types[:2]]
        labelled = [(s["answer"], 2), (s["related"], 1)] + [(m, 1) for m in mentions]
        qrels[s["id"]] = {}
        for d, grade in labelled:
            docs.append(d)
            qrels[s["id"]][doc_id(d)] = grade

    if size < len(docs):
        raise ValueError(f"size must be at least {len(docs)} (the labelled documents)")
    have = {t: sum(d["type"] == t for d in docs) for t in TYPE_SHARE}
    want = {t: round(size * share) for t, share in TYPE_SHARE.items()}
    want["history"] += size - sum(want.values())
    seen_ids = {doc_id(d) for d in docs}
    # The history parser merges visits that share a site and title, so a
    # duplicate would be indexed once but counted twice.
    seen_pages = {_page_key(d) for d in docs if d["type"] == "history"}
    i = 0
    for t in TYPE_SHARE:
        need = max(0, want[t] - have[t])
        made = 0
        while made < need:
            i += 1
            d = _distractor(t, rng, i)
            text = " ".join(str(d.get(k, "")) for k in ("text", "subject", "title", "url"))
            if has_guard_word(text) or doc_id(d) in seen_ids:
                continue
            if d["type"] == "history":
                if _page_key(d) in seen_pages:
                    continue
                seen_pages.add(_page_key(d))
            seen_ids.add(doc_id(d))
            docs.append(d)
            made += 1
    return docs, qrels


# ---------------------------------------------------------------- writing files

def _write_pdf(path: str, text: str) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(path, pagesize=letter)
    y = 740
    line = ""
    for word in text.split():
        if len(line) + len(word) + 1 > 90:
            c.drawString(60, y, line)
            y -= 16
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        c.drawString(60, y, line)
    c.save()


def _write_history(path: str, visits: List[dict]) -> None:
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE urls (id INTEGER PRIMARY KEY AUTOINCREMENT, url LONGVARCHAR, title LONGVARCHAR,
                    visit_count INTEGER DEFAULT 0 NOT NULL, typed_count INTEGER DEFAULT 0 NOT NULL,
                    last_visit_time INTEGER NOT NULL, hidden INTEGER DEFAULT 0 NOT NULL)""")
    rows = []
    for n, v in enumerate(visits):
        when = BASE_TIME - timedelta(hours=7 * n + 1)
        rows.append((v["url"], v["title"], 1 + n % 5, int((when - WEBKIT_EPOCH).total_seconds() * 1_000_000)))
    conn.executemany("INSERT INTO urls (url, title, visit_count, last_visit_time) VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


def write_corpus(out_dir: str, size: int = 500, seed: int = 295) -> dict:
    docs, qrels = build_documents(size, seed)
    for folder in ("notes", "emails", "docs", "browser"):
        os.makedirs(os.path.join(out_dir, folder), exist_ok=True)
    visits = []
    for n, d in enumerate(docs):
        if d["type"] == "history":
            visits.append(d)
            continue
        path = os.path.join(out_dir, doc_id(d))
        if d["type"] == "note":
            with open(path, "w", encoding="utf-8") as f:
                f.write(d["text"] + "\n")
        elif d["type"] == "email":
            date = (BASE_TIME - timedelta(days=n % 90)).strftime("%a, %d %b %Y %H:%M")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"From: {d['sender']}\nTo: {ME}\nDate: {date}\nSubject: {d['subject']}\n\n{d['text']}\n")
        else:
            _write_pdf(path, d["text"])
    history_path = os.path.join(out_dir, "browser", "History")
    if os.path.exists(history_path):
        os.remove(history_path)
    _write_history(history_path, visits)

    manifest = {"size": len(docs), "seed": seed,
                "counts": {t: sum(d["type"] == t for d in docs) for t in TYPE_SHARE},
                "docs": [{"id": doc_id(d), "type": d["type"]} for d in docs]}
    with open(os.path.join(out_dir, "qrels.json"), "w") as f:
        json.dump(qrels, f, indent=1)
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=500)
    ap.add_argument("--seed", type=int, default=295)
    args = ap.parse_args()
    m = write_corpus(args.out, args.size, args.seed)
    print(f"Wrote {m['size']} documents to {args.out}: {m['counts']}")


if __name__ == "__main__":
    main()
