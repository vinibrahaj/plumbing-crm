import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal

from .db import connect, init_db
from .security import (bearer, current_user, hash_password, manager, public_user,
                       token_hash, verify_password)


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title='Plumb CRM', lifespan=lifespan)


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')


class Login(Input):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(Input):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    role: Literal['customer', 'plumber']
    phone: str = Field(default='', max_length=40)
    address: str = Field(default='', max_length=300)
    service_ids: list[int] = Field(default_factory=list, max_length=100)

    @field_validator('email')
    @classmethod
    def email_shape(cls, value):
        if '@' not in value or value.startswith('@') or value.endswith('@'):
            raise ValueError('Enter a valid email address')
        return value.lower()


class ServiceCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    price_cents: int = Field(ge=0, le=100_000_000)
    workers: int = Field(ge=1, le=10)


class JobCreate(Input):
    customer_id: int | None = None
    service_id: int
    description: str = Field(min_length=1, max_length=4000)
    address: str = Field(min_length=1, max_length=300)
    priority: Literal['low', 'normal', 'high', 'emergency'] = 'normal'


class Assignment(Input):
    plumber_ids: list[int] = Field(max_length=10)


class Stage(Input):
    status: Literal['in_progress', 'finished']


class Note(Input):
    body: str = Field(min_length=1, max_length=4000)


def accessible_job(db, job_id, user):
    job = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    if not job:
        raise HTTPException(404, 'Job not found')
    allowed = user['role'] == 'manager' or (
        user['role'] == 'customer' and job['customer_id'] == user['id']
    ) or (user['role'] == 'plumber' and db.execute(
        'SELECT 1 FROM assignments WHERE job_id=? AND plumber_id=?', (job_id, user['id'])
    ).fetchone())
    if not allowed:
        raise HTTPException(404, 'Job not found')
    return job


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.post('/api/auth/login')
def login(data: Login):
    with connect() as db:
        user = db.execute('SELECT * FROM users WHERE email=?', (data.email,)).fetchone()
        # Use the same expensive operation for unknown users.
        encoded = user['password_hash'] if user else '0' * 32 + '$' + '0' * 64
        valid = verify_password(data.password, encoded)
        if not user or not valid:
            raise HTTPException(401, 'Incorrect email or password')
        token = secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires_at<=?', (int(time.time()),))
        db.execute('INSERT INTO sessions VALUES (?,?,?)',
                   (token_hash(token), user['id'], int(time.time()) + 8 * 3600))
        return {'access_token': token, 'token_type': 'bearer', 'user': public_user(user)}


@app.post('/api/auth/logout', status_code=204)
def logout(user=Depends(current_user), credentials=Depends(bearer)):
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(credentials.credentials),))


@app.get('/api/me')
def me(user=Depends(current_user)):
    return public_user(user)


@app.get('/api/users')
def users(user=Depends(manager)):
    with connect() as db:
        result = []
        for row in db.execute('SELECT * FROM users ORDER BY name').fetchall():
            item = public_user(row)
            item['service_ids'] = [s[0] for s in db.execute(
                'SELECT service_id FROM skills WHERE plumber_id=?', (row['id'],))]
            result.append(item)
        return result


@app.post('/api/users', status_code=201)
def create_user(data: UserCreate, user=Depends(manager)):
    with connect() as db:
        service_ids = set(data.service_ids)
        if data.role == 'customer' and service_ids:
            raise HTTPException(422, 'Only plumbers have service skills')
        for sid in service_ids:
            if not db.execute('SELECT 1 FROM services WHERE id=?', (sid,)).fetchone():
                raise HTTPException(422, 'Unknown service skill')
        try:
            cur = db.execute(
                'INSERT INTO users(name,email,password_hash,role,phone,address) VALUES (?,?,?,?,?,?)',
                (data.name, data.email, hash_password(data.password), data.role, data.phone, data.address))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Email already exists')
        uid = cur.lastrowid
        db.executemany('INSERT INTO skills VALUES (?,?)', [(uid, sid) for sid in service_ids])
        return public_user(db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone())


@app.get('/api/services')
def services(user=Depends(current_user)):
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM services ORDER BY name')]


@app.post('/api/services', status_code=201)
def create_service(data: ServiceCreate, user=Depends(manager)):
    with connect() as db:
        try:
            cur = db.execute('INSERT INTO services(name,price_cents,workers) VALUES (?,?,?)',
                             (data.name, data.price_cents, data.workers))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Service already exists')
        return {'id': cur.lastrowid, **data.model_dump()}


@app.get('/api/jobs')
def jobs(user=Depends(current_user)):
    with connect() as db:
        clause, args = '', []
        if user['role'] == 'customer':
            clause, args = 'WHERE j.customer_id=?', [user['id']]
        elif user['role'] == 'plumber':
            clause = 'WHERE j.id IN (SELECT job_id FROM assignments WHERE plumber_id=?)'
            args = [user['id']]
        rows = db.execute(
            'SELECT j.*, u.name customer_name, s.name service_name, s.workers '
            'FROM jobs j JOIN users u ON u.id=j.customer_id JOIN services s ON s.id=j.service_id '
            + clause + ' ORDER BY j.id DESC', args).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['plumbers'] = [dict(p) for p in db.execute(
                'SELECT u.id,u.name,u.phone,u.email FROM users u '
                'JOIN assignments a ON a.plumber_id=u.id WHERE a.job_id=?', (row['id'],))]
            # Work notes are internal to managers and assigned plumbers.
            item['notes'] = [] if user['role'] == 'customer' else [dict(n) for n in db.execute(
                'SELECT n.id,n.body,n.created_at,u.name author_name FROM notes n '
                'JOIN users u ON u.id=n.author_id WHERE n.job_id=? ORDER BY n.id', (row['id'],))]
            result.append(item)
        return result


@app.post('/api/jobs', status_code=201)
def create_job(data: JobCreate, user=Depends(current_user)):
    if user['role'] == 'plumber':
        raise HTTPException(403, 'Only managers and customers can create jobs')
    customer_id = user['id'] if user['role'] == 'customer' else data.customer_id
    if user['role'] == 'customer' and data.customer_id not in (None, user['id']):
        raise HTTPException(403, 'You can only create your own jobs')
    with connect() as db:
        if not db.execute("SELECT 1 FROM users WHERE id=? AND role='customer'", (customer_id,)).fetchone():
            raise HTTPException(422, 'Choose a customer')
        service = db.execute('SELECT * FROM services WHERE id=?', (data.service_id,)).fetchone()
        if not service:
            raise HTTPException(422, 'Unknown service')
        cur = db.execute(
            'INSERT INTO jobs(customer_id,service_id,description,address,priority,price_cents) '
            'VALUES (?,?,?,?,?,?)',
            (customer_id, data.service_id, data.description, data.address, data.priority, service['price_cents']))
        return {'id': cur.lastrowid}


@app.put('/api/jobs/{job_id}/assignments')
def assign(job_id: int, data: Assignment, user=Depends(manager)):
    with connect() as db:
        # Acquire the write lock before checking counts and replacing assignments.
        db.execute('BEGIN IMMEDIATE')
        job = accessible_job(db, job_id, user)
        if job['status'] != 'new':
            raise HTTPException(409, 'Assignments can only change before a job starts')
        workers = db.execute('SELECT workers FROM services WHERE id=?', (job['service_id'],)).fetchone()[0]
        if len(data.plumber_ids) != len(set(data.plumber_ids)):
            raise HTTPException(422, 'Duplicate plumbers are not allowed')
        if len(data.plumber_ids) > workers:
            raise HTTPException(422, f'This service allows at most {workers} plumbers')
        for pid in data.plumber_ids:
            if not db.execute(
                "SELECT 1 FROM skills s JOIN users u ON u.id=s.plumber_id "
                "WHERE u.role='plumber' AND u.id=? AND s.service_id=?", (pid, job['service_id'])
            ).fetchone():
                raise HTTPException(422, 'Every plumber must have the required service skill')
        db.execute('DELETE FROM assignments WHERE job_id=?', (job_id,))
        db.executemany('INSERT INTO assignments VALUES (?,?)', [(job_id, pid) for pid in data.plumber_ids])
        return {'plumber_ids': data.plumber_ids}


@app.patch('/api/jobs/{job_id}/status')
def stage(job_id: int, data: Stage, user=Depends(manager)):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        job = accessible_job(db, job_id, user)
        expected = {'new': 'in_progress', 'in_progress': 'finished'}.get(job['status'])
        if data.status != expected:
            raise HTTPException(409, 'Jobs must progress New → In Progress → Finished')
        if job['status'] == 'new':
            required = db.execute('SELECT workers FROM services WHERE id=?', (job['service_id'],)).fetchone()[0]
            count = db.execute('SELECT COUNT(*) FROM assignments WHERE job_id=?', (job_id,)).fetchone()[0]
            if count != required:
                raise HTTPException(409, f'Assign exactly {required} plumbers before starting')
        stamp = datetime.now(timezone.utc).isoformat()
        column = 'started_at' if data.status == 'in_progress' else 'finished_at'
        db.execute(f'UPDATE jobs SET status=?, {column}=? WHERE id=?', (data.status, stamp, job_id))
        return {'status': data.status}


@app.post('/api/jobs/{job_id}/notes', status_code=201)
def add_note(job_id: int, data: Note, user=Depends(current_user)):
    with connect() as db:
        accessible_job(db, job_id, user)
        if user['role'] == 'customer':
            raise HTTPException(403, 'Work notes are for managers and plumbers')
        cur = db.execute('INSERT INTO notes(job_id,author_id,body) VALUES (?,?,?)',
                         (job_id, user['id'], data.body))
        return {'id': cur.lastrowid}
