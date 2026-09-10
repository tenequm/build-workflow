"""Authenticated access to the identified per-run task server."""

from __future__ import annotations

import httpx

from .storage import Park


class Server:
    def __init__(self, url: str, token: str):
        self.client = httpx.Client(
            base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=15
        )

    def close(self):
        self.client.close()

    def tasks(self) -> list[dict]:
        tasks = []
        offset = 0
        while True:
            response = self.client.get("/tasks", params={"limit": 200, "offset": offset})
            response.raise_for_status()
            page = response.json()
            if isinstance(page, list):
                if offset:
                    raise Park("server changed pagination format")
                return page
            rows = page["tasks"]
            tasks.extend(rows)
            offset += len(rows)
            if offset >= page["total"]:
                return tasks
            if not rows:
                raise Park("task inventory pagination made no progress")

    def post_task(self, body: dict) -> dict:
        response = self.client.post("/tasks", json=body)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def verify_task(task: dict, body: dict) -> None:
        for key in (
            "title",
            "description",
            "role",
            "owned_files",
            "depends_on",
            "completion_signals",
            "model",
            "effort",
            "cli",
            "scope",
            "complexity",
        ):
            if key in body and task.get(key) != body[key]:
                raise Park(f"stored task differs from frozen payload: {key}")
        for key, value in body.get("metadata", {}).items():
            if task.get("metadata", {}).get(key) != value:
                raise Park(f"stored task lost metadata: {key}")


def admitted_inventory(tasks: list[dict], expected: set[str]) -> None:
    """Only genuine retry lineage may extend the posted set; no repair/QA wildcard."""
    allowed = set(expected)
    by_id = {task["id"]: task for task in tasks}
    if len(by_id) != len(tasks):
        raise Park("task inventory contains duplicate IDs")
    # Every retry is compared against the ADMITTED task at the root of its chain, not
    # its immediate parent: a middle retry that dropped owned_files must not become
    # the anchor a later retry carrying the frozen list is judged against.
    root = {task_id: task_id for task_id in allowed}
    pending = [task for task in tasks if task["id"] not in allowed]
    while pending:
        next_pending = []
        for task in pending:
            parent = task.get("metadata", {}).get("retry_of")
            if parent in allowed and parent in by_id:
                original = by_id[root[parent]]
                root[task["id"]] = root[parent]
                for key in ("title", "description", "role", "completion_signals"):
                    if task.get(key) != original.get(key):
                        raise Park(f"native retry changed frozen task {key}")
                # The native retry path drops owned_files (measured 2026-09-10: a retry
                # of a three-file step carried []). Ownership is enforced by the scorer
                # from the frozen plan, not from the task, so an emptied list is the
                # engine losing a field. A DIFFERENT list would be a widened scope.
                if task.get("owned_files") not in (original.get("owned_files"), [], None):
                    raise Park("native retry changed frozen task owned_files")
                for key in ("operator_run", "operator_spec", "context_files"):
                    if task.get("metadata", {}).get(key) != original.get("metadata", {}).get(key):
                        raise Park(f"native retry changed frozen metadata {key}")
                allowed.add(task["id"])
            else:
                next_pending.append(task)
        if len(next_pending) == len(pending):
            raise Park(
                "unexpected task inventory: " + ", ".join(task["title"] for task in next_pending)
            )
        pending = next_pending
    missing = expected - {task["id"] for task in tasks}
    if missing:
        raise Park(f"posted tasks disappeared: {sorted(missing)}")
