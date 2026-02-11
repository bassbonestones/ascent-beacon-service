# Ascent Beacon - Backend API

Backend API for Ascent Beacon: Priority Lock module.

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Configure environment variables in `.env` file (see `.env` for required variables)

3. Run database migrations:

```bash
alembic upgrade head
```

4. Start the development server:

```bash
uvicorn app.main:app --reload
```

## Database Migrations

Create a new migration:

```bash
alembic revision -m "description"
```

Apply migrations:

```bash
alembic upgrade head
```

Rollback migrations:

```bash
alembic downgrade -1
```

## API Documentation

Once the server is running, visit:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Architecture

- **FastAPI** - Web framework
- **SQLAlchemy** - ORM with async support
- **PostgreSQL** - Database with pgvector extension
- **Alembic** - Database migrations
- **Pydantic** - Data validation and schemas
- **JWT** - Authentication tokens
- **OpenAI** - LLM and STT services

## Key Features

- Backend-owned authentication (Apple, Google, Magic Link Email)
- Values and Priorities with revision tracking
- Value-Priority linking system
- Alignment calculation (declared vs implied values)
- LLM-powered recommendations and reflections
- Speech-to-text transcription (ephemeral, no audio storage)
- Vector embeddings for semantic comparison
