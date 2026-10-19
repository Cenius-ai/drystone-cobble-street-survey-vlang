"""``python3 -m app`` runs the survey server on 0.0.0.0:$PORT."""

from __future__ import annotations

import uvicorn

from app.main import app
from app.settings import port

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=port(), log_level="info")
