"""Opt-in, persistent per-target request budgets shared by all LLM stages.

Unknown charges remain reserved and block that target pending reconciliation.
This is an experimental safety/accounting facility, not a research contribution.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from contextlib import contextmanager


class BudgetExceeded(RuntimeError):
    pass


class RequestBudget:
    def __init__(self, path, policy):
        self.path = Path(path)
        if not self.path.is_absolute():
            raise ValueError("Budget ledger_path must be absolute across stages")
        self.policy = dict(policy)
        for key in ("max_calls_per_target", "max_total_tokens_per_target", "max_input_tokens_per_call", "max_output_tokens_per_call"):
            value = policy.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("Budget requires positive integer " + key)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.policy_json = json.dumps(self.policy, sort_keys=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS policy (id INTEGER PRIMARY KEY CHECK(id=1), spec TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS calls (call_id TEXT PRIMARY KEY, target TEXT NOT NULL, stage TEXT, "
                       "reserved INTEGER NOT NULL, charged INTEGER NOT NULL, status TEXT NOT NULL, "
                       "created REAL NOT NULL, actual_input INTEGER, actual_output INTEGER)")
            db.execute("INSERT OR IGNORE INTO policy VALUES(1, ?)", (self.policy_json,))
            if db.execute("SELECT spec FROM policy WHERE id=1").fetchone()[0] != self.policy_json:
                raise ValueError("Budget policy changed for existing ledger")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, call_id, target, stage, input_tokens, output_tokens):
        if not isinstance(target, str) or not target:
            raise BudgetExceeded("Missing trace_target for budgeted request")
        if any(isinstance(n, bool) or not isinstance(n, int) for n in (input_tokens, output_tokens)) or input_tokens < 0 or output_tokens <= 0:
            raise ValueError("Invalid integer token count")
        if input_tokens > self.policy["max_input_tokens_per_call"]:
            raise BudgetExceeded("Input exceeds per-call budget")
        if output_tokens > self.policy["max_output_tokens_per_call"]:
            raise BudgetExceeded("Output exceeds per-call budget")
        amount = input_tokens + output_tokens
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            unresolved = db.execute("SELECT count(*) FROM calls WHERE target=? AND status IN ('reserved','unknown','overrun')", (target,)).fetchone()[0]
            if unresolved:
                raise BudgetExceeded("Prior request unresolved or overrun; no automatic retry")
            count, charged = db.execute("SELECT count(*), COALESCE(sum(charged),0) FROM calls WHERE target=?", (target,)).fetchone()
            if count >= self.policy["max_calls_per_target"]:
                raise BudgetExceeded("Per-target call budget exhausted")
            if charged + amount > self.policy["max_total_tokens_per_target"]:
                raise BudgetExceeded("Per-target reserved token budget exhausted")
            db.execute("INSERT INTO calls VALUES(?,?,?,?,?,?,?,?,?)",
                       (call_id, target, stage, amount, amount, "reserved", time.time(), None, None))
        return {"reserved_tokens": amount, "estimated_input_with_reserve": input_tokens, "effective_max_output": output_tokens}

    def settle(self, call_id, usage):
        incoming, outgoing = usage.get("prompt_tokens"), usage.get("completion_tokens")
        valid = all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (incoming, outgoing))
        reported_total = usage.get("total_tokens")
        if valid and reported_total is not None and reported_total != incoming + outgoing:
            valid = False
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT reserved,status FROM calls WHERE call_id=?", (call_id,)).fetchone()
            if row is None or row[1] != "reserved":
                raise ValueError("Unknown or already settled reservation")
            reserved = row[0]
            total = incoming + outgoing if valid else reserved
            status = "settled" if valid else "unknown"
            if valid and (incoming > self.policy["max_input_tokens_per_call"] or outgoing > self.policy["max_output_tokens_per_call"] or total > reserved):
                status = "overrun"
            db.execute("UPDATE calls SET charged=?,status=?,actual_input=?,actual_output=? WHERE call_id=?",
                       (total, status, incoming if valid else None, outgoing if valid else None, call_id))
        return {"status": status, "charged_tokens": total, "actual_usage_known": valid}


def load_budget(config, model):
    """Return budget and offline counter. Never downloads or executes tokenizer code."""
    raw = config.get("request_budget")
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        raise ValueError("request_budget must be a mapping")
    path = Path(raw["tokenizer_json"])
    if not path.is_absolute():
        raise ValueError("tokenizer_json must be an absolute local path")
    content = path.read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    if actual != raw["tokenizer_sha256"]:
        raise ValueError("Tokenizer hash mismatch")
    reserve = raw.get("framing_reserve", 256)
    if isinstance(reserve, bool) or not isinstance(reserve, int) or reserve < 0:
        raise ValueError("Invalid framing reserve")
    from tokenizers import Tokenizer
    tokenizer = Tokenizer.from_str(content.decode("utf-8"))
    policy = {key: raw[key] for key in ("max_calls_per_target", "max_total_tokens_per_target",
                                      "max_input_tokens_per_call", "max_output_tokens_per_call")}
    policy.update(model=model, thinking=config["llm"].get("thinking"),
                  tokenizer_sha256=actual, framing_reserve=reserve, version=1)
    budget = RequestBudget(raw["ledger_path"], policy)

    def count(messages):
        if any(not isinstance(message.get("content"), str) for message in messages):
            raise BudgetExceeded("Budget counter supports text-only messages")
        return reserve + sum(len(tokenizer.encode(m["content"], add_special_tokens=False).ids) for m in messages)

    return budget, count
