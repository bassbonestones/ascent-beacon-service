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
