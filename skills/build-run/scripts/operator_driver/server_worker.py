"""Native task server alone, with authenticated identity for the launch transaction."""

import os
from pathlib import Path

import uvicorn
from bernstein.core.server.server_app import create_app


def main():
    root = Path.cwd().resolve()
    app = create_app(
        jsonl_path=root / ".sdd/runtime/tasks.jsonl", auth_token=os.environ["BERNSTEIN_AUTH_TOKEN"]
    )

    @app.get("/operator/identity")
    def operator_identity():
        return {"run_id": os.environ["BERNSTEIN_RUN_ID"], "root": str(root), "pid": os.getpid()}

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ["BERNSTEIN_OPERATOR_PORT"]), workers=1)


if __name__ == "__main__":
    main()
