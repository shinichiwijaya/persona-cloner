import json
import random
import re
import pandas as pd
from services.parser import is_pasted
from services.llm import call_llm

SCHEMA = """{
 "big_five": {
  "openness": {"skor": 0, "bukti": ["kutipan pendek"]},
  "conscientiousness": {"skor": 0, "bukti": []},
  "extraversion": {"skor": 0, "bukti": []},
  "agreeableness": {"skor": 0, "bukti": []},
  "neuroticism": {"skor": 0, "bukti": []}
 },
 "dimensi_gaya": {
  "formalitas": {"skor": 0, "bukti": []}, "kehangatan": {"skor": 0, "bukti": []},
  "humor": {"skor": 0, "bukti": []}, "sarkasme": {"skor": 0, "bukti": []},
  "ekspresivitas_emosi": {"skor": 0, "bukti": []}, "ketegasan": {"skor": 0, "bukti": []},
  "rasa_ingin_tahu_bertanya": {"skor": 0, "bukti": []}
 },
 "ringkasan_kepribadian": "3-5 kalimat, sudut pandang orang ketiga",
 "cara_bicara": "3-5 kalimat tentang gaya bicara khas (pilihan kata, nada, kebiasaan)",
 "pola_respon": [{"situasi": "...", "respon_khas": "...", "contoh_kutipan": "..."}],
 "topik_favorit": ["..."],
 "hal_yang_dihindari": ["..."],
 "fakta_personal_aman": ["fakta umum non-sensitif yang jelas disebut TARGET sendiri"],
 "tingkat_keyakinan": "rendah|sedang|tinggi",
 "catatan_keterbatasan": "..."
}"""

TRAIT_DESC = {
    "openness": (
        "cenderung praktis dan konvensional; jarang mengulik topik abstrak atau hal baru",
        "penasaran, suka ide dan topik baru; sering melempar pertanyaan atau gagasan di luar topik utama",
    ),
    "conscientiousness": (
        "spontan dan santai; kadang menunda atau lupa, balasan tidak terlalu terstruktur",
        "teratur dan bisa diandalkan; ingat detail, mengonfirmasi rencana, menepati janji",
    ),
    "extraversion": (
        "pendiam dan hemat kata; menunggu diajak bicara, jarang memulai obrolan",
        "ramai dan energik; sering memulai obrolan, banyak bicara, mudah akrab",
    ),
    "agreeableness": (
        "blak-blakan; tidak sungkan menolak, mengkritik, atau berdebat",
        "hangat dan suportif; menghindari konflik, mudah mengalah, memberi empati",
    ),
    "neuroticism": (
        "tenang dan stabil; jarang mengeluh atau panik",
        "mudah cemas; sering mengeluh, overthinking, ekspresif soal stres",
    ),
}
TRAIT_ID = {
    "openness": "Keterbukaan",
    "conscientiousness": "Kehati-hatian",
    "extraversion": "Ekstraversi",
    "agreeableness": "Keramahan",
    "neuroticism": "Neurotisisme",
}


def sample_dialogue(d, max_chars=60000, seed=42, session_gap_hours=6):
    d = d.copy().reset_index(drop=True)
    d["session"] = (d.datetime.diff() > pd.Timedelta(hours=session_gap_hours)).cumsum()
    sess = [g for _, g in d.groupby("session") if (g.sender == "TARGET").sum() >= 2]
    random.Random(seed).shuffle(sess)
    chosen, total = [], 0
    for g in sess:
        block = "\n".join(
            f"{s}: " + ("[teks tempelan panjang dilewati]" if is_pasted(t) else str(t)[:300])
            for s, t in zip(g.sender, g.text)
        )
        if total + len(block) > max_chars:
            continue
        chosen.append((g.datetime.iloc[0], block))
        total += len(block)
    chosen.sort(key=lambda x: x[0])
    return "\n\n--- percakapan baru ---\n".join(b for _, b in chosen), len(chosen)


def build_extraction_messages(dialogue, stats):
    system = (
        "Kamu analis linguistik forensik dan psikologi kepribadian. Kamu menilai kepribadian seseorang "
        "HANYA dari bukti di chat. Jangan mengarang. Keluaran harus JSON valid saja, tanpa markdown pembuka/penutup."
    )
    user = f"""Di bawah ini cuplikan chat WhatsApp. Pengirim 'TARGET' adalah orang yang dianalisis; 'LAWAN' adalah lawan bicaranya.
Di dalam teks, nama TARGET disensor jadi {{{{char}}}} dan nama lawan bicara jadi {{{{user}}}};
pihak ketiga jadi <NAMA>, nomor telepon jadi <NOMOR>.
Teks tempelan panjang sudah dilewati dan BUKAN gaya TARGET.

ATURAN:
- Skor 0-100 (50 = rata-rata populasi umum). Nilai ekstrem hanya jika bukti kuat.
- 'bukti' = kutipan asli TARGET, maksimal 8 kata per kutipan, 1-3 kutipan per item.
- 'pola_respon': 6-8 item tentang bagaimana TARGET biasa menanggapi situasi (mis. ditanya hal sepele, diajak bertemu,
  dikritik, dicurhati, diajak bercanda, tidak setuju, dipuji, menolak ajakan). Hanya yang terbukti di chat.
- Gunakan angka stilometrik sebagai dasar kuat untuk dimensi gaya.
- Jika tidak ada bukti untuk suatu hal, isi null atau daftar kosong. Jangan menebak fakta pribadi.
- 'fakta_personal_aman' tidak boleh berisi data sensitif (kesehatan, agama, politik, alamat, keuangan).
- Isi 'tingkat_keyakinan' dan 'catatan_keterbatasan' dengan jujur.

ANGKA STILOMETRIK TARGET (hasil hitung kode):
{json.dumps(stats, ensure_ascii=False)}

FORMAT KELUARAN (JSON saja, persis struktur ini):
{SCHEMA}

CUPLIKAN CHAT:
{dialogue}"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_json_loose(text):
    t = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.I)
    t = re.sub(r"\s*```$", "", t, flags=re.I)
    s, e = t.find("{"), t.rfind("}")
    if s == -1 or e == -1:
        raise ValueError("No JSON object structure found in LLM response.")
    json_str = t[s:e + 1]
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
    return json.loads(json_str)


def clean_profile(p):
    for grp in ("big_five", "dimensi_gaya"):
        g = p.get(grp) or {}
        for k, v in list(g.items()):
            v = v if isinstance(v, dict) else {"skor": v, "bukti": []}
            try:
                v["skor"] = max(0, min(100, int(round(float(v.get("skor", 50))))))
            except Exception:
                v["skor"] = 50
            v.setdefault("bukti", [])
            g[k] = v
        p[grp] = g
    return p


def extract_profile(dialogue, stats, llm_config, tries=3):
    msgs = build_extraction_messages(dialogue, stats)
    for i in range(tries):
        out = call_llm(
            messages=msgs,
            api_key=llm_config.get("api_key"),
            model=llm_config.get("model"),
            provider=llm_config.get("provider", "openrouter"),
            base_url=llm_config.get("base_url"),
            temperature=0.2,
            max_tokens=4000,
        )
        try:
            return clean_profile(parse_json_loose(out))
        except Exception:
            if i == tries - 1:
                raise
            msgs += [
                {"role": "assistant", "content": out},
                {
                    "role": "user",
                    "content": "Keluaranmu bukan JSON valid. Kirim ulang HANYA JSON valid sesuai format schema yang diminta, tanpa markdown, tanpa koma menggantung.",
                },
            ]
    raise RuntimeError("Failed to parse valid persona profile JSON from LLM.")


def pick_examples(d, n=12, seed=42, session_gap_hours=6):
    d = d.copy().reset_index(drop=True)
    d["turn"] = (d.sender != d.sender.shift()).cumsum()
    d["session"] = (d.datetime.diff() > pd.Timedelta(hours=session_gap_hours)).cumsum()
    turns = []
    for (_, s, sess), g in d.groupby(["turn", "sender", "session"], sort=False):
        turns.append((s, sess, list(g.text)))
    pairs = []
    for i in range(1, len(turns)):
        ps, psess, ptxt = turns[i - 1]
        s, sess, txt = turns[i]
        if s == "TARGET" and ps != "TARGET" and sess == psess:
            ctx, rep = "\n".join(ptxt[-2:])[:300], txt[:5]
            if (
                0 < len(" ".join(rep)) <= 400
                and not re.search(r"<[A-Z_]+>", ctx + " ".join(rep))
                and not any(is_pasted(x) for x in ptxt[-2:] + txt)
            ):
                pairs.append({"konteks": ctx, "balasan": rep})

    bucket = lambda p: (
        0 if len(" ".join(p["balasan"]).split()) <= 3 else (1 if len(" ".join(p["balasan"]).split()) <= 12 else 2)
    )
    rnd = random.Random(seed)
    groups = [[p for p in pairs if bucket(p) == b] for b in range(3)]
    for g in groups:
        rnd.shuffle(g)
    out, k = [], 0
    while len(out) < n and any(groups):
        if groups[k % 3]:
            out.append(groups[k % 3].pop())
        k += 1
        if k > 10 * n:
            break
    return out


def lvl(s):
    return "rendah" if s <= 35 else ("tinggi" if s >= 65 else "sedang")


def trait_line(k, s, bukti=None):
    lo, hi = TRAIT_DESC[k]
    desc = lo if s <= 35 else (hi if s >= 65 else "tidak menonjol; ikuti konteks percakapan")
    line = f"- {TRAIT_ID[k]} ({lvl(s)}): {desc}"
    if bukti and len(bukti) > 0:
        line += f" (Contoh ekspresi asli: {', '.join(repr(x) for x in bukti)})"
    return line + "."


def style_rules(st):
    lines = []
    if st["kata_per_pesan_rata2"] <= 3:
        lines.append("Pesan biasanya sangat singkat dan langsung ke inti. Sering kali satu bubble hanya berisi satu sampai beberapa kata.")
    elif st["kata_per_pesan_rata2"] <= 6:
        lines.append("Pesan umumnya singkat dan langsung ke inti, tetapi dapat menjadi lebih panjang ketika konteks membutuhkan penjelasan.")
    else:
        lines.append("Pesan cenderung ringkas, tetapi panjangnya dapat berubah mengikuti konteks percakapan.")

    if st["kata_per_pesan_p90"] <= 6:
        lines.append("Sebagian besar balasan tetap pendek; jangan membuat setiap respons menjadi paragraf panjang kecuali memang sedang menjelaskan sesuatu.")

    if st["bubble_per_giliran_rata2"] >= 2:
        lines.append("Sering mengirim beberapa bubble pendek secara berurutan daripada menggabungkan semuanya menjadi satu pesan panjang. Jika ada beberapa pikiran yang muncul berturut-turut, pisahkan menjadi beberapa baris.")

    if st["pesan_huruf_kecil_semua_persen"] >= 70:
        lines.append("Biasanya menggunakan huruf kecil dalam percakapan sehari-hari. Kapitalisasi tidak perlu dibuat formal.")
    elif st["pesan_huruf_kecil_semua_persen"] >= 40:
        lines.append("Sering menggunakan huruf kecil dalam percakapan santai.")

    if st["tanpa_tanda_baca_akhir_persen"] >= 70:
        lines.append("Sering tidak menggunakan tanda baca di akhir pesan. Balasan terasa seperti chat spontan.")
    elif st["tanpa_tanda_baca_akhir_persen"] >= 40:
        lines.append("Tidak selalu menggunakan tanda baca di akhir pesan, terutama dalam percakapan santai.")

    if st["pesan_huruf_diperpanjang_persen"] >= 3:
        lines.append("Kadang memanjangkan huruf untuk mengekspresikan emosi atau penekanan, misalnya 'iyaaa', 'gakkk'.")

    if st["emoji_per_pesan"] < 0.05:
        rare = [e for e, c in st["emoji_teratas"][:3] if c >= 5]
        if rare:
            lines.append(f"Emoji jarang digunakan dan biasanya hanya muncul sesekali. Emoji yang pernah digunakan: {' '.join(rare)}.")
        else:
            lines.append("Emoji sangat jarang digunakan dalam percakapan.")
    else:
        top = [e for e, _ in st["emoji_teratas"][:4]]
        lines.append(f"Emoji dapat digunakan untuk memperkuat ekspresi suasana percakapan: {' '.join(top)}.")

    if st["pesan_tawa_persen"] >= 3:
        tawa = [w for w, _ in st["tawa_teratas"][:5]]
        if tawa:
            lines.append(f"Sering menggunakan tawa tertulis spontan seperti {', '.join(tawa)}.")

    if st["slang_teratas"]:
        slang = [w for w, _ in st["slang_teratas"][:10]]
        lines.append(f"Menggunakan slang dan singkatan dalam percakapan sehari-hari, termasuk: {', '.join(slang)}.")

    pp = st.get("kata_ganti_persen", {})
    mix = [k for k, v in pp.items() if v >= 25]
    if len(mix) >= 2:
        lines.append(f"Bentuk kata ganti yang umum: {', '.join(mix)}.")
    elif mix:
        lines.append(f"Kata ganti yang paling umum digunakan adalah {mix[0]}.")

    if st.get("panggil_lawan_persen", 0) >= 5:
        lines.append("Sesekali menyebut nama atau panggilan lawan bicara ({{user}}) untuk menarik perhatian.")

    if st.get("pesan_kata_diulang_persen", 0) >= 2:
        contoh = [w for w in st["kata_diulang_contoh"][:5]]
        if contoh:
            lines.append(f"Suka mengulang kata tertentu untuk penekanan. Contoh: {', '.join(repr(w) for w in contoh)}.")

    if st.get("kata_inggris_persen", 0) >= 3:
        lines.append("Sering mencampur bahasa Indonesia dengan bahasa Inggris secara spontan.")

    lines.append("Prioritaskan kesan seperti percakapan WhatsApp spontan: ringkas, informal, dan responsif terhadap konteks.")
    return "\n".join("- " + x for x in lines)


def example_block(exs, user="{{user}}", char="{{char}}", with_start=False):
    out = []
    for e in exs:
        blk = f"{user}: {e['konteks']}\n{char}: " + "\n".join(e["balasan"])
        out.append(("<START>\n" if with_start else "") + blk)
    return "\n\n".join(out)


def build_system_prompt(profile, st, exs, include_examples=True):
    big = profile.get("big_five") or {}
    traits = "\n".join(trait_line(k, big[k]["skor"], big[k].get("bukti")) for k in TRAIT_DESC if k in big)

    dims_list = []
    for k, v in (profile.get("dimensi_gaya") or {}).items():
        score = v.get("skor", 50) if isinstance(v, dict) else v
        evidence = v.get("bukti", []) if isinstance(v, dict) else []
        line = f"- {k.replace('_', ' ').title()}: {lvl(score)}"
        if evidence:
            line += f" (Contoh ekspresi: {', '.join(repr(x) for x in evidence)})"
        dims_list.append(line)
    dims = "\n".join(dims_list) if dims_list else "- Tidak ada data dimensi gaya."

    pola_list = []
    for p in (profile.get("pola_respon") or []):
        sit = p.get("situasi", "")
        resp = p.get("respon_khas", "")
        quote = p.get("contoh_kutipan", "")
        line = f"- Saat {sit}: {resp}"
        if quote:
            line += f" (Contoh kutipan asli: {repr(quote)})"
        pola_list.append(line)
    pola = "\n".join(pola_list) if pola_list else "- Tidak ada pola respon khusus."

    fav = ", ".join(profile.get("topik_favorit") or []) or "-"
    avoid = ", ".join(profile.get("hal_yang_dihindari") or []) or "-"
    facts = "\n".join(f"- {f}" for f in (profile.get("fakta_personal_aman") or [])) or "- (tidak ada)"

    p = f"""Kamu adalah {{{{char}}}}, sedang ngobrol lewat WhatsApp dengan {{{{user}}}}. Tirukan kepribadian dan gaya mengetik {{{{char}}}} secara presisi berdasarkan analisis psikologis forensik chat aslinya di bawah ini. Balaslah sebagai {{{{char}}}}, bukan sebagai asisten AI.

## ATURAN UTAMA
- Hanya tulis teks chat murni. Jangan pernah membuat narasi tindakan dalam tanda bintang (*tersenyum*, *menggaruk kepala*).
- Jangan menjelaskan profil psikologis ini kepada {{{{user}}}}, jangan sebutkan skor angka kepribadian.
- Jangan pernah mengarang fakta pribadi baru di luar fakta aman yang terdaftar di bawah.

## PROFIL KEPRIBADIAN
{profile.get('ringkasan_kepribadian') or ''}

Kecenderungan Karakteristik Psikologis (Big Five):
{traits}

Detail Dimensi Gaya:
{dims}

## POLA RESPONS SITUASIONAL (Harus Dipatuhi)
{pola}

## ATURAN CARA BICARA
{profile.get('cara_bicara') or ''}

## GAYA MENGETIK STILOMETRIK (Ritme & Struktur Pesan)
{style_rules(st)}

## BATASAN TOPIK DAN DATA
- Topik Favorit/Sering Dibahas: {fav}
- Topik yang Dihindari/Sensitif: {avoid}
- Fakta Personal Aman yang Valid:
{facts}"""

    if include_examples and exs:
        p += "\n\n## CONTOH SEGMEN BALASAN ASLI\n" + example_block(exs)
    return p


def build_character_card(char_name, profile, stats, examples):
    opener = stats["pembuka_teratas"][0][0] if stats.get("pembuka_teratas") else "halo"
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": char_name,
            "description": build_system_prompt(profile, stats, examples, include_examples=False),
            "personality": profile.get("ringkasan_kepribadian") or "",
            "scenario": "Ngobrol santai lewat WhatsApp.",
            "first_mes": opener,
            "mes_example": example_block(examples, with_start=True),
            "creator_notes": "Dihasilkan otomatis dari analisis chat WhatsApp via Persona Cloner.",
            "system_prompt": "",
            "post_history_instructions": "",
            "alternate_greetings": [],
            "tags": ["persona-cloning", "whatsapp"],
            "creator": "Persona-Cloner-Web",
            "character_version": "1.0",
            "extensions": {},
        },
    }
