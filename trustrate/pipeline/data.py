"""Real, attributed review text with explicitly synthetic behavior metadata."""
from __future__ import annotations

import hashlib
import io
import json
import random
import re
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

DATASET_URL = "https://archive.ics.uci.edu/dataset/331/sentiment+labelled+sentences"
ARCHIVE_URL = "https://archive.ics.uci.edu/static/public/331/sentiment+labelled+sentences.zip"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0"
CANONICAL_KEYS = (
    "id", "product_id", "user_id", "ip_hash", "ip_prefix", "user_agent",
    "created_at", "account_created", "rating", "body", "revision", "scenario",
    "true_label", "split",
)


def text_group(text):
    normalized = re.sub(r"\s+", " ", text.strip().casefold())
    return hashlib.sha256(normalized.encode()).hexdigest()


def download_public(directory="data"):
    """Download/cache the official archive; retain license evidence and hashes."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "sentiment-labelled-sentences.zip"
    page_path = directory / "uci-331.html"
    if not archive.exists():
        archive.write_bytes(urllib.request.urlopen(ARCHIVE_URL, timeout=60).read())
    if not page_path.exists():
        page_path.write_bytes(urllib.request.urlopen(DATASET_URL, timeout=60).read())
    page = page_path.read_text(encoding="utf8")
    if LICENSE_URL not in page or "CC BY 4.0" not in page:
        raise ValueError("Official dataset page did not confirm CC BY 4.0")
    raw = archive.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = next(n for n in zf.namelist() if n.endswith("/amazon_cells_labelled.txt") and not n.startswith("__MACOSX"))
        amazon = zf.read(name)
    records = []
    for index, line in enumerate(amazon.decode("utf8").splitlines()):
        body, sentiment = line.rsplit("\t", 1)
        records.append({"body": body, "sentiment": int(sentiment), "source_row": index + 1,
                        "source_group": text_group(body)})
    if len(records) != 1000 or any(r["sentiment"] not in (0, 1) for r in records):
        raise ValueError("Unexpected Amazon subset; expected 1000 binary sentiment rows")
    provenance = {
        "dataset": "UCI Sentiment Labelled Sentences (331), Amazon subset",
        "citation": "Kotzias, D. (2015). Sentiment Labelled Sentences. UCI. DOI:10.24432/C57604",
        "source_url": DATASET_URL, "archive_url": ARCHIVE_URL,
        "license": "CC BY 4.0", "license_url": LICENSE_URL,
        "license_evidence": "Official dataset page explicitly states CC BY 4.0",
        "archive_sha256": hashlib.sha256(raw).hexdigest(),
        "license_page_sha256": hashlib.sha256(page_path.read_bytes()).hexdigest(),
        "amazon_sha256": hashlib.sha256(amazon).hexdigest(), "source_rows": len(records),
        "retrieved_at": datetime.fromtimestamp(archive.stat().st_mtime, timezone.utc).isoformat(),
        "label_warning": "Sentiment labels are NOT fraud labels. Behavior metadata and true_label are synthetic.",
    }
    (directory / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return records, provenance


def make_dataset(sources, seed=42):
    """1,800 baseline genuine rows plus traps and four attack mechanisms per split.

    Source text groups are assigned once before metadata is generated. Reuse is
    intentional and confined to one split. Campaign text pools are split-local;
    there are no appended attack phrases or shared attack templates.
    """
    rng = random.Random(seed)
    groups = {}
    for source in sources:
        groups.setdefault(source["source_group"], source)
    pool = list(groups.values())
    rng.shuffle(pool)
    cuts = (0, int(.6 * len(pool)), int(.8 * len(pool)), len(pool))
    rows = []
    start = 1704067200.0
    for split_index, (split, count) in enumerate(zip(("train", "validation", "test"), (1080, 360, 360))):
        local = pool[cuts[split_index]:cuts[split_index + 1]]
        if len(local) < 20:
            raise ValueError("Not enough independent source groups")
        genuine_sources, attack_sources = local[:-12], local[-12:]
        duration = count * 1200
        serial = 0

        def add(source, t, scenario="G", label=0, **overrides):
            nonlocal serial
            serial += 1
            user = f"{split}-user-{serial}"
            ip = f"{split}-network-{rng.randrange(100)}"
            row = dict(
                id=f"{split}-{serial:05d}", product_id=f"product-{rng.randrange(8)}",
                user_id=user, ip_hash=hashlib.sha256(ip.encode()).hexdigest(),
                ip_prefix=f"synthetic:{split}:{rng.randrange(20)}",
                user_agent=rng.choice(["Chrome/120", "Chrome/120", "Safari/17", "Firefox/121"]),
                created_at=float(t), account_created=float(t - rng.randint(7, 1000) * 86400),
                rating=rng.choice([4, 5]) if source["sentiment"] else rng.choice([1, 2, 3]),
                body=source["body"], revision=1, scenario=scenario, true_label=label,
                split=split, source_group=source["source_group"], source_row=source["source_row"],
                source_sentiment=source["sentiment"], template_group=None,
                metadata_origin="synthetic", text_origin="UCI-331-Amazon",
            )
            row.update(overrides)
            rows.append(row)

        # Cycling makes text reuse explicit, rather than pretending these are
        # independent public reviews. Every genuine source appears before reuse.
        for i in range(count):
            add(genuine_sources[i % len(genuine_sources)], start + i * 1200 + rng.uniform(0, 200))
        for trap, fraction in (("N1", .25), ("N2", .7)):
            for i in range(24):
                overrides = {"account_created": start - (100 + i) * 86400}
                if trap == "N1":  # legitimate shared NAT, diverse reviews
                    overrides["ip_hash"] = hashlib.sha256(f"{split}-campus".encode()).hexdigest()
                else:  # legitimate launch enthusiasm, established accounts
                    overrides.update(product_id="product-launch", rating=5)
                add(genuine_sources[(i * 5 + 17) % len(genuine_sources)],
                    start + duration * fraction + i * 30, scenario=trap, **overrides)
        for a, fraction in enumerate((.15, .4, .6, .85), 1):
            scenario = f"A{a}"
            for i in range(16):
                t = start + duration * fraction + i * (900 if a == 3 else 4)
                override = {"product_id": f"product-{a}", "rating": 1 if a == 3 else 5,
                            "template_group": f"{split}-campaign-{a}"}
                source = attack_sources[(a - 1) * 3 + (i % 3 if a != 1 else 0)]
                if a == 1:  # new-account, one-IP exact-copy burst
                    override.update(ip_hash=text_group(f"{split}-attack-ip"), account_created=t - 60)
                elif a == 2:  # distributed new accounts, coordinated target
                    override.update(account_created=t - 3600, user_agent="SyntheticAutomation/1")
                elif a == 3:  # aged-account slower negative campaign
                    override.update(account_created=t - 500 * 86400)
                else:  # one account submitting a rapid repeated-text stream
                    override.update(user_id=f"{split}-repeat-account", account_created=t - 30 * 86400)
                add(source, t, scenario=scenario, label=1, **override)
        start += duration + 2 * 86400
    rows.sort(key=lambda r: (r["created_at"], r["id"]))
    assert_split_integrity(rows)
    return rows


def assert_split_integrity(rows):
    from .features import validate_review
    seen_ids, text_splits, source_splits, templates = set(), {}, {}, {}
    by_split = {s: [] for s in ("train", "validation", "test")}
    for row in rows:
        validate_review(row)
        if any(key not in row for key in CANONICAL_KEYS):
            raise ValueError("Dataset is missing canonical keys")
        if row["id"] in seen_ids:
            raise ValueError("Duplicate dataset review id")
        seen_ids.add(row["id"])
        split = row["split"]
        if split not in by_split or row["true_label"] not in (0, 1):
            raise ValueError("Invalid split or true_label")
        by_split[split].append(float_timestamp(row["created_at"]))
        for mapping, key in ((text_splits, text_group(row["body"])),
                             (source_splits, row.get("source_group")),
                             (templates, row.get("template_group"))):
            if key is not None:
                if key in mapping and mapping[key] != split:
                    raise ValueError("Source text/group or attack template leaks across splits")
                mapping[key] = split
    if any(not times for times in by_split.values()):
        raise ValueError("All three splits are required")
    if not (max(by_split["train"]) < min(by_split["validation"]) and
            max(by_split["validation"]) < min(by_split["test"])):
        raise ValueError("Splits must be strictly chronological")


def float_timestamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Timestamp strings must include a timezone")
        return parsed.timestamp()
    raise ValueError("Expected numeric Unix seconds or timezone-aware ISO timestamp")


def write_jsonl(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")


def load_reviews(path):
    with Path(path).open(encoding="utf8") as stream:
        return [json.loads(line) for line in stream if line.strip()]
