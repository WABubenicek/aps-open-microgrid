"""Config loader with publish gate: any value whose status is 'conflict' is refused."""
import json, os, copy
from functools import lru_cache

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PUBLIC = os.path.join(ROOT, "aps-config.v0.1.json")
PRIVATE = os.path.join(ROOT, "aps-config.private.json")


class ConflictBlocked(Exception):
    """Raised when an output would publish a value whose status is 'conflict'."""


@lru_cache(maxsize=1)
def _load_public():
    with open(PUBLIC) as f:
        return json.load(f)


class Config:
    def __init__(self, data=None, private=None):
        self.data = copy.deepcopy(data if data is not None else _load_public())
        if private is None and os.path.exists(PRIVATE):
            with open(PRIVATE) as f:
                private = json.load(f)
        self.private = private or {}
        self.version = self.data.get("version")

    def raw(self, path, root=None):
        node = root if root is not None else self.data
        for k in path.split("/"):
            if not isinstance(node, dict) or k not in node:
                return None
            node = node[k]
        return node

    def leaf(self, path, root=None):
        """Return (value, meta). Refuses conflicts; ranges -> midpoint flagged unverified."""
        n = self.raw(path, root)
        if isinstance(n, dict) and "status" in n and "value" in n:
            if n["status"] == "conflict":
                raise ConflictBlocked(f"{path} is in conflict ({n.get('conflict_id')}); refusing to publish")
            v = n["value"]
            meta = {"status": n["status"], "source": n.get("source"), "verified_on": n.get("verified_on")}
            if isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
                meta["range"] = v
                meta["status"] = "unverified"
                v = sum(v) / 2
            return v, meta
        return n, {"status": "structural", "source": "config"}

    def val(self, path, root=None, default=None):
        v, _ = self.leaf(path, root)
        return default if v is None else v

    def scan_conflicts(self, node=..., path=""):
        node = self.data if node is ... else node
        out = []
        if isinstance(node, dict):
            if node.get("status") == "conflict":
                out.append(path)
            for k, v in node.items():
                out += self.scan_conflicts(v, f"{path}/{k}")
        return out


def default_config():
    return Config()
