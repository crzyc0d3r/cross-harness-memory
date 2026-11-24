"""Deterministic cross-harness handoff using synthetic travel preferences."""
import argparse
import json
from pathlib import Path
import tempfile

from lifecycle import Session
from store import LocalMemory


def run_demo(path, query="vegetarian dinner Kyoto", person="traveler"):
    store = LocalMemory(path)
    owner = store.for_user("traveler")
    owner.remember("I prefer vegetarian dinner.", writer="traveler", writer_type="human",
                   standing=True, dedup="fixture-standing-preference")
    owner.remember("I prefer quiet vegetarian restaurants in Kyoto.", writer="claude-code",
                   dedup="fixture-preference")
    other = store.for_user("other-person")
    other.remember("My private reservation code is SYNTHETIC-PRIVATE-42.",
                   writer="claude-code", dedup="fixture-other")
    selected = owner if person == "traveler" else other
    first = Session(owner, "claude-code")
    first.turn("Remember my vegetarian dinner preference.", lambda *_: "Preference recorded explicitly.")
    first.close()
    second = Session(selected, "codex")

    def deterministic_answer(question, prime, context):
        records = json.loads(context["content"])["records"]
        if not records:
            return "No matching memory; ask for preferences before suggesting dinner."
        facts = [r for r in records if r["type"] == "fact"]
        return ("Recovered stated facts: " + " | ".join(r["content"][0]["text"] for r in facts)) \
            if facts else "Related episodes found; ask for a confirmed preference."

    result = second.turn(query, deterministic_answer)
    second.close()
    return {"mode": "offline deterministic demonstration", "person": person,
            "handoff": "claude-code → shared private memory → fresh codex session",
            "result": result, "records_after_turn": len(selected.all()),
            "isolation": "The selected bound identity cannot read another private root."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--query", default="vegetarian dinner Kyoto")
    parser.add_argument("--person", choices=["traveler", "other-person"], default="traveler")
    args = parser.parse_args()
    if args.db:
        print(json.dumps(run_demo(args.db, args.query, args.person), indent=2))
    else:
        with tempfile.TemporaryDirectory() as temporary:
            print(json.dumps(run_demo(Path(temporary) / "memory.sqlite", args.query, args.person), indent=2))


if __name__ == "__main__":
    main()
