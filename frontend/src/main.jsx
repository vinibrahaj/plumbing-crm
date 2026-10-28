import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api } from './api';
import './style.css';

const stages = [['new', 'New'], ['in_progress', 'In progress'], ['finished', 'Finished']];
const money = cents => `${(cents / 100).toFixed(2)} EUR`;
const values = event => Object.fromEntries(new FormData(event.currentTarget));

function Field({ label, children, ...props }) {
  return <label className="field"><span>{label}</span>{children || <input {...props}/>}</label>;
}

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [services, setServices] = useState([]);
  const [users, setUsers] = useState([]);
  const [view, setView] = useState('Jobs');
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(null);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const expired = () => { setUser(null); setError('Your session expired. Sign in again.'); };
    window.addEventListener('session-expired', expired);
    if (sessionStorage.getItem('plumb-token')) {
      api('/me').then(setUser).catch(e => setError(e.message)).finally(() => setLoading(false));
    } else setLoading(false);
    return () => window.removeEventListener('session-expired', expired);
  }, []);

  async function refresh(who = user) {
    const [nextJobs, nextServices, nextUsers] = await Promise.all([
      api('/jobs'), api('/services'), who.role === 'manager' ? api('/users') : Promise.resolve([]),
    ]);
    setJobs(nextJobs); setServices(nextServices); setUsers(nextUsers);
  }
  useEffect(() => {
    if (user) refresh(user).catch(e => setError(e.message));
  }, [user]);

  async function act(task) {
    setBusy(true); setError(''); setNotice('');
    try { await task(); }
    catch (e) { setError(e.message || 'Unable to connect to the API'); }
    finally { setBusy(false); }
  }

  async function login(event) {
    event.preventDefault(); const body = values(event);
    await act(async () => {
      const data = await api('/auth/login', { method: 'POST', body });
      sessionStorage.setItem('plumb-token', data.access_token);
      setView('Jobs'); setUser(data.user);
    });
  }

  async function save(event) {
    event.preventDefault(); const form = event.currentTarget; const data = values(event);
    await act(async () => {
      if (modal === 'job') {
        data.service_id = Number(data.service_id);
        if (data.customer_id) data.customer_id = Number(data.customer_id);
        await api('/jobs', { method: 'POST', body: data });
      } else if (modal === 'service') {
        await api('/services', { method: 'POST', body: {
          name: data.name, price_cents: Math.round(Number(data.price) * 100), workers: Number(data.workers),
        } });
      } else if (modal === 'customer' || modal === 'plumber') {
        data.role = modal;
        data.service_ids = new FormData(form).getAll('service_ids').map(Number);
        await api('/users', { method: 'POST', body: data });
      } else if (modal?.kind === 'assign') {
        await api(`/jobs/${modal.job.id}/assignments`, { method: 'PUT', body: {
          plumber_ids: new FormData(form).getAll('plumber_ids').map(Number),
        } });
      } else if (modal?.kind === 'note') {
        await api(`/jobs/${modal.job.id}/notes`, { method: 'POST', body: data });
      }
      setModal(null); setNotice('Saved successfully.'); await refresh();
    });
  }

  if (loading) return <main className="login"><p>Loading workspace…</p></main>;
  if (!user) return <main className="login">
    <section className="login-story"><div className="brand"><b className="brand-mark">P</b> Plumb CRM</div>
      <div><p className="eyebrow">YOUR PLUMBING WORKSPACE</p><h1>Every job.<br/>Under control.</h1><p>Keep customers, your team, and the work ahead in one place.</p></div>
      <small>From first request to finished job.</small>
    </section>
    <section className="login-form"><form onSubmit={login}><p className="eyebrow">WELCOME BACK</p><h2>Sign in to your workspace</h2>
      <p className="muted">Use the account created by your manager.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <Field label="Email address" name="email" type="email" autoComplete="username" required/>
      <Field label="Password" name="password" type="password" autoComplete="current-password" required/>
      <button className="primary wide" disabled={busy}>{busy ? 'Signing in…' : 'Sign in →'}</button>
      <p className="small muted">First setup? Create a manager with the command in the repository README.</p>
    </form></section>
  </main>;

  const isManager = user.role === 'manager';
  const filtered = jobs.filter(j => `${j.description} ${j.customer_name} ${j.service_name} ${j.id}`.toLowerCase().includes(search.toLowerCase()));
  const contacts = users.filter(u => u.role === (view === 'Customers' ? 'customer' : 'plumber'));
  const modalTitle = typeof modal === 'string' ? `New ${modal}` : modal?.kind === 'assign' ? 'Assign plumbers' : 'Work notes';

  return <div className="workspace">
    <aside><div className="brand"><b className="brand-mark">P</b> Plumb CRM</div><p className="nav-label">WORKSPACE</p>
      <nav>{['Jobs', ...(isManager ? ['Customers', 'Plumbers'] : []), 'Services'].map(v => <button key={v} className={view === v ? 'nav active' : 'nav'} onClick={() => { setView(v); setSearch(''); }}>{v}<span>↗</span></button>)}</nav>
      <div className="account"><div className="avatar">{user.name[0]}</div><div><b>{user.name}</b><small>{user.role}</small></div></div>
      <button className="logout" disabled={busy} onClick={() => act(async () => { await api('/auth/logout', { method: 'POST' }); sessionStorage.removeItem('plumb-token'); setUser(null); setJobs([]); setUsers([]); })}>Sign out</button>
    </aside>
    <main className="content"><header><div><p className="eyebrow">OPERATIONS / {view.toUpperCase()}</p><h1>{view === 'Jobs' ? 'Job overview' : view}</h1><p className="muted">{view === 'Jobs' ? 'A clear view of your work, from request to completion.' : view === 'Services' ? 'Services, fixed prices, and team requirements.' : 'The people behind every completed job.'}</p></div>
      {(isManager || (view === 'Jobs' && user.role === 'customer')) && <button className="primary" onClick={() => { setError(''); setModal(view === 'Jobs' ? 'job' : view === 'Services' ? 'service' : view === 'Customers' ? 'customer' : 'plumber'); }}>+ New {view === 'Jobs' ? 'job' : view === 'Services' ? 'service' : view === 'Customers' ? 'customer' : 'plumber'}</button>}
    </header>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p className="success" role="status">{notice}</p>}
    {view === 'Jobs' ? <>
      <section className="stats">{stages.map(([key, label]) => <div className="stat" key={key}><span>{label}</span><strong>{jobs.filter(j => j.status === key).length}</strong><small>{key === 'new' ? 'Waiting to get started' : key === 'in_progress' ? 'Your team is on it' : 'Work completed'}</small></div>)}</section>
      <div className="board-heading"><h2>All jobs <span className="count">{jobs.length}</span></h2><input aria-label="Search jobs" className="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search jobs or customers…"/></div>
      <section className="board">{stages.map(([key, label]) => <section className="column" key={key}><h3><i className={`dot ${key}`}/>{label}<span>{filtered.filter(j => j.status === key).length}</span></h3>
        {filtered.filter(j => j.status === key).map(job => <article className="job" key={job.id}>
          <div className="job-meta"><span>JOB #{String(job.id).padStart(3, '0')}</span><span className={`priority ${job.priority}`}>{job.priority}</span></div>
          <h3>{job.service_name}</h3><p className="description">{job.description}</p><p className="customer">{job.customer_name}</p><p className="muted small">{job.address}</p>
          <div className="job-team"><span>{job.plumbers.length ? job.plumbers.map(p => p.name).join(', ') : 'Unassigned'}</span><b>{money(job.price_cents)}</b></div>
          {(job.started_at || job.finished_at) && <p className="small muted">{job.finished_at ? 'Finished' : 'Started'} {new Date(job.finished_at || job.started_at).toLocaleString()}</p>}
          <div className="job-actions">
            {isManager && key === 'new' && <button disabled={busy} onClick={() => setModal({ kind: 'assign', job })}>Assign team</button>}
            {user.role !== 'customer' && <button onClick={() => setModal({ kind: 'note', job })}>Notes ({job.notes.length})</button>}
            {isManager && key !== 'finished' && <button className="action-primary" disabled={busy} onClick={() => act(async () => { await api(`/jobs/${job.id}/status`, { method: 'PATCH', body: { status: key === 'new' ? 'in_progress' : 'finished' } }); await refresh(); })}>{key === 'new' ? 'Start job →' : 'Finish job ✓'}</button>}
          </div></article>)}
        {!filtered.some(j => j.status === key) && <div className="empty-column">No {search ? 'matching ' : ''}jobs here</div>}
      </section>)}</section>
    </> : view === 'Services' ? <section className="service-grid">{services.map(s => <article className="service" key={s.id}><span className="service-icon">↗</span><h2>{s.name}</h2><p className="muted">{s.workers} {s.workers === 1 ? 'plumber' : 'plumbers'} required</p><strong>{money(s.price_cents)}</strong></article>)}{!services.length && <div className="empty-panel">No services yet.{isManager ? ' Add your first service to start creating jobs.' : ' Your manager will add services here.'}</div>}</section> : <div className="table-wrap"><table><thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>{view === 'Plumbers' ? 'Skills' : 'Address'}</th></tr></thead><tbody>{contacts.map(c => <tr key={c.id}><td><b>{c.name}</b></td><td>{c.email}</td><td>{c.phone || '—'}</td><td>{view === 'Plumbers' ? services.filter(s => c.service_ids.includes(s.id)).map(s => s.name).join(', ') || 'No skills' : c.address || '—'}</td></tr>)}</tbody></table>{!contacts.length && <p className="empty-panel">No {view.toLowerCase()} yet. Add the first one to get started.</p>}</div>}
    </main>
    {modal && <div className="overlay"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div className="modal-header"><h2 id="modal-title">{modalTitle}</h2><button type="button" aria-label="Close dialog" disabled={busy} onClick={() => setModal(null)}>✕</button></div>
      {error && <p className="error" role="alert">{error}</p>}
      <form onSubmit={save}>
        {modal === 'job' && <>
          {isManager && <Field label="Customer"><select name="customer_id" required defaultValue=""><option value="" disabled>Select customer</option>{users.filter(u => u.role === 'customer').map(u => <option value={u.id} key={u.id}>{u.name}</option>)}</select></Field>}
          <Field label="Service"><select name="service_id" required defaultValue=""><option value="" disabled>Select service</option>{services.map(s => <option key={s.id} value={s.id}>{s.name} · {money(s.price_cents)}</option>)}</select></Field>
          <Field label="Problem description"><textarea name="description" required maxLength={4000} rows={3}/></Field>
          <Field label="Service address" name="address" defaultValue={user.role === 'customer' ? user.address : ''} required maxLength={300}/>
          <Field label="Priority"><select name="priority" defaultValue="normal">{['low', 'normal', 'high', 'emergency'].map(p => <option key={p}>{p}</option>)}</select></Field>
        </>}
        {modal === 'service' && <><Field label="Service name" name="name" required maxLength={100}/><div className="form-row"><Field label="Price (EUR)" name="price" type="number" min="0" max="1000000" step="0.01" required/><Field label="Required plumbers" name="workers" type="number" min="1" max="10" defaultValue="1" required/></div></>}
        {(modal === 'customer' || modal === 'plumber') && <><Field label="Full name" name="name" required maxLength={120}/><Field label="Email" name="email" type="email" required maxLength={254}/><Field label="Initial password" name="password" type="password" autoComplete="new-password" minLength={12} maxLength={256} required/><Field label="Phone" name="phone" maxLength={40}/><Field label="Address" name="address" maxLength={300}/>{modal === 'plumber' && <fieldset><legend>Service skills</legend>{services.map(s => <label className="check" key={s.id}><input type="checkbox" name="service_ids" value={s.id}/>{s.name}</label>)}{!services.length && <p className="muted">Create services before adding a plumber.</p>}</fieldset>}</>}
        {modal?.kind === 'assign' && <><p className="muted">{modal.job.service_name} requires {modal.job.workers} plumber(s). Only matching skills are shown.</p><fieldset><legend>Available team</legend>{users.filter(u => u.role === 'plumber' && u.service_ids.includes(modal.job.service_id)).map(u => <label key={u.id} className="check"><input type="checkbox" name="plumber_ids" value={u.id} defaultChecked={modal.job.plumbers.some(p => p.id === u.id)}/>{u.name}</label>)}{!users.some(u => u.role === 'plumber' && u.service_ids.includes(modal.job.service_id)) && <p className="muted">Add a plumber with this service skill first.</p>}</fieldset></>}
        {modal?.kind === 'note' && <><div className="notes">{modal.job.notes.map(n => <article key={n.id}><b>{n.author_name}</b><small>{new Date(n.created_at).toLocaleString()}</small><p>{n.body}</p></article>)}{!modal.job.notes.length && <p className="muted">No work notes yet.</p>}</div><Field label="New internal note"><textarea name="body" required rows={3} maxLength={4000}/></Field></>}
        <button className="primary wide" disabled={busy}>{busy ? 'Saving…' : modal?.kind === 'note' ? 'Add note' : 'Save'}</button>
      </form></section></div>}
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
