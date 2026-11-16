#!/usr/bin/env python3
"""Convert dialogueText.csv (Ubuntu Dialogue Corpus) into a 2-user WhatsApp chat export."""

import argparse
import csv
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

PROFANITY_RE = re.compile(
    r"\b(?:"
    r"fuck\w*|fck\w*|fuk\w*|motherfuck\w*|"
    r"shit\w*|sh1t\w*|bullshit\w*|horseshit\w*|"
    r"bitch\w*|bastard\w*|asshole\w*|jackass\w*|dumbass\w*|smartass\w*|badass\w*|ass|"
    r"cunt\w*|dick\w*|cock\w*|pussy\w*|prick\w*|twat\w*|"
    r"slut\w*|whore\w*|skank\w*|fag\w*|retard\w*|"
    r"damn\w*|dammit|goddamn\w*|hell|crap\w*|piss\w*|douche\w*|"
    r"wtf|wth|stfu|gtfo|omfg|lmfao|ffs"
    r")\b",
    re.IGNORECASE,
)


def contains_profanity(text: str) -> bool:
    """Return True if text contains profanity or common curse abbreviations."""
    return bool(PROFANITY_RE.search(text))


def parse_iso_timestamp(raw: str) -> datetime:
    """Parse ISO-8601 timestamp from dialogueText.csv."""
    cleaned = raw.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    return datetime.fromisoformat(cleaned)


def format_whatsapp_line(dt: datetime, sender: str, text: str, fmt: str) -> str:
    """Format a single message in iOS or Android WhatsApp export format."""
    safe_sender = sender.replace(":", "_").strip()
    safe_text = text.strip()
    if fmt == "android":
        return f"{dt.strftime('%d/%m/%Y, %H:%M')} - {safe_sender}: {safe_text}"
    return f"[{dt.strftime('%d/%m/%Y, %H:%M:%S')}] {safe_sender}: {safe_text}"


def load_two_user_dialogues(csv_path: Path, filter_profanity: bool = True):
    """Group CSV rows by dialogueID and keep valid 2-user back-and-forth dialogues."""
    dialogues = defaultdict(list)
    with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sender = (row.get("from") or "").strip()
            text = (row.get("text") or "").strip()
            date_str = (row.get("date") or "").strip()
            did = (row.get("dialogueID") or "").strip()
            if not (did and sender and text and date_str):
                continue
            try:
                dt = parse_iso_timestamp(date_str)
            except ValueError:
                continue
            dialogues[did].append((dt, sender, text))

    valid_dialogues = []
    user_dialogue_counts = Counter()
    profane_users = set()

    for did, msgs in dialogues.items():
        for _, sender, text in msgs:
            if contains_profanity(text) or contains_profanity(sender):
                profane_users.add(sender)
        if len(msgs) < 2:
            continue
        msgs.sort(key=lambda m: m[0])
        senders = {m[1] for m in msgs}
        # Require exactly 2 speakers and at least one back-and-forth turn
        if len(senders) != 2:
            continue
        has_switch = any(msgs[i][1] != msgs[i + 1][1] for i in range(len(msgs) - 1))
        if not has_switch:
            continue
        if filter_profanity and any(contains_profanity(m[2]) or contains_profanity(m[1]) for m in msgs):
            continue

        valid_dialogues.append((msgs[0][0], did, senders, msgs))
        for s in senders:
            user_dialogue_counts[s] += 1

    valid_dialogues.sort(key=lambda item: item[0])
    return valid_dialogues, user_dialogue_counts, profane_users


def select_messages(
    valid_dialogues,
    target_user: str,
    partner_name: str,
    limit: int,
):
    """Select complete 2-user dialogues for target_user up to ~limit messages."""
    selected = []
    dialogue_count = 0

    for _, _, senders, msgs in valid_dialogues:
        if target_user not in senders:
            continue
        if selected and len(selected) + len(msgs) > limit:
            # Stop if adding this dialogue moves us further from limit than stopping now
            if abs(limit - len(selected)) <= abs((len(selected) + len(msgs)) - limit):
                break
        for dt, sender, text in msgs:
            mapped_sender = target_user if sender == target_user else partner_name
            selected.append((dt, mapped_sender, text))
        dialogue_count += 1
        if len(selected) >= limit:
            break

    return selected, dialogue_count


def main():
    parser = argparse.ArgumentParser(
        description="Convert dialogueText.csv into a 2-user WhatsApp chat .txt export."
    )
    parser.add_argument(
        "-i", "--input", type=Path, default=Path("dialogueText.csv"),
        help="Path to input CSV file (default: dialogueText.csv)",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("whatsapp_chat.txt"),
        help="Path to output WhatsApp .txt file (default: whatsapp_chat.txt)",
    )
    parser.add_argument(
        "-u", "--target-user", type=str, default=None,
        help="Primary username to extract dialogues for (default: user with most 2-person dialogues)",
    )
    parser.add_argument(
        "-p", "--partner-name", type=str, default="User",
        help="Display name for the second participant (default: User)",
    )
    parser.add_argument(
        "-n", "--limit", type=int, default=2000,
        help="Target number of messages to select (default: 2000)",
    )
    parser.add_argument(
        "-f", "--format", choices=["ios", "android"], default="ios",
        help="WhatsApp export format: ios or android (default: ios)",
    )
    parser.add_argument(
        "--allow-profanity", action="store_true",
        help="Disable the profanity filter (enabled by default)",
    )
    args = parser.parse_args()

    valid_dialogues, user_counts, profane_users = load_two_user_dialogues(
        args.input, filter_profanity=not args.allow_profanity
    )
    if not valid_dialogues:
        raise SystemExit("No valid 2-user back-and-forth dialogues found.")

    if args.target_user:
        target_user = args.target_user
    else:
        clean_users = [(u, c) for u, c in user_counts.most_common() if u not in profane_users]
        target_user = clean_users[0][0] if clean_users else user_counts.most_common(1)[0][0]
    if user_counts[target_user] == 0:
        raise SystemExit(f"No 2-user dialogues found for user: {target_user}")

    messages, dialogue_count = select_messages(
        valid_dialogues, target_user, args.partner_name, args.limit
    )

    lines = [
        format_whatsapp_line(dt, sender, text, args.format)
        for dt, sender, text in messages
    ]
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")

    counts = Counter(sender for _, sender, _ in messages)
    print(f"Target user: {target_user}")
    print(f"Partner name: {args.partner_name}")
    print(f"Selected dialogues: {dialogue_count}")
    print(f"Total messages written: {len(messages)}")
    print(f"Message breakdown: {dict(counts)}")
    print(f"Output written to: {args.output}")


if __name__ == "__main__":
    main()
