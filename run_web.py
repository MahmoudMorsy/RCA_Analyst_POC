from __future__ import annotations

import uvicorn

from rca_server.backend_config import BackendSettings


def main() -> int:
    settings = BackendSettings.load(__import__("pathlib").Path(__file__).resolve().parent)
    uvicorn.run("rca_server.app:app", host=settings.deployment.bind_host, port=settings.deployment.port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
