"""Import the released human annotations without inventing dimension mappings."""
import hashlib
import json
import random
from datetime import datetime
import urllib.request
from collections import defaultdict
from pathlib import Path
from .io import atomic_json, digest, now

SOURCE_COMMIT = "c3d44a6fc1790cc8c4b2fd7c01f0c72930655e0c"
SOURCE_BASE = f"https://raw.githubusercontent.com/morecry/CharacterEval/{SOURCE_COMMIT}/"
FILES = ["LICENSE", "rm_train_data.json", "data/character_profiles.json",
         "results/generation_trans_qwen_7b.jsonl", "results/generation_trans_baichuan_7b.jsonl"]
DIMENSIONS = ("persona", "empathy", "quality", "safety")


def fetch(raw_dir):
    raw = Path(raw_dir)
    raw.mkdir(parents=True, exist_ok=True)
    sources = []
    for relative in FILES:
        target = raw / Path(relative).name
        if not target.exists():
            with urllib.request.urlopen(SOURCE_BASE + relative, timeout=90) as response:
                data = response.read()
            temp = target.with_suffix(target.suffix + ".tmp")
            temp.write_bytes(data)
            temp.replace(target)
        payload = target.read_bytes()
        sources.append({"url": SOURCE_BASE + relative, "file": target.name,
                        "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)})
    manifest = {"commit": SOURCE_COMMIT, "fetched_at": now(), "license": "MIT (repository LICENSE)", "files": sources}
    atomic_json(raw.parent / "source-manifest.json", manifest)
    return manifest


def load_array(path):
    # CharacterEval's *.jsonl are JSON arrays, NOT line-delimited JSON.
    value = json.loads(Path(path).read_text())
    if not isinstance(value, list):
        raise ValueError(f"Expected CharacterEval JSON array: {path}")
    return value


def case_id(role, context, response):
    return digest([role, context, response])[:24]


def score(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a rating")
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError("Ratings must be integers 1..5")
    return value


def prepare(raw_dir, count=200, seed=42):
    raw = Path(raw_dir)
    rows = load_array(raw / "rm_train_data.json")
    profiles = json.loads((raw / "character_profiles.json").read_text())
    by_case = {}
    for index, row in enumerate(rows):
        cid = case_id(row["role"], row["context"], row["model_output"])
        if cid not in by_case:
            by_case[cid] = {"id": cid, "context_id": digest([row["role"], row["context"]])[:24],
                "source_id": row["id"], "role": row["role"], "profile": profiles[row["role"]],
                "context": row["context"], "response": row["model_output"],
                "human_scores": {}, "source_scores": {}, "source_rows": [], "primary": True,
                "human_provenance": "CharacterEval released rm_train_data; human annotation per upstream README",
                "source_commit": SOURCE_COMMIT}
        entry = by_case[cid]
        metric = row["metric_en"]
        rating = score(row[metric])
        if metric in entry["source_scores"] and entry["source_scores"][metric] != rating:
            raise ValueError(f"Conflicting original human scores for {cid}/{metric}")
        entry["source_scores"][metric] = rating
        entry["source_rows"].append(index)
        if metric == "Empathy":
            entry["human_scores"]["empathy"] = rating
    # Population is explicitly the Empathy-annotated subset, not all CharacterEval.
    eligible = sorted((row for row in by_case.values() if "empathy" in row["human_scores"]), key=lambda r: r["id"])
    if count > len(eligible) or count < 1:
        raise ValueError(f"Requested {count}; available Empathy-annotated cases: {len(eligible)}")
    selected = random.Random(seed).sample(eligible, count)
    selected.sort(key=lambda r: r["id"])
    for row in selected:
        row["human_pending"] = [d for d in DIMENSIONS if d not in row["human_scores"]]
    # Published candidate outputs add same-context alternatives, never human labels.
    alternatives = defaultdict(dict)
    for name in ("generation_trans_qwen_7b.jsonl", "generation_trans_baichuan_7b.jsonl"):
        path = raw / name
        if not path.exists():
            continue
        for row in load_array(path):
            text = row.get("model_output")
            if not text or text == "ERROR":
                continue
            context_id = digest([row["role"], row["context"]])[:24]
            alternatives[context_id][text] = name
    pairs, extra = [], {}
    selected_ids = {row["id"] for row in selected}
    for row in selected:
        choices = sorted((text, filename) for text, filename in alternatives[row["context_id"]].items() if text != row["response"])
        if not choices:
            continue
        text, filename = choices[0]
        cid = case_id(row["role"], row["context"], text)
        if cid not in selected_ids:
            extra[cid] = {**row, "id": cid, "response": text, "human_scores": {}, "source_scores": {},
                "source_rows": [], "primary": False, "human_provenance": None,
                "human_pending": list(DIMENSIONS), "candidate_source": filename}
        pairs.append({"id": digest([row["id"], cid])[:24], "context_id": row["context_id"],
                      "a_id": row["id"], "b_id": cid, "human_winners": {}, "human_pending": list(DIMENSIONS)})
    return selected + list(extra.values()), pairs


def annotation_template(cases, pairs, round_name="initial"):
    rows = []
    for case in cases:
        if not case["primary"]:
            continue
        rows.append({"kind": "pointwise", "id": case["id"], "round": round_name,
                     "annotator": "", "annotated_at": "", "scores": {d: None for d in DIMENSIONS},
                     "role": case["role"], "profile": case["profile"], "context": case["context"],
                     "response": case["response"], "provenance": "human"})
    index = {c["id"]: c for c in cases}
    for pair in pairs:
        a, b = index[pair["a_id"]], index[pair["b_id"]]
        rows.append({"kind": "pairwise", "id": pair["id"], "round": round_name,
                     "annotator": "", "annotated_at": "", "winners": {d: None for d in DIMENSIONS},
                     "role": a["role"], "profile": a["profile"], "context": a["context"],
                     "response_a": a["response"], "response_b": b["response"], "provenance": "human"})
    return rows


def validate_annotations(rows, cases, pairs):
    valid_ids = {"pointwise": {c["id"] for c in cases}, "pairwise": {p["id"] for p in pairs}}
    seen = set()
    dates = {}
    for row in rows:
        kind = row.get("kind")
        if kind not in valid_ids or row.get("id") not in valid_ids[kind]:
            raise ValueError("Unknown annotation kind or item ID")
        key = (kind, row["id"], row.get("round"), row.get("annotator"))
        if key in seen:
            raise ValueError("Duplicate annotation")
        seen.add(key)
        if row.get("provenance") != "human" or not row.get("annotator") or not row.get("annotated_at"):
            raise ValueError("Human provenance, annotator, and annotated_at are required")
        if row.get("round") not in {"initial", "retest"}:
            raise ValueError("Annotation round must be initial or retest")
        try:
            annotated_at = datetime.fromisoformat(row["annotated_at"].replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            raise ValueError("annotated_at must be an ISO timestamp") from None
        if annotated_at.tzinfo is None:
            raise ValueError("annotated_at must include a timezone")
        dates.setdefault((kind, row["id"], row["annotator"]), {})[row["round"]] = annotated_at
        values = row.get("scores" if kind == "pointwise" else "winners")
        if not isinstance(values, dict) or set(values) != set(DIMENSIONS):
            raise ValueError("Annotate all four dimensions explicitly")
        for value in values.values():
            if kind == "pointwise":
                if type(value) is not int:
                    raise ValueError("Human ratings must be JSON integer numbers")
                score(value)
            elif value not in {"A", "B", "tie"}:
                raise ValueError("Pairwise winners must be A, B or tie")
    for rounds in dates.values():
        if "initial" in rounds and "retest" in rounds and (rounds["retest"] - rounds["initial"]).total_seconds() < 48 * 3600:
            raise ValueError("Delayed retest must be at least 48 hours after the same annotator's initial rating")
    return rows
