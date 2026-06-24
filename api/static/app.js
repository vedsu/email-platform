let TOKEN = localStorage.getItem('token');
let USER = JSON.parse(localStorage.getItem('user') || 'null');

// --- API ---
async function api(path, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (TOKEN) headers['Authorization'] = 'Bearer ' + TOKEN;
    delete opts.headers;
    const res = await fetch(path, { headers, ...opts });
    if (res.status === 401) { doLogout(); throw new Error('Unauthorized'); }
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || res.statusText);
    }
    if (res.headers.get('content-type')?.includes('text/csv')) return res;
    return res.json();
}

// --- Auth ---
async function doLogin() {
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    try {
        const data = await api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
        TOKEN = data.access_token;
        USER = data.user;
        localStorage.setItem('token', TOKEN);
        localStorage.setItem('user', JSON.stringify(USER));
        showApp();
    } catch (e) { document.getElementById('login-error').textContent = e.message; }
}

function doLogout() {
    TOKEN = null; USER = null;
    localStorage.removeItem('token'); localStorage.removeItem('user');
    document.getElementById('app').classList.add('hidden');
    document.getElementById('login-page').style.display = 'flex';
}

function showApp() {
    document.getElementById('login-page').style.display = 'none';
    document.getElementById('app').classList.remove('hidden');
    document.getElementById('sidebar-user').textContent = USER ? `${USER.name} (${USER.role})` : '';
    if (USER?.role === 'admin') document.getElementById('admin-nav').classList.remove('hidden');
    else document.getElementById('admin-nav').classList.add('hidden');
    loadDashboard();
}

// --- Navigation ---
document.querySelectorAll('.sidebar a[data-page]').forEach(link => {
    link.addEventListener('click', e => {
        e.preventDefault();
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.querySelectorAll('.sidebar a').forEach(a => a.classList.remove('active'));
        document.getElementById('page-' + link.dataset.page).classList.add('active');
        link.classList.add('active');
        loadPage(link.dataset.page);
    });
});

function loadPage(p) {
    const m = { dashboard: loadDashboard, contacts: loadContacts, lists: loadLists, templates: loadTemplates, campaigns: loadCampaigns, suppressions: loadSuppressions, reports: loadReports, cleaning: ()=>{}, ai: loadAI, users: loadUsers };
    if (m[p]) m[p]();
}

// --- Modal ---
function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

// --- Dashboard ---
async function loadDashboard() {
    const d = await api('/dashboard/overview');
    const c = d.contacts;
    document.getElementById('dash-stats').innerHTML = `
        <div class="stat-card"><div class="label">Contacts</div><div class="value blue">${c.total}</div></div>
        <div class="stat-card"><div class="label">Active</div><div class="value green">${c.active}</div></div>
        <div class="stat-card"><div class="label">Suppressed</div><div class="value red">${c.suppressed}</div></div>
        <div class="stat-card"><div class="label">Campaigns</div><div class="value blue">${d.campaigns.total}</div></div>
        <div class="stat-card"><div class="label">Events</div><div class="value orange">${d.events.total}</div></div>`;
    const st = c.by_stream || {};
    document.getElementById('dash-streams').innerHTML = Object.keys(st).length
        ? `<table><thead><tr><th>Stream</th><th>Active</th></tr></thead><tbody>${Object.entries(st).map(([s,n])=>`<tr><td><span class="badge ${s}">${s}</span></td><td>${n}</td></tr>`).join('')}</tbody></table>`
        : '<p class="text-muted">No contacts</p>';
}

// --- Contacts ---
async function loadContacts() {
    const stream = document.getElementById('c-stream').value;
    const status = document.getElementById('c-status').value;
    let url = '/contacts?limit=100';
    if (stream) url += '&stream=' + stream;
    if (status) url += '&status=' + status;
    const d = await api(url);
    document.getElementById('contacts-tbody').innerHTML = d.contacts.map(c => `<tr>
        <td>${c.email}</td><td>${c.first_name||''} ${c.last_name||''}</td>
        <td><span class="badge ${c.stream}">${c.stream}</span></td>
        <td><span class="badge ${c.status}">${c.status}</span></td>
        <td>${c.engagement?.total_sent||0}</td><td>${c.engagement?.total_opened||0}</td><td>${c.engagement?.total_clicked||0}</td>
    </tr>`).join('');
    document.getElementById('contacts-info').textContent = `${d.contacts.length} of ${d.total}`;
}

function switchImportTab(tab, el) {
    document.querySelectorAll('#import-modal .tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    document.getElementById('import-json-tab').classList.toggle('hidden', tab !== 'json');
    document.getElementById('import-csv-tab').classList.toggle('hidden', tab !== 'csv');
}

async function importContacts() {
    const csvFile = document.getElementById('import-csv-file').files[0];
    const stream = document.getElementById('import-stream').value;
    const listId = document.getElementById('import-list').value;

    if (csvFile) {
        const form = new FormData();
        form.append('file', csvFile);
        form.append('stream', stream);
        if (listId) form.append('list_id', listId);
        const res = await fetch('/csv/import-contacts', { method: 'POST', headers: { Authorization: 'Bearer ' + TOKEN }, body: form });
        const data = await res.json();
        document.getElementById('import-result').innerHTML = `<span class="badge active">Imported: ${data.imported}</span> <span class="badge cold">Skipped: ${data.skipped}</span>`;
    } else {
        const raw = document.getElementById('import-data').value.trim();
        let contacts;
        try { contacts = JSON.parse(raw); if (!Array.isArray(contacts)) contacts = [contacts]; } catch { return alert('Invalid JSON'); }
        contacts.forEach(c => { if (!c.stream) c.stream = stream; });
        const data = await api('/contacts/import', { method: 'POST', body: JSON.stringify({ contacts }) });
        document.getElementById('import-result').innerHTML = `<span class="badge active">Imported: ${data.imported}</span> <span class="badge cold">Skipped: ${data.skipped}</span>`;
    }
    loadContacts();
}

// --- Lists ---
async function loadLists() {
    const d = await api('/lists');
    document.getElementById('lists-tbody').innerHTML = d.lists.map(l => `<tr><td>${l.name}</td><td>${l.list_type}</td><td>${l.contact_count}</td><td>${new Date(l.created_at).toLocaleDateString()}</td></tr>`).join('');
    // Update list selectors
    const opts = d.lists.map(l => `<option value="${l._id}">${l.name}</option>`).join('');
    const il = document.getElementById('import-list'); if (il) il.innerHTML = '<option value="">None</option>' + opts;
    const cl = document.getElementById('camp-lists'); if (cl) cl.innerHTML = opts;
}
async function createList() {
    await api('/lists', { method: 'POST', body: JSON.stringify({ name: document.getElementById('list-name').value, description: document.getElementById('list-desc').value }) });
    closeModal('list-modal'); loadLists();
}

// --- Templates ---
async function loadTemplates() {
    const d = await api('/templates');
    document.getElementById('templates-tbody').innerHTML = d.templates.map(t => `<tr>
        <td>${t.name}</td><td><span class="badge">${t.category}</span></td><td>${t.subject}</td>
        <td>${new Date(t.created_at).toLocaleDateString()}</td>
        <td><button class="btn btn-secondary btn-sm" onclick="cloneTemplate('${t._id}','${t.name}')">Clone</button> <button class="btn btn-danger btn-sm" onclick="deleteTemplate('${t._id}')">Del</button></td>
    </tr>`).join('');
    // Update campaign template selector
    const sel = document.getElementById('camp-tpl');
    if (sel) sel.innerHTML = '<option value="">— None (custom) —</option>' + d.templates.map(t => `<option value="${t._id}" data-subject="${t.subject}" data-preheader="${t.preheader||''}" data-html="${encodeURIComponent(t.html_body)}">${t.name}</option>`).join('');
}

async function createTemplate() {
    await api('/templates', { method: 'POST', body: JSON.stringify({
        name: document.getElementById('tpl-name').value, category: document.getElementById('tpl-cat').value,
        subject: document.getElementById('tpl-subject').value, preheader: document.getElementById('tpl-preheader').value,
        html_body: document.getElementById('tpl-html').value
    })});
    closeModal('template-modal'); loadTemplates();
}

function previewTemplate() {
    const html = document.getElementById('tpl-html').value.replace(/\{\{first_name\}\}/g, 'John').replace(/\{\{last_name\}\}/g, 'Doe').replace(/\{\{email\}\}/g, 'john@example.com');
    const el = document.getElementById('tpl-preview');
    el.classList.remove('hidden'); el.innerHTML = html;
}

async function cloneTemplate(id, name) {
    const newName = prompt('New template name:', name + ' (copy)');
    if (!newName) return;
    await api(`/templates/${id}/clone?new_name=${encodeURIComponent(newName)}`, { method: 'POST' });
    loadTemplates();
}

async function deleteTemplate(id) {
    if (!confirm('Delete this template?')) return;
    await api('/templates/' + id, { method: 'DELETE' }); loadTemplates();
}

// --- Campaigns ---
async function loadCampaigns() {
    const d = await api('/campaigns');
    document.getElementById('campaigns-tbody').innerHTML = d.campaigns.map(c => {
        const s = c.stats || {};
        let actions = '';
        if (c.status === 'draft' || c.status === 'scheduled') actions = `<button class="btn btn-success btn-sm" onclick="launchCampaign('${c._id}')">Launch</button>`;
        else if (c.status === 'sending') actions = `<button class="btn btn-secondary btn-sm" onclick="pauseCampaign('${c._id}')">Pause</button>`;
        else if (c.status === 'paused') actions = `<button class="btn btn-primary btn-sm" onclick="resumeCampaign('${c._id}')">Resume</button>`;
        actions += ` <button class="btn btn-secondary btn-sm" onclick="exportCSV('campaign/${c._id}')">CSV</button>`;
        return `<tr><td>${c.name}</td><td><span class="badge ${c.stream}">${c.stream}</span></td><td><span class="badge ${c.status}">${c.status}</span></td><td>${s.sent||0}/${s.total_recipients||0}</td><td>${s.opened||0}</td><td>${s.bounced||0}</td><td>${actions}</td></tr>`;
    }).join('');
    // Update report + AI campaign selectors
    ['report-campaign','ai-camp'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<option value="">Select...</option>' + d.campaigns.map(c => `<option value="${c._id}">${c.name} (${c.status})</option>`).join('');
    });
}

async function openCampaignModal() {
    await loadLists(); await loadTemplates();
    openModal('campaign-modal');
}

function onTemplateSelect() {
    const opt = document.getElementById('camp-tpl').selectedOptions[0];
    if (opt && opt.value) {
        document.getElementById('camp-subject').value = opt.dataset.subject || '';
        document.getElementById('camp-preheader').value = opt.dataset.preheader || '';
        document.getElementById('camp-html').value = decodeURIComponent(opt.dataset.html || '');
    }
}

async function createCampaign() {
    const listSel = document.getElementById('camp-lists');
    const listIds = Array.from(listSel.selectedOptions).map(o => o.value);
    const schedule = document.getElementById('camp-schedule').value;
    const body = {
        name: document.getElementById('camp-name').value,
        template_id: document.getElementById('camp-tpl').value || undefined,
        subject: document.getElementById('camp-subject').value,
        preheader: document.getElementById('camp-preheader').value,
        from_name: document.getElementById('camp-from-name').value,
        from_email: document.getElementById('camp-from-email').value,
        stream: document.getElementById('camp-stream').value,
        target_list_ids: listIds,
        html_body: document.getElementById('camp-html').value,
        scheduled_at: schedule ? new Date(schedule).toISOString() : undefined,
    };
    await api('/campaigns', { method: 'POST', body: JSON.stringify(body) });
    closeModal('campaign-modal'); loadCampaigns();
}

async function launchCampaign(id) { if (!confirm('Launch campaign?')) return; const d = await api('/campaigns/'+id+'/launch', {method:'POST'}); alert(`Launched! ${d.enqueued} enqueued.`); loadCampaigns(); }
async function pauseCampaign(id) { await api('/campaigns/'+id+'/pause', {method:'POST'}); loadCampaigns(); }
async function resumeCampaign(id) { const d = await api('/campaigns/'+id+'/resume', {method:'POST'}); alert(`Resumed! ${d.enqueued} enqueued.`); loadCampaigns(); }

// --- Suppressions ---
async function loadSuppressions() {
    const [d, b] = await Promise.all([api('/suppressions'), api('/dashboard/suppression-breakdown')]);
    document.getElementById('sup-stats').innerHTML = `<div class="stat-card"><div class="label">Total</div><div class="value red">${b.total}</div></div>` +
        Object.entries(b.by_reason||{}).map(([r,c])=>`<div class="stat-card"><div class="label">${r.replace('_',' ')}</div><div class="value">${c}</div></div>`).join('');
    document.getElementById('sup-tbody').innerHTML = d.suppressions.map(s => `<tr><td>${s.email}</td><td><span class="badge ${s.reason}">${s.reason}</span></td><td>${s.source||'-'}</td><td>${new Date(s.created_at).toLocaleDateString()}</td><td><button class="btn btn-secondary btn-sm" onclick="removeSup('${s.email}')">Remove</button></td></tr>`).join('');
}
async function addSuppression() { await api('/suppressions', {method:'POST', body:JSON.stringify({email:document.getElementById('sup-email').value, reason:document.getElementById('sup-reason').value})}); closeModal('sup-modal'); loadSuppressions(); }
async function removeSup(email) { if (!confirm('Remove '+email+'?')) return; await api('/suppressions/'+email, {method:'DELETE'}); loadSuppressions(); }

// --- Reports ---
async function loadReports() {
    const d = await api('/reports/overview');
    const g = d.global || {};
    document.getElementById('reports-global').innerHTML = `
        <div class="stat-card"><div class="label">Total Sent</div><div class="value blue">${g.total_sent||0}</div></div>
        <div class="stat-card"><div class="label">Open Rate</div><div class="value green">${d.rates?.open_rate||'0%'}</div></div>
        <div class="stat-card"><div class="label">Click Rate</div><div class="value blue">${d.rates?.click_rate||'0%'}</div></div>
        <div class="stat-card"><div class="label">Bounce Rate</div><div class="value orange">${d.rates?.bounce_rate||'0%'}</div></div>
        <div class="stat-card"><div class="label">Complaint Rate</div><div class="value red">${d.rates?.complaint_rate||'0%'}</div></div>`;
    await loadCampaigns();
}

async function loadCampaignReport() {
    const id = document.getElementById('report-campaign').value;
    if (!id) { document.getElementById('report-detail').innerHTML = ''; return; }
    const d = await api('/reports/campaign/' + id);
    const s = d.stats || {};
    document.getElementById('report-detail').innerHTML = `
        <div class="stats-grid">
            <div class="stat-card"><div class="label">Sent</div><div class="value">${s.sent||0}</div></div>
            <div class="stat-card"><div class="label">Delivered</div><div class="value green">${s.delivered||0}</div></div>
            <div class="stat-card"><div class="label">Opened</div><div class="value blue">${s.opened||0}</div></div>
            <div class="stat-card"><div class="label">Clicked</div><div class="value blue">${s.clicked||0}</div></div>
            <div class="stat-card"><div class="label">Bounced</div><div class="value orange">${s.bounced||0}</div></div>
            <div class="stat-card"><div class="label">Complained</div><div class="value red">${s.complained||0}</div></div>
        </div>
        <p class="text-muted">Open: ${d.rates?.open_rate} | Click: ${d.rates?.click_rate} | Bounce: ${d.rates?.bounce_rate} | Complaint: ${d.rates?.complaint_rate}</p>
        <button class="btn btn-secondary btn-sm mt-2" onclick="exportCSV('campaign/${id}')">Export CSV</button>`;
}

async function loadContactReport() {
    const email = document.getElementById('report-email').value;
    if (!email) return;
    try {
        const d = await api('/reports/contact/' + email);
        const c = d.contact;
        const eng = c.engagement || {};
        document.getElementById('report-contact').innerHTML = `
            <div class="card mt-2">
                <p><strong>${c.email}</strong> — ${c.first_name||''} ${c.last_name||''}</p>
                <p>Stream: <span class="badge ${c.stream}">${c.stream}</span> Status: <span class="badge ${c.status}">${c.status}</span> ${d.suppressed ? '<span class="badge suppressed">SUPPRESSED: '+d.suppression_reason+'</span>' : ''}</p>
                <p class="text-muted">Sent: ${eng.total_sent||0} | Opened: ${eng.total_opened||0} | Clicked: ${eng.total_clicked||0}</p>
                <h2 class="mt-2" style="font-size:13px">Recent Events</h2>
                <table><thead><tr><th>Type</th><th>Campaign</th><th>Date</th></tr></thead><tbody>${d.recent_events.map(e=>`<tr><td><span class="badge ${e.event_type}">${e.event_type}</span></td><td class="text-muted">${e.campaign_id?.substring(0,8)||'-'}</td><td>${new Date(e.created_at).toLocaleString()}</td></tr>`).join('')}</tbody></table>
            </div>`;
    } catch (e) { document.getElementById('report-contact').innerHTML = `<p class="text-muted mt-2">${e.message}</p>`; }
}

// --- Cleaning ---
async function verifyEmail() {
    const email = document.getElementById('verify-email').value;
    const d = await api('/cleaning/verify', {method:'POST', body:JSON.stringify({email})});
    document.getElementById('verify-result').innerHTML = `<div class="card mt-2"><p><strong>Verdict:</strong> <span class="badge ${d.verdict==='valid'?'active':'suppressed'}">${d.verdict}</span></p><p>MX: ${d.mx_record||'None'} | Role: ${d.is_role?'Yes':'No'} | Disposable: ${d.is_disposable?'Yes':'No'}</p></div>`;
}
async function bulkClean() {
    const emails = document.getElementById('bulk-emails').value.split('\n').map(e=>e.trim()).filter(e=>e);
    const d = await api('/cleaning/bulk', {method:'POST', body:JSON.stringify({emails})});
    const s = d.summary;
    document.getElementById('bulk-result').innerHTML = `<div class="stats-grid mt-2"><div class="stat-card"><div class="label">Valid</div><div class="value green">${s.valid}</div></div><div class="stat-card"><div class="label">Invalid</div><div class="value red">${s.invalid_syntax}</div></div><div class="stat-card"><div class="label">No MX</div><div class="value red">${s.no_mx}</div></div><div class="stat-card"><div class="label">Disposable</div><div class="value orange">${s.disposable}</div></div><div class="stat-card"><div class="label">Role</div><div class="value orange">${s.role}</div></div></div>`;
}

// --- AI ---
async function loadAI() { await loadCampaigns(); }
async function aiDraft(btn) {
    btn.disabled=true; btn.innerHTML='<span class="loading"></span> Generating...';
    const pts = document.getElementById('ai-points').value.split('\n').filter(p=>p.trim());
    const d = await api('/ai/draft-email', {method:'POST', body:JSON.stringify({purpose:document.getElementById('ai-purpose').value, audience:document.getElementById('ai-audience').value, tone:document.getElementById('ai-tone').value, key_points:pts.length?pts:null})});
    btn.disabled=false; btn.textContent='Generate';
    document.getElementById('ai-draft-out').innerHTML = `<div class="ai-response mt-2">${d.content}</div>`;
}
async function aiBounce(btn) {
    btn.disabled=true; btn.innerHTML='<span class="loading"></span>';
    const d = await api('/ai/classify-bounce', {method:'POST', body:JSON.stringify({bounce_message:document.getElementById('ai-bmsg').value, smtp_code:document.getElementById('ai-bcode').value})});
    btn.disabled=false; btn.textContent='Classify';
    document.getElementById('ai-bounce-out').innerHTML = `<div class="ai-response mt-2">${d.classification}</div>`;
}
async function aiAnalyze(btn) {
    const id = document.getElementById('ai-camp').value; if (!id) return;
    btn.disabled=true; btn.innerHTML='<span class="loading"></span> Analyzing...';
    const d = await api('/ai/analyze-campaign/'+id, {method:'POST'});
    btn.disabled=false; btn.textContent='Analyze';
    document.getElementById('ai-analyze-out').innerHTML = `<div class="ai-response mt-2">${d.analysis}</div>`;
}

// --- Users (Admin) ---
async function loadUsers() {
    const d = await api('/auth/users');
    document.getElementById('users-tbody').innerHTML = d.users.map(u => `<tr>
        <td>${u.email}</td><td>${u.name}</td><td><span class="badge ${u.role}">${u.role}</span></td>
        <td>${u.is_active !== false ? '<span class="badge active">Yes</span>' : '<span class="badge suppressed">No</span>'}</td>
        <td>${u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'Never'}</td>
        <td><button class="btn btn-secondary btn-sm" onclick="resetPassword('${u._id}')">Reset PW</button></td>
    </tr>`).join('');
}
async function createUser() {
    await api('/auth/users', {method:'POST', body:JSON.stringify({email:document.getElementById('usr-email').value, name:document.getElementById('usr-name').value, password:document.getElementById('usr-pass').value, role:document.getElementById('usr-role').value})});
    closeModal('user-modal'); loadUsers();
}
async function resetPassword(id) {
    const d = await api('/auth/users/'+id+'/reset-password', {method:'POST'});
    alert('New password: ' + d.new_password);
}

// --- CSV Export ---
function exportCSV(type) {
    const a = document.createElement('a');
    a.href = '/csv/export-' + type;
    a.download = type + '.csv';
    if (TOKEN) a.href += (a.href.includes('?') ? '&' : '?') + '_token=' + TOKEN;
    a.click();
}

// --- Init ---
if (TOKEN && USER) showApp();
