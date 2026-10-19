"""Root entrypoint so `uvicorn main:app` works as well as `uvicorn app.main:app`."""

from __future__ import annotations

import uvicorn

from app.main import app
from app.settings import port

__all__ = ["app"]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=port(), log_level="info")
