# Firewatch

A NIST 800-30 aligned cybersecurity risk register. Track risks, score them by likelihood and impact, assign treatments, and monitor your risk posture over time.

## Features

- **Risk register** — create and manage risks with full NIST 800-30 fields (threat source, threat event, vulnerability, affected asset)
- **Scoring** — likelihood × impact matrix (1–5 scale) with score history tracking
- **Treatments** — attach mitigation plans with owners, deadlines, and status
- **Audit trail** — field-level change history on every risk
- **Dashboard** — summary cards, 5×5 risk matrix heatmap, and average score trend chart with date range filter
- **Role-based access** — admin, security analyst, risk owner, and executive viewer roles
- **Database flexibility** — SQLite out of the box, PostgreSQL for production

## Quick Start (Docker)

The only requirement is [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
git clone https://github.com/smoore0927/Firewatch.git
cd Firewatch
make setup
```

Open `firewatch-backend/.env` and set `SECRET_KEY` to a random value:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Then start everything:

```bash
make up
```

Open [http://localhost:3000](http://localhost:3000).

## Configuration

All configuration lives in `firewatch-backend/.env`. The only required value is `SECRET_KEY`. Everything else has sensible defaults.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(required)* | Signs JWT tokens — generate with `secrets.token_hex(32)` |
| `DATABASE_URL` | `sqlite:///./firewatch.db` | Use `postgresql://user:pass@host/db` for Postgres |
| `DEBUG` | `False` | Set `True` to enable `/docs` and `/redoc` |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated list of allowed frontend origins |
| `SEED_ADMIN_EMAIL` | *(blank)* | Creates an admin account on first startup if set |
| `SEED_ADMIN_PASSWORD` | *(blank)* | Password for the seeded admin account |

## Manual Setup (without Docker)

**Backend**

```bash
cd firewatch-backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then edit .env
alembic upgrade head            # skip for SQLite — tables are created automatically
uvicorn main:app --reload
```

**Frontend**

```bash
cd firewatch-frontend
npm install
npm run dev
```

## Makefile Commands

| Command | Description |
|---|---|
| `make up` | Start all services |
| `make down` | Stop all services |
| `make build` | Rebuild Docker images |
| `make logs` | Follow logs from all services |
| `make backend` | Open a shell in the backend container |
| `make frontend` | Open a shell in the frontend container |

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Recharts |
| Backend | FastAPI, SQLAlchemy 2, Alembic |
| Database | SQLite (default) / PostgreSQL |
| Auth | JWT via HTTP-only cookies |
| Container | Docker Compose |

## License

[GNU Affero General Public License v3.0](LICENSE) — you are free to use and modify this software, but any modified version that you distribute or run as a network service must also be open-sourced under the same license.
