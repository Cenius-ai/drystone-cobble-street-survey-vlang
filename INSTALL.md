# Installing Drystone Cobble Street Survey

## Prerequisites (installed by you, not by the setup script)

- **Python 3.11 or newer** with `pip` on the PATH (`python3 --version`).
- A POSIX shell (`sh`/`bash`).
- No database server, cache, message broker or network access is required: the
  app stores everything in a local SQLite file it creates itself.

## Full install, step by step

1. **Install the project dependencies.**

   ```bash
   pip3 install --upgrade pip setuptools wheel
   pip3 install -r requirements.txt
   ```

   `install.sh` runs exactly these two commands plus the seed step, non-
   interactively:

   ```bash
   sh install.sh
   ```

   It never starts the server and exits 0 on success.

2. **Create the schema and seed the demo data.** (Already done by `install.sh`;
   safe to re-run at any time — it skips rows that exist.)

   ```bash
   python3 -m app.seed
   ```

   This creates `drystone.db` in the project root, the operator account and the
   sample register: 6 streets (2 heritage conservation areas), 3 crews (1
   inactive), 10 patches and 6 jobs spanning all five statuses — including a
   heritage job left in `planned` with no consent reference, which is what the
   dashboard consent-gap metric counts.

3. **Run the app** (this is the step that keeps running):

   ```bash
   python3 -m app
   ```

   It binds `0.0.0.0` on `$PORT` (default `8000`). The equivalent explicit
   command is:

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
   ```

4. **Sign in** at <http://localhost:8000/login> with the demo operator:

   | Email | Username | Role | Password |
   | --- | --- | --- | --- |
   | cenius@cenius.ai | cenius | Survey operator (full access) | cenius |

5. **Run the tests** (optional, no network needed):

   ```bash
   python3 -m pytest
   ```

## Configuration

All settings are optional and have working defaults; the app boots with no
`.env` file. See `.env.example` for the complete list:

- `SECRET_KEY` — session signing key. Unset, the app logs a warning and uses the
  documented development fallback from `app/settings.py`. Set a long random
  value before deploying. A local `.env` is read on boot when present and never
  overrides variables already exported in the environment.
- `DATABASE_URL` — defaults to `sqlite:///./drystone.db` (relative to the
  project root; the file and its directory are created automatically).
- `PORT` — defaults to `8000`.

## Troubleshooting

- **`ModuleNotFoundError`** — run `pip3 install -r requirements.txt` again; the
  requirements file lists every runtime and test dependency.
- **Port already in use** — set `PORT=8010 python3 -m app` (any free port).
- **Empty dashboard** — run `python3 -m app.seed`; it is idempotent and will not
  duplicate the sample register.
- **Forgot the demo password** — it is printed on the login page and in the
  table above; seeding never overwrites an existing operator row.
