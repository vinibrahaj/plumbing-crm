# Plumb CRM

A small standalone plumbing CRM with a FastAPI API, a React interface, and SQLite storage. Inspired by the core workflow of a plumbing Odoo app; this version does not connect to Odoo.

## Included

- Manager, plumber, and customer accounts with API-enforced permissions.
- Managers create customer and plumber profiles, services, and jobs.
- Customers request services and see their own jobs only.
- Plumbers see assigned jobs, team contact details, and internal work notes. Home addresses of fellow plumbers stay private.
- Services have a fixed price in EUR, required plumber count, and matching plumber skills.
- Managers assign qualified plumbers and move jobs through **New → In progress → Finished**. Starting requires the full team; starting and finishing record timestamps.
- Internal work notes are visible to managers and assigned plumbers.
- Job prices are captured when a job is created. Amounts are stored as integer cents. No tax rules.

This starter deliberately leaves custom hourly jobs, materials, invoice PDFs, scheduling, reminders, editing/deleting profiles, and password reset for later iterations.

## Local setup

Requires Python 3.12+ and Node.js 22.12+ (Node 24 also works). SQLite is a local file, so no separate database server is needed.

```bash
git clone https://github.com/vinibrahaj/plumb-crm.git
cd plumb-crm
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
python -m app.cli --email manager@example.com --name "Manager"
```

The manager command securely prompts for a password of at least 12 characters. No default account or sample customer data is shipped. On Windows, activate the virtual environment with `.venv\Scripts\activate` instead.

Start the API from `backend/`:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, start the interface from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173** and sign in with the manager you created. Vite forwards `/api` requests to FastAPI. API documentation: **http://127.0.0.1:8000/docs**.

## First workflow

1. Add a service, its EUR price, and required plumber count.
2. Add a customer.
3. Add plumbers and select matching service skills when creating their accounts.
4. Create a job for the customer.
5. Assign the required team and click **Start job**.
6. Add internal work notes and click **Finish job** when complete.

Customers and plumbers sign in using the credentials created by their manager. There is no public signup in this version.

## Structure

```text
backend/app/db.py         SQLite schema and connection handling
backend/app/security.py   Password hashing and expiring session tokens
backend/app/main.py       API endpoints, permissions, and job rules
backend/app/cli.py        Manager bootstrap command
backend/tests/           API integration tests
frontend/src/            React interface and API client
.github/workflows/ci.yml  Backend tests and frontend build
```

## Checks

```bash
cd backend
python -m pytest -q
```

```bash
cd frontend
npm run build
```

## Configuration and deployment boundary

`DATABASE_PATH` optionally changes the SQLite location (default: `plumb.db` in the API's working directory). Set the same absolute path for both the manager command and API when overriding it. Back up the database using SQLite's backup API and keep it on persistent storage.

Passwords use PBKDF2-SHA256 with unique salts and 600,000 iterations. Random bearer sessions expire after eight hours, are hashed in the database, and are revoked on logout. The browser holds its token in session storage; it clears when that tab's session ends. Treat the frontend as a trusted origin and avoid injecting third-party scripts.

This is a local development starter. Before exposing it to the internet, serve the frontend and `/api` behind one HTTPS origin, add login rate limiting, password reset, and operational backups. The Vite proxy is development-only: `npm run preview` does not proxy the API. Run a single API process with this SQLite setup. A Cloudflare Pages-only deployment cannot run the Python API; it needs a Python-capable host with persistent disk, or a separate database/hosting adaptation.

Framework documentation: [FastAPI](https://fastapi.tiangolo.com/) · [React](https://react.dev/) · [Vite](https://vite.dev/guide/).
