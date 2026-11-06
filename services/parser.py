import re
import os
from collections import Counter
import pandas as pd

DATE = r"(?P<date>\d{1,4}[-/.]\d{1,2}(?:[-/.]\d{1,4})?)"
TIME = r"(?P<time>\d{1,2}[.:]\d{2}(?:[.:]\d{2})?(?:\s?[AaPp]\.?\s?[Mm]\.?)?)"

HEADER_PATTERNS = [
    # [10/6/26, 18:32:45] Sender: text
    ("berkurung siku (export iOS / salinan)",
     re.compile(rf"^\[{DATE},?\s+{TIME}\]\s*(?P<rest>.*)$")),
    # 10/6/26, 18.32 - Sender: text
    ("dash (export Android / salinan)",
     re.compile(rf"^{DATE},?\s+{TIME}\s*[-\u2013\u2014]\s*(?P<rest>.*)$")),
    # [18:32] Sender: text
    ("berkurung siku tanpa tanggal",
     re.compile(rf"^\[{TIME}\]\s*(?P<rest>.*)$")),
    # 18:32 - Sender: text
    ("dash tanpa tanggal",
     re.compile(rf"^{TIME}\s*[-\u2013\u2014]\s*(?P<rest>.*)$")),
]

RE_SENDER = re.compile(r"^([^:\n]{1,60}?):\s(.*)$", re.S)

NOISE = [
    r"media (omitted|tidak disertakan)",
    r"(gambar|video|audio|stiker|sticker|gif|dokumen|image|document|kontak|contact card) (omitted|tidak disertakan|dihilangkan)",
    r"pesan ini dihapus",
    r"this message was deleted",
    r"anda menghapus pesan ini",
    r"you deleted this message",
    r"^null$",
    r"menunggu pesan ini",
    r"waiting for this message",
]

MEDIA_RE = re.compile(
    r"(?:<media omitted>|media omitted|image omitted|video omitted|audio omitted|sticker omitted|"
    r"gif omitted|document omitted|contact card omitted|pesan ini dihapus|this message was deleted|"
    r"you deleted this message|media tidak disertakan|(?:gambar|video|audio|stiker|sticker|gif|dokumen|image|document)\s+(?:omitted|tidak disertakan))",
    re.I,
)


def is_noise(t):
    return len(t) < 80 and any(re.search(p, t.lower()) for p in NOISE)


def is_media(t):
    return len(t) < 80 and bool(MEDIA_RE.search(t))


def is_pasted(t, max_len=400, max_words=60):
    t = str(t)
    if len(t.split()) > max_words or len(t) > max_len:
        return True
    if t.count("\n") >= 3 or "```" in t or t.count("**") >= 2:
        return True
    return False


def _norm_time(t):
    t = re.sub(r"\s+", "", (t or "").replace("\u202f", ""))
    m = re.match(r"^(\d{1,2})[.:](\d{2})(?:[.:](\d{2}))?([AaPp]\.?[Mm]\.?)?$", t)
    if not m:
        return ""
    h, mi, sec, ap = int(m.group(1)), m.group(2), m.group(3), m.group(4)
    if ap:
        ap = ap.replace(".", "").lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
    return f"{h:02d}:{mi}" + (f":{sec}" if sec else "")


def _pisah(raw):
    return [int(x) for x in re.split(r"[-/.]", raw) if x.isdigit()]


def _deteksi_urutan(dates):
    f, s = [], []
    for d in dates:
        if not d:
            continue
        p = _pisah(d)
        if len(p) == 3 and p[0] > 99:
            return False, "YYYY-MM-DD"
        if len(p) >= 2:
            f.append(p[0])
            s.append(p[1])
    if f and max(f) > 12:
        return True, "DD/MM"
    if s and max(s) > 12:
        return False, "MM/DD"
    return True, "default DD/MM"


def _ke_iso(raw, time_val, dayfirst, default_year):
    p = _pisah(raw) if raw else [1, 1]
    if len(p) == 3 and p[0] > 99:
        y, mo, d = p
    elif len(p) == 3:
        a, b, y = p
        if y < 100:
            y += 2000 if y < 70 else 1900
        d, mo = (a, b) if dayfirst else (b, a)
    else:
        a, b = (p + [1, 1])[:2]
        d, mo = (a, b) if dayfirst else (b, a)
        y = default_year
    if not (1 <= mo <= 12):
        d, mo = mo, d
    return f"{y:04d}:{mo:02d}:{d:02d}".replace(":", "-") + (f" {time_val}" if time_val else "")


def parse_whatsapp_text(raw_text, default_year=None):
    if not raw_text or not raw_text.strip():
        raise ValueError("Chat file is empty.")

    for ch in ["\u200e", "\u200f", "\ufeff", "\u202f", "\u00a0"]:
        raw_text = raw_text.replace(ch, " " if ch in ["\u202f", "\u00a0"] else "")

    lines = raw_text.splitlines()
    rows, cur = [], None

    for line in lines:
        m, rest = None, None
        for _, pat in HEADER_PATTERNS:
            mm = pat.match(line)
            if mm:
                m, rest = mm, mm.group("rest")
                break
        if m is not None:
            if cur:
                rows.append(cur)
            cur = None
            ms = RE_SENDER.match(rest)
            if not ms:
                continue
            g = m.groupdict()
            cur = {
                "date": g.get("date") or "",
                "time": _norm_time(g.get("time") or ""),
                "sender": ms.group(1).strip(),
                "text": ms.group(2).strip(),
            }
        elif cur is not None:
            cur["text"] += "\n" + line.strip()

    if cur:
        rows.append(cur)

    if not rows:
        # Fallback for plain lines without timestamps
        for line in lines:
            if not line.strip():
                continue
            ms = RE_SENDER.match(line)
            if ms:
                rows.append({
                    "date": "",
                    "time": "",
                    "sender": ms.group(1).strip(),
                    "text": ms.group(2).strip(),
                })

    if not rows:
        raise ValueError("Could not parse any messages from the uploaded file.")

    df = pd.DataFrame(rows)
    if default_year is None:
        default_year = pd.Timestamp.today().year

    dayfirst, _ = _deteksi_urutan(df["date"].tolist())
    stamps = [_ke_iso(r["date"], r["time"], dayfirst, default_year) for _, r in df.iterrows()]
    df["datetime"] = pd.to_datetime(stamps, errors="coerce")
    df["datetime"] = df["datetime"].fillna(pd.Timestamp.today())
    df = df.sort_values("datetime").reset_index(drop=True)

    df["is_media"] = df["text"].apply(is_media)
    media_counts = df[df["is_media"]]["sender"].value_counts().to_dict()
    df = df[~df["is_media"]].reset_index(drop=True)

    df["text"] = (
        df["text"]
        .str.replace(r"\s*<(pesan ini diedit|this message was edited)>", "", regex=True, flags=re.I)
        .str.strip()
    )
    df = df[(df["text"] != "") & (~df["text"].apply(is_noise))].reset_index(drop=True)

    # Calculate participant statistics
    total_msgs = len(df)
    sender_counts = df["sender"].value_counts()
    participants = []
    for sender, count in sender_counts.items():
        sub = df[df["sender"] == sender]
        first_ts = sub["datetime"].min()
        last_ts = sub["datetime"].max()
        participants.append({
            "name": sender,
            "count": int(count),
            "percentage": round(100.0 * count / max(total_msgs, 1), 1),
            "media_count": int(media_counts.get(sender, 0)),
            "first_message": first_ts.strftime("%Y-%m-%d %H:%M") if pd.notna(first_ts) else "",
            "last_message": last_ts.strftime("%Y-%m-%d %H:%M") if pd.notna(last_ts) else "",
        })

    return df, media_counts, participants


def anonymize_messages(df, target_name, char_name="Fossetta", user_aliases=None, char_aliases=None, third_party_names=None):
    df = df.copy()
    user_aliases = set(user_aliases or [])
    char_aliases = set(char_aliases or [])
    third_party_names = set(third_party_names or [])

    target_sender = None
    for s in df["sender"].unique():
        if s.strip().lower() == target_name.strip().lower():
            target_sender = s
            break
    if not target_sender:
        target_sender = target_name

    others = [s for s in df["sender"].unique() if s != target_sender]
    primary_user = others[0] if others else "User"

    # Assign roles
    df["sender"] = df["sender"].apply(lambda s: "TARGET" if s == target_sender else "LAWAN")

    # Name replacement regex rules
    re_url = re.compile(r"(?:https?://|www\.)\S+", re.I)
    re_email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
    re_phone = re.compile(r"(?:\+?62|\b0)[\s-]?8\d{1,3}[\s-]?\d{3,4}[\s-]?\d{2,5}|\b\d{9,}\b")
    re_handle = re.compile(r"(?<![\w.])@[A-Za-z0-9._]{3,30}\b")

    def name_regex(names):
        forms = set()
        for n in names:
            n = (n or "").strip()
            if not n:
                continue
            if n.endswith("*") and len(n) >= 4:
                forms.add(re.escape(n[:-1]) + r"\w*")
            elif len(n) >= 3 and re.search(r"[A-Za-z]", n):
                forms.add(re.escape(n) + re.escape(n[-1]) + r"*(?:chan|kun|san|sama|nya|ku|mu)?")
        forms = sorted(forms, key=len, reverse=True)
        return re.compile(r"(?<!\w)(?:" + "|".join(forms) + r")(?!\w)", re.I) if forms else None

    char_names = {target_sender} | char_aliases
    user_names = set(others) | user_aliases | {primary_user}

    char_rx = name_regex(char_names)
    user_rx = name_regex(user_names)
    third_rx = name_regex(third_party_names)

    def scrub(t):
        t = str(t)
        t = re_url.sub("<URL>", t)
        t = re_email.sub("<EMAIL>", t)
        t = re_phone.sub("<NOMOR>", t)
        t = re_handle.sub("<AKUN>", t)
        if third_rx:
            t = third_rx.sub("<NAMA>", t)
        if user_rx:
            t = user_rx.sub("{{user}}", t)
        if char_rx:
            t = char_rx.sub("{{char}}", t)
        return t

    df["text"] = df["text"].apply(scrub)
    return df, target_sender
