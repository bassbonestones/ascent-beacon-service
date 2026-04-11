# Sound First Service - Setup & Run

## First Time Setup

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

2. **Create `.env` file** (copy from `.env.example`):

   ```bash
   cp .env.example .env
   ```

   Then edit `.env` to set your `DATABASE_URL` (e.g., `sqlite:///./sound_first.db`)

3. **Run database migrations:**

   ```bash
   alembic upgrade head
   ```

4. **Initialize database (fresh start):**

   ```bash
   PYTHONPATH=. python resources/init_setup.py
   ```

   This removes the DB, runs migrations, and seeds all data.

   Or seed individually:

   ```bash
   PYTHONPATH=. python resources/seed_all.py              # all seed scripts
   PYTHONPATH=. python resources/seed_capabilities.py     # capabilities only
   PYTHONPATH=. python resources/seed_data.py             # focus cards, materials, test user
   PYTHONPATH=. python resources/seed_soft_gates.py resources/soft_gate_rules.json  # soft gates
   ```

## Run the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Run Tests

```bash
pytest
```

### Full test suite with coverage (JSON + terminal)

Run with the shell **current working directory** set to **`ascent-beacon-service`** (required by `tests/conftest.py`). From the monorepo root: `cd ascent-beacon-service`.

**One command** (writes `coverage.json` in the service directory, then prints total percent from JSON):

```bash
python -m pytest tests/ -v --cov=app --cov-report=json --cov-report=term-missing && python3 -c "import json; d=json.load(open('coverage.json')); print(f\"Coverage: {d['totals']['percent_covered']:.2f}%\")"
```

**Two-step** (same run, print percent from stdin):

```bash
python -m pytest tests/ -v --cov=app --cov-report=json --cov-report=term-missing
cat coverage.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"{d['totals']['percent_covered']:.2f}%\")"
```

The ratchet in `architecture/maturity-framework.md` also references `coverage report --precision=2` after `pytest --cov=app`; if those two totals ever disagree, use the documented gate command for the official floor.
