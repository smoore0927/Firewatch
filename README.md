# Firewatch

A NIST 800-30 aligned cybersecurity risk register. Track risks, score them by likelihood and impact, assign owners, and monitor your risk posture over time.

## Features

- **Risk register** — create, manage, and delete risks with full NIST 800-30 fields (threat source, threat event, vulnerability, affected asset)
- **Scoring** — likelihood × impact matrix (1–5 scale) with score history tracking
- **Remediation Plans** — attach mitigation plans with owners, deadlines, and status
- **Audit trail** — field-level change history on every risk, plus a system-wide audit log of auth, SSO, and admin actions
- **Settings page** — admin-only view of the full audit log with filters by action, user, resource type, and date range
- **Dashboard** — summary cards, 5×5 risk matrix heatmap, and average score trend chart with date range filter
- **Review cadence** — set a reassessment frequency on each risk; the dashboard surfaces risks past their next review date, and re-scoring auto-schedules the next review
- **CSV import / export** — export the full risk register to CSV; download a pre-populated template and bulk-import risks from a spreadsheet
- **Role-based access** — admin, security analyst, risk owner, and executive viewer roles
- **SSO / OIDC login** — optional single sign-on via any OIDC-compliant provider (Google, Microsoft Entra, Okta, Auth0, Keycloak); email/password login continues to work alongside it
- **Database flexibility** — SQLite out of the box, PostgreSQL for production

## How It Works

```mermaid
graph TD
    Browser([🌐 Browser])

    subgraph Docker Compose
        subgraph fe[" Frontend Container  :3000 "]
            Vite["Vite Dev Server"]
            React["React + TypeScript"]
        end

        subgraph be[" Backend Container  :8000 "]
            FastAPI["FastAPI"]
            Auth["JWT Auth\n─────────\nbcrypt · PyJWT"]
            Logic["Risk Service\n─────────\nBusiness Logic"]
            ORM["SQLAlchemy ORM"]
        end

        subgraph db[" Database "]
            SQLite[("SQLite\ndefault")]
            PG[("PostgreSQL\nproduction")]
        end
    end

    Browser -->|"loads app"| Vite
    Vite -->|"serves React app"| React
    React -->|"API calls /api/*"| Vite
    Vite -->|"proxies to :8000"| FastAPI
    FastAPI -->|"validates JWT cookie"| Auth
    Auth -->|"user identity"| FastAPI
    FastAPI -->|"delegates"| Logic
    Logic -->|"queries"| ORM
    ORM -->|"reads / writes"| SQLite
    ORM -.->|"swap via DATABASE_URL"| PG
```

**Request flow in plain English:**
1. You open the app — Vite serves the React frontend to your browser
2. React makes API calls to `/api/...` — Vite proxies those to the FastAPI backend
3. FastAPI checks your JWT cookie to verify who you are
4. The Risk Service applies business rules, SQLAlchemy talks to the database
5. Data flows back up the chain and renders in the browser

## Quick Start (Docker)

The only requirement is [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
git clone https://github.com/smoore0927/Firewatch.git
cd Firewatch
```

Copy the example config file:

```bash
# Mac / Linux / Windows (with make)
make setup

# Windows (without make)
copy firewatch-backend\.env.example firewatch-backend\.env
```

Open `firewatch-backend/.env` and set `SECRET_KEY` to a random value:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Then start everything:

```bash
# Mac / Linux / Windows (with make)
make up

# Windows (without make)
docker compose up
```

Create the first admin account:

```bash
# Mac / Linux / Windows (with make)
make backend
python seed_admin.py

# Windows (without make)
docker compose exec backend bash
python seed_admin.py
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
| `FRONTEND_URL` | `http://localhost:3000` | Base URL of the frontend — used for SSO post-login redirects |

**SSO / OIDC (optional)** — leave `OIDC_ENABLED` unset or `False` to keep email/password-only login.

| Variable | Default | Description |
|---|---|---|
| `OIDC_ENABLED` | `False` | Set `True` to enable the SSO login button |
| `OIDC_DISCOVERY_URL` | — | Provider discovery URL, e.g. `https://accounts.google.com/.well-known/openid-configuration` |
| `OIDC_CLIENT_ID` | — | OAuth 2.0 client ID from your IdP |
| `OIDC_CLIENT_SECRET` | — | OAuth 2.0 client secret from your IdP |
| `OIDC_REDIRECT_URI` | — | Callback URL registered with your IdP, e.g. `https://your-host/api/auth/sso/callback` |
| `OIDC_PROVIDER_NAME` | `SSO` | Display label shown on the login button (e.g. `Okta`, `Google`) |
| `OIDC_SCOPES` | `openid email profile` | OIDC scopes to request |
| `OIDC_DEFAULT_ROLE` | `risk_owner` | Role assigned to new users provisioned via SSO |
| `OIDC_ROLE_CLAIM` | `groups` | ID token claim that contains the user's groups or roles (e.g. `groups` for Entra/Okta, `roles` for Entra App Roles) |
| `OIDC_ROLE_MAP` | `{}` | JSON object mapping claim values to Firewatch roles, e.g. `{"sec-team": "security_analyst", "admins": "admin"}`. Unmapped users get `OIDC_DEFAULT_ROLE`. |

## Running Tests

**Backend** — pytest suite covering risks, auth, users, dashboard, SSO/OIDC, and audit logging:

```bash
cd firewatch-backend
pip install -r requirements-dev.txt
pytest tests/ -v
```

**Frontend** — Vitest + React Testing Library:

```bash
cd firewatch-frontend
npm install
npm test             # single run
npm run test:watch   # watch mode
```

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

## Commands

If you have `make` installed:

| Command | Description |
|---|---|
| `make up` | Start all services |
| `make down` | Stop all services |
| `make build` | Rebuild Docker images |
| `make logs` | Follow logs from all services |
| `make backend` | Open a shell in the backend container |
| `make frontend` | Open a shell in the frontend container |

`make` is pre-installed on Mac and Linux. On Windows, install it with `winget install GnuWin32.Make` or use the Docker Compose commands directly:

| Equivalent | Docker Compose command |
|---|---|
| `make up` | `docker compose up` |
| `make down` | `docker compose down` |
| `make build` | `docker compose build` |
| `make logs` | `docker compose logs -f` |
| `make backend` | `docker compose exec backend bash` |
| `make frontend` | `docker compose exec frontend sh` |

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Recharts |
| Backend | FastAPI, SQLAlchemy 2, Alembic, slowapi |
| Database | SQLite (default) / PostgreSQL |
| Auth | JWT via HTTP-only cookies |
| Container | Docker Compose |

## License

[GNU Affero General Public License v3.0](LICENSE) — you are free to use and modify this software, but any modified version that you distribute or run as a network service must also be open-sourced under the same license.
