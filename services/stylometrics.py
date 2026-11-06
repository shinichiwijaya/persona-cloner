import re
import statistics
from collections import Counter
import pandas as pd
from services.parser import is_pasted

_EMOJI_CP = (
    "\U0001F000-\U0001F0FF"
    "\U0001F100-\U0001F1FF"
    "\U0001F200-\U0001F2FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2190-\u21FF"
    "\u2300-\u23FF"
    "\u25A0-\u25FF"
    "\u2600-\u27BF"
    "\u2B00-\u2BFF"
    "\u00A9\u00AE\u203C\u2049\u2122\u2139\u20E3"
)
_EMOJI_CHAR = "[" + _EMOJI_CP + "]"
_EMOJI_TAIL = "[\uFE0F\u200D\U0001F3FB-\U0001F3FF]*"
EMOJI_RE = re.compile(_EMOJI_CHAR + _EMOJI_TAIL + "(?:\u200D" + _EMOJI_CHAR + _EMOJI_TAIL + ")*")

EMOTICON_RE = re.compile(
    r"(?:</?3|[;:=8xX][-o*']?[)(\]\[dDpP3{]|[)(\]\[dDpP3][-o*']?[;:=8xX]|[;:]['`]?-?[(\[]|\^[_.]?\^|[Oo0][_.][Oo0]|[Tt][_.][Tt]|;-;|[><][_.]?[<>]|[dD]:|[xX][DdpP]+)(?![0-9A-Za-z])",
    re.I,
)

LAUGH_RE = re.compile(
    r"\b(?:(?:wk){2,}\w*|w[k]{3,}|(?:ha){2,}h?|(?:he){2,}h?|(?:hi){2,}h?|(?:xi){2,}x?|(?:kw){2,}\w*|awok\w*|lol|lmao|rofl)\b",
    re.I,
)
PLACEHOLDER = re.compile(r"<[A-Z_]+>|\{\{(?:user|char)\}\}")

SLANG = {
    "gak", "ga", "nggak", "ngga", "enggak", "engga", "nggk", "yg", "dgn", "dg", "utk", "aja", "aj",
    "banget", "bgt", "bngt", "sih", "deh", "dong", "lah", "kok", "yaudah", "yaudh", "udah", "udh",
    "gpp", "gapapa", "btw", "otw", "gitu", "gini", "gimana", "gmn", "kayak", "kek", "emang", "emg",
    "tuh", "nih", "yah", "yaa", "iya", "iyaa", "oke", "okeh", "sip", "mantap", "anjir", "anjay",
    "njir", "wah", "duh", "hmm", "bro", "bang", "kak", "cuy", "guys", "dah", "kan", "loh", "lho",
    "mah", "tau", "tp", "jd", "krn", "sm", "klo", "kalo", "kalau", "bsk", "besok", "lg", "lagi",
    "pls", "plis", "thx", "makasih", "tengkyu", "mksh", "gk", "dh", "ntar", "jir", "bejir", "pake",
    "tpi", "blm", "brp", "cmn", "sbb", "ngab", "woi", "wey"
}

PRONOUNS = {
    "gue/lu": {"gue", "gw", "gua", "w", "lu", "lo", "loe", "elu", "elo"},
    "aku/kamu": {"aku", "ak", "km", "kamu", "kmu", "kau"},
    "saya/anda": {"saya", "anda"},
}

STOP_ID = {
    "yang", "di", "ke", "dan", "itu", "ini", "yg", "dgn", "untuk", "dari", "ada", "sama", "juga",
    "ya", "nya", "aku", "kamu", "gak", "ga", "aja", "udah", "kan", "mau", "bisa", "apa", "kalo",
    "tapi", "sih"
}

EN_WORDS = {
    "the", "is", "are", "and", "you", "i", "to", "of", "it", "that", "for", "in", "on", "my", "me",
    "we", "this", "with", "what", "so", "just", "can", "not", "but", "if", "have", "do", "how", "why",
    "yes", "no", "thanks", "please", "sorry", "love", "like", "good", "nice", "really", "actually", "anyway"
}

REDUP_RE = re.compile(r"\b([A-Za-z]{2,}?)\s?\1\b", re.I)


def tok(t):
    return re.findall(r"[a-zA-Z']+", PLACEHOLDER.sub(" ", t).lower())


def r2(x, nd=2):
    return None if x is None else round(float(x), nd)


def compute_stats(d, media_count=0, session_gap_hours=6):
    d = d.copy().reset_index(drop=True)
    d["pasted"] = d.text.apply(is_pasted)
    n_pasted = int(((d.sender == "TARGET") & d.pasted).sum())
    d = d[~d.pasted].reset_index(drop=True)

    if len(d) == 0:
        raise ValueError("No valid messages after removing pasted content.")

    d["turn"] = (d.sender != d.sender.shift()).cumsum()
    d["session"] = (d.datetime.diff() > pd.Timedelta(hours=session_gap_hours)).cumsum()

    t_df = d[d.sender == "TARGET"]
    texts = t_df.text.tolist()
    n = len(texts)
    if n == 0:
        raise ValueError("No messages found from TARGET sender.")

    pct = lambda c: r2(100 * c / n, 1)
    clean = [PLACEHOLDER.sub("", t).strip() for t in texts]
    wc = [len(t.split()) for t in texts]
    toks = [w for t in texts for w in tok(t)]
    ntok = max(len(toks), 1)

    emo = [EMOJI_RE.findall(t) for t in texts]
    emo_all = Counter(e for l in emo for e in l)
    emo_msg = [bool(l) for l in emo]

    ect = [EMOTICON_RE.findall(t) for t in texts]
    ect_all = Counter(e.lower() for l in ect for e in l)
    ect_msg = [bool(l) for l in ect]

    express_msg = [a or b for a, b in zip(emo_msg, ect_msg)]
    laugh = [LAUGH_RE.findall(t) for t in texts]
    laugh_all = Counter(x.lower() for l in laugh for x in l)
    redup = [
        m for m in (REDUP_RE.search(LAUGH_RE.sub("", t)) for t in clean)
        if m and len(set(m.group(0).lower().replace(" ", ""))) > 1
    ]
    redup_all = Counter(m.group(0).lower() for m in redup)
    alpha = [t for t in clean if re.search(r"[A-Za-z]", t)]
    first_alpha = [re.search(r"[A-Za-z]", t).group() for t in alpha]
    last_char = [t.rstrip()[-1:] for t in clean if t.strip()]
    tcount = Counter(toks)

    pron = {k: sum(tcount[w] for w in v) for k, v in PRONOUNS.items()}
    ptot = sum(pron.values())
    pron_pct = {k: (r2(100 * v / ptot, 1) if ptot else 0) for k, v in pron.items()}

    turns = d.groupby("turn").agg(
        sender=("sender", "first"),
        session=("session", "first"),
        start=("datetime", "first"),
        end=("datetime", "last"),
        n=("text", "size"),
    )
    ps, pe, pss = turns.sender.shift(), turns.end.shift(), turns.session.shift()
    mask = (turns.sender == "TARGET") & ps.notna() & (ps != "TARGET") & (turns.session == pss)
    lat = ((turns.start[mask] - pe[mask]).dt.total_seconds() / 60).tolist()
    first_in_session = d.groupby("session").sender.first()
    hours = Counter(t_df.datetime.dt.hour)

    sorted_wc = sorted(wc)
    p90_idx = int(0.9 * (n - 1)) if n > 1 else 0

    return {
        "n_pesan_target": n,
        "n_pesan_total": len(d),
        "porsi_target_persen": r2(100 * n / len(d), 1),
        "pesan_tempelan_diabaikan": n_pasted,
        "rentang_tanggal": [str(d.datetime.min().date()), str(d.datetime.max().date())],
        "kata_per_pesan_rata2": r2(statistics.mean(wc) if wc else 0),
        "kata_per_pesan_median": statistics.median(wc) if wc else 0,
        "kata_per_pesan_p90": r2(sorted_wc[p90_idx] if sorted_wc else 0),
        "karakter_per_pesan_rata2": r2(statistics.mean(len(t) for t in texts) if texts else 0, 1),
        "pesan_pendek_le3kata_persen": pct(sum(w <= 3 for w in wc)),
        "bubble_per_giliran_rata2": r2(turns[turns.sender == "TARGET"].n.mean() if not turns.empty else 1),
        "media_per_100_pesan_teks": r2(100 * media_count / n, 1),
        "emoji_per_pesan": r2(sum(len(l) for l in emo) / n, 3),
        "pesan_beremoji_persen": pct(sum(emo_msg)),
        "emoji_teratas": [[e, c] for e, c in emo_all.most_common(5)],
        "emotikon_per_pesan": r2(sum(len(l) for l in ect) / n, 3),
        "pesan_beremotikon_persen": pct(sum(ect_msg)),
        "emotikon_teratas": [[e, c] for e, c in ect_all.most_common(5)],
        "pesan_berekspresi_persen": pct(sum(express_msg)),
        "ekspresi_teratas": [[e, c] for e, c in (emo_all + ect_all).most_common(8)],
        "pesan_tawa_persen": pct(sum(bool(l) for l in laugh)),
        "tawa_teratas": [[w, c] for w, c in laugh_all.most_common(4)],
        "pesan_kata_diulang_persen": pct(len(redup)),
        "kata_diulang_contoh": [w for w, _ in redup_all.most_common(4)],
        "pesan_huruf_kecil_semua_persen": pct(sum(t == t.lower() for t in alpha)),
        "awal_huruf_kecil_persen": r2(100 * sum(c.islower() for c in first_alpha) / max(len(first_alpha), 1), 1),
        "kata_kapital_per_100pesan": r2(
            100 * sum(len([w for w in re.findall(r"[A-Za-z]{3,}", t) if w.isupper()]) for t in clean) / n, 1
        ),
        "pesan_huruf_diperpanjang_persen": pct(sum(bool(re.search(r"([a-zA-Z])\1{2,}", t)) for t in clean)),
        "akhir_titik_persen": r2(100 * sum(c == "." for c in last_char) / max(len(last_char), 1), 1),
        "akhir_tanya_persen": r2(100 * sum(c == "?" for c in last_char) / max(len(last_char), 1), 1),
        "akhir_seru_persen": r2(100 * sum(c == "!" for c in last_char) / max(len(last_char), 1), 1),
        "tanpa_tanda_baca_akhir_persen": r2(
            100 * sum(not re.match(r"[.?!]", c) for c in last_char) / max(len(last_char), 1), 1
        ),
        "pesan_elipsis_persen": pct(sum("..." in t for t in clean)),
        "pesan_mengandung_tanya_persen": pct(sum("?" in t for t in clean)),
        "panggil_lawan_persen": pct(sum("{{user}}" in t for t in texts)),
        "kata_teratas": [[w, c] for w, c in tcount.most_common(60) if w not in STOP_ID and len(w) > 1][:15],
        "slang_teratas": [[w, c] for w, c in Counter({w: tcount[w] for w in SLANG if tcount[w]}).most_common(12)],
        "kata_ganti": pron,
        "kata_ganti_persen": pron_pct,
        "kata_ganti_dominan": (max(pron, key=pron.get) if ptot else "tidak menonjol"),
        "kata_inggris_persen": r2(100 * sum(tcount[w] for w in EN_WORDS) / ntok, 1),
        "pembuka_teratas": [[w, c] for w, c in Counter(next(iter(tok(t)), "") for t in clean).most_common(8) if w],
        "jeda_balas_median_menit": r2(statistics.median(lat)) if lat else None,
        "jeda_balas_p75_menit": r2(sorted(lat)[int(0.75 * (len(lat) - 1))]) if lat else None,
        "balas_kurang_1menit_persen": r2(100 * sum(x < 1 for x in lat) / len(lat), 1) if lat else None,
        "inisiasi_percakapan_persen": r2(100 * (first_in_session == "TARGET").mean(), 1) if not first_in_session.empty else 0,
        "jam_aktif_teratas": [h for h, _ in hours.most_common(3)],
        "pesan_larut_malam_0_4_persen": pct(sum(v for h, v in hours.items() if h < 5)),
    }
