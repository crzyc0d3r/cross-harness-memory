"""Session-start prime, per-turn recall, and completed-turn observation."""
import json
import uuid


def memory_data(records):
    """Keep provenance and data together; never interpolate records into instructions."""
    return {"role": "tool", "name": "memory_context",
            "content": json.dumps({"trust": "untrusted", "records": records}, ensure_ascii=False)}


class Session:
    def __init__(self, memory, harness):
        if not isinstance(harness, str) or not harness.strip():
            raise ValueError("A harness label is required")
        self.memory, self.harness = memory, harness
        self.id, self.closed, self.turns = uuid.uuid4().hex, False, 0
        self.start_context = memory_data(memory.prime()["records"])

    def turn(self, question, answerer):
        if self.closed:
            raise RuntimeError("Session is closed")
        recalled = self.memory.recall(question)
        context = memory_data([x["record"] for x in recalled["results"]])
        answer = answerer(question, self.start_context, context)
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("An answerer must return nonempty text")
        self.turns += 1
        self.memory.observe(question, answer, session_id=self.id, turn_id=str(self.turns),
                            writer=self.harness)
        return {"harness": self.harness, "session": self.id, "question": question,
                "prime": json.loads(self.start_context["content"]),
                "recall": recalled, "answer": answer}

    def close(self):
        self.closed = True
