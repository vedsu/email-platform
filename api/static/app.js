let TOKEN = localStorage.getItem('token');
let USER = JSON.parse(localStorage.getItem('user') || 'null');
let ALL_LISTS = [];

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

// --- Toast ---
function toast(msg, type = 'success') {
    const el = document.createElement('div');
    el.className = 'toast toast-' + type;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.classList.add('show'), 10);
    setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 300); }, 3000);
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
    loadAllLists();
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
    const m = { dashboard: loadDashboard, contacts: loadContacts, lists: loadLists, templates: loadTemplates, campaigns: loadCampaigns, suppressions: loadSuppressions, reports: loadReports, cleaning: ()=>{}, ai: loadAI, users: loadUsers, domains: loadDomains, ippools: loadIPPools, admin: loadAdmin };
    if (m[p]) m[p]();
}

// --- Modal ---
function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

// --- Multi-select dropdown helper ---
function createMultiSelect(containerId, options, placeholder = 'Select...') {
    const container = document.getElementById(containerId);
    container.innerHTML = '';
    container.className = 'multi-select';

    const display = document.createElement('div');
    display.className = 'ms-display';
    display.textContent = placeholder;
    display.onclick = () => dropdown.classList.toggle('open');

    const dropdown = document.createElement('div');
    dropdown.className = 'ms-dropdown';

    options.forEach(opt => {
        const label = document.createElement('label');
        label.className = 'ms-option';
        label.innerHTML = `<input type="checkbox" value="${opt.value}"> ${opt.label}`;
        label.querySelector('input').onchange = () => updateMultiSelectDisplay(containerId, placeholder);
        dropdown.appendChild(label);
    });

    container.appendChild(display);
    container.appendChild(dropdown);

    document.addEventListener('click', e => { if (!container.contains(e.target)) dropdown.classList.remove('open'); });
}

function getMultiSelectValues(containerId) {
    const checks = document.querySelectorAll(`#${containerId} input[type="checkbox"]:checked`);
    return Array.from(checks).map(c => c.value);
}

function updateMultiSelectDisplay(containerId, placeholder) {
    const vals = getMultiSelectValues(containerId);
    const display = document.querySelector(`#${containerId} .ms-display`);
    if (vals.length === 0) display.textContent = placeholder;
    else {
        const names = vals.map(v => { const l = ALL_LISTS.find(l => l._id === v); return l ? l.name : v; });
        display.textContent = names.length <= 2 ? names.join(', ') : `${names.length} lists selected`;
    }
}

// --- Load all lists (used across pages) ---
async function loadAllLists() {
    try {
        const d = await api('/lists');
        ALL_LISTS = d.lists || [];
    } catch { ALL_LISTS = []; }
}

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
let contactsPage = 0;
const CONTACTS_PER_PAGE = 50;

async function loadContacts() {
    const stream = document.getElementById('c-stream').value;
    const status = document.getElementById('c-status').value;
    const listId = document.getElementById('c-list').value;
    const search = document.getElementById('c-search').value.trim();

    // Populate list filter
    const listSel = document.getElementById('c-list');
    if (listSel.options.length <= 1) {
        ALL_LISTS.forEach(l => {
            if (!listSel.querySelector(`option[value="${l._id}"]`)) {
                const opt = document.createElement('option');
                opt.value = l._id; opt.textContent = l.name;
                listSel.appendChild(opt);
            }
        });
    }

    let url = `/contacts?limit=${CONTACTS_PER_PAGE}&skip=${contactsPage * CONTACTS_PER_PAGE}`;
    if (stream) url += '&stream=' + stream;
    if (status) url += '&status=' + status;
    if (listId) url += '&list_id=' + listId;
    if (search) url += '&search=' + encodeURIComponent(search);

    const d = await api(url);
    let contacts = d.contacts;

    document.getElementById('contacts-tbody').innerHTML = contacts.map(c => {
        const lists = (c.list_ids || []).map(id => { const l = ALL_LISTS.find(l => l._id === id); return l ? l.name : ''; }).filter(n => n);
        const tags = (c.tags || []).map(t => `<span class="badge" style="background:#e0e7ff;color:#3730a3;margin-right:2px">${t}</span>`).join('');
        const score = c.engagement_score || 0;
        const scoreColor = score >= 50 ? 'green' : score >= 20 ? 'orange' : 'red';
        return `<tr>
            <td>${c.email}</td><td>${c.first_name||''} ${c.last_name||''}</td>
            <td><span class="badge ${c.stream}">${c.stream}</span></td>
            <td><span class="badge ${c.status}">${c.status}</span></td>
            <td>${tags || '-'}</td>
            <td><span class="value ${scoreColor}" style="font-size:13px">${score}</span></td>
            <td class="text-muted">${lists.length ? lists.join(', ') : '-'}</td>
            <td>${c.engagement?.total_sent||0}</td><td>${c.engagement?.total_opened||0}</td><td>${c.engagement?.total_clicked||0}</td>
        </tr>`;
    }).join('');

    const total = d.total;
    const totalPages = Math.ceil(total / CONTACTS_PER_PAGE);
    document.getElementById('contacts-info').innerHTML = `
        Showing ${contactsPage * CONTACTS_PER_PAGE + 1}–${Math.min((contactsPage + 1) * CONTACTS_PER_PAGE, total)} of ${total}
        ${contactsPage > 0 ? `<button class="btn btn-secondary btn-sm" onclick="contactsPage--;loadContacts()">Prev</button>` : ''}
        ${contactsPage < totalPages - 1 ? `<button class="btn btn-secondary btn-sm" onclick="contactsPage++;loadContacts()">Next</button>` : ''}
    `;
}

function resetContactsPage() { contactsPage = 0; loadContacts(); }

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

    let data;
    if (csvFile) {
        const form = new FormData();
        form.append('file', csvFile);
        form.append('stream', stream);
        if (listId) form.append('list_id', listId);
        const res = await fetch('/csv/import-contacts', { method: 'POST', headers: { Authorization: 'Bearer ' + TOKEN }, body: form });
        data = await res.json();
    } else {
        const raw = document.getElementById('import-data').value.trim();
        let contacts;
        try { contacts = JSON.parse(raw); if (!Array.isArray(contacts)) contacts = [contacts]; } catch { return toast('Invalid JSON format', 'error'); }
        contacts.forEach(c => { if (!c.stream) c.stream = stream; });
        data = await api('/contacts/import', { method: 'POST', body: JSON.stringify({ contacts }) });
    }

    document.getElementById('import-result').innerHTML = `
        <div class="import-success">
            <span class="badge active">Imported: ${data.imported}</span>
            <span class="badge cold">Skipped: ${data.skipped}</span>
            ${data.errors?.length ? `<span class="badge suppressed">Errors: ${data.errors.length}</span>` : ''}
        </div>`;
    toast(`${data.imported} contacts imported, ${data.skipped} skipped`, data.imported > 0 ? 'success' : 'warning');
    loadContacts();
    loadAllLists();
}

// --- Lists ---
async function loadLists() {
    await loadAllLists();
    document.getElementById('lists-tbody').innerHTML = ALL_LISTS.map(l => `<tr>
        <td>${l.name}</td><td>${l.list_type}</td><td>${l.contact_count}</td>
        <td>${new Date(l.created_at).toLocaleDateString()}</td>
        <td>
            <button class="btn btn-danger btn-sm" onclick="deleteList('${l._id}','${l.name}',false)">Delete List</button>
            <button class="btn btn-danger btn-sm" onclick="deleteList('${l._id}','${l.name}',true)">Delete + Contacts</button>
        </td>
    </tr>`).join('');
}

async function createList() {
    await api('/lists', { method: 'POST', body: JSON.stringify({ name: document.getElementById('list-name').value, description: document.getElementById('list-desc').value }) });
    closeModal('list-modal');
    toast('List created');
    loadLists();
}

async function deleteList(listId, listName, deleteContacts) {
    const msg = deleteContacts
        ? `Delete list "${listName}" AND all contacts that ONLY belong to this list?`
        : `Delete list "${listName}"? Contacts will be kept but removed from this list.`;
    if (!confirm(msg)) return;

    if (deleteContacts) {
        await api(`/lists/${listId}/delete-with-contacts`, { method: 'DELETE' });
    } else {
        await api(`/lists/${listId}/delete`, { method: 'DELETE' });
    }
    toast(`List "${listName}" deleted`);
    loadLists();
    loadAllLists();
}

// --- Templates ---
async function loadTemplates() {
    const d = await api('/templates');
    document.getElementById('templates-tbody').innerHTML = d.templates.map(t => `<tr>
        <td>${t.name}</td><td><span class="badge">${t.category}</span></td><td>${t.subject}</td>
        <td>${new Date(t.created_at).toLocaleDateString()}</td>
        <td><button class="btn btn-secondary btn-sm" onclick="cloneTemplate('${t._id}','${t.name}')">Clone</button> <button class="btn btn-danger btn-sm" onclick="deleteTemplate('${t._id}')">Del</button></td>
    </tr>`).join('');
}

async function createTemplate() {
    const listOpts = ALL_LISTS.map(l => ({ value: l._id, label: l.name }));
    await api('/templates', { method: 'POST', body: JSON.stringify({
        name: document.getElementById('tpl-name').value, category: document.getElementById('tpl-cat').value,
        subject: document.getElementById('tpl-subject').value, preheader: document.getElementById('tpl-preheader').value,
        html_body: document.getElementById('tpl-html').value
    })});
    closeModal('template-modal');
    toast('Template created');
    loadTemplates();
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
    toast('Template cloned');
    loadTemplates();
}

async function deleteTemplate(id) {
    if (!confirm('Delete this template?')) return;
    await api('/templates/' + id, { method: 'DELETE' });
    toast('Template deleted');
    loadTemplates();
}

// --- Campaigns ---
async function loadCampaigns() {
    const d = await api('/campaigns');
    document.getElementById('campaigns-tbody').innerHTML = d.campaigns.map(c => {
        const s = c.stats || {};
        let actions = '';
        if (c.status === 'draft' || c.status === 'scheduled') actions = `<button class="btn btn-success btn-sm" onclick="launchCampaign('${c._id}')">Launch</button> `;
        else if (c.status === 'sending') actions = `<button class="btn btn-secondary btn-sm" onclick="pauseCampaign('${c._id}')">Pause</button> `;
        else if (c.status === 'paused') actions = `<button class="btn btn-primary btn-sm" onclick="resumeCampaign('${c._id}')">Resume</button> `;
        actions += `<button class="btn btn-secondary btn-sm" onclick="exportCSV('campaign/${c._id}')">CSV</button>`;
        if (c.status !== 'sending') {
            if (USER?.role === 'admin') actions += ` <button class="btn btn-danger btn-sm" onclick="deleteCampaign('${c._id}')">Delete</button>`;
            else actions += ` <button class="btn btn-secondary btn-sm" onclick="archiveCampaign('${c._id}')">Archive</button>`;
        }
        const tplName = c.template_id ? ' (from template)' : '';
        const archived = c.archived ? ' <span class="badge suppressed">archived</span>' : '';
        return `<tr><td>${c.name}<span class="text-muted">${tplName}</span>${archived}</td><td><span class="badge ${c.stream}">${c.stream}</span></td><td><span class="badge ${c.status}">${c.status}</span></td><td>${s.sent||0}/${s.total_recipients||0}</td><td>${s.opened||0}</td><td>${s.bounced||0}</td><td>${actions}</td></tr>`;
    }).join('');
    ['report-campaign','ai-camp'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<option value="">Select...</option>' + d.campaigns.map(c => `<option value="${c._id}">${c.name} (${c.status})</option>`).join('');
    });
}

async function openCampaignModal() {
    await loadAllLists();
    // Populate template selector
    const tplData = await api('/templates');
    const tplSel = document.getElementById('camp-tpl');
    tplSel.innerHTML = '<option value="">— None (custom) —</option>' + tplData.templates.map(t => `<option value="${t._id}" data-subject="${t.subject}" data-preheader="${t.preheader||''}" data-html="${encodeURIComponent(t.html_body)}">${t.name}</option>`).join('');

    // Populate list multi-select
    const listOpts = ALL_LISTS.map(l => ({ value: l._id, label: `${l.name} (${l.contact_count})` }));
    createMultiSelect('camp-lists-ms', listOpts, 'Select target lists...');

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
    const listIds = getMultiSelectValues('camp-lists-ms');
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
    closeModal('campaign-modal');
    toast('Campaign created');
    loadCampaigns();
}

async function archiveCampaign(id) { if (!confirm('Archive this campaign? It will be hidden from your view but admin can still see it.')) return; await api('/campaigns/'+id+'/archive', {method:'POST'}); toast('Campaign archived'); loadCampaigns(); }
async function deleteCampaign(id) { if (!confirm('Permanently delete this campaign and all its events? This cannot be undone.')) return; await api('/campaigns/'+id, {method:'DELETE'}); toast('Campaign permanently deleted'); loadCampaigns(); }
async function launchCampaign(id) { if (!confirm('Launch campaign? Emails will be sent.')) return; const d = await api('/campaigns/'+id+'/launch', {method:'POST'}); toast(`Campaign launched! ${d.enqueued} emails enqueued.`); loadCampaigns(); }
async function pauseCampaign(id) { await api('/campaigns/'+id+'/pause', {method:'POST'}); toast('Campaign paused'); loadCampaigns(); }
async function resumeCampaign(id) { const d = await api('/campaigns/'+id+'/resume', {method:'POST'}); toast(`Campaign resumed! ${d.enqueued} enqueued.`); loadCampaigns(); }

// --- Suppressions ---
async function loadSuppressions() {
    const [d, b] = await Promise.all([api('/suppressions'), api('/dashboard/suppression-breakdown')]);
    document.getElementById('sup-stats').innerHTML = `<div class="stat-card"><div class="label">Total</div><div class="value red">${b.total}</div></div>` +
        Object.entries(b.by_reason||{}).map(([r,c])=>`<div class="stat-card"><div class="label">${r.replace('_',' ')}</div><div class="value">${c}</div></div>`).join('');
    document.getElementById('sup-tbody').innerHTML = d.suppressions.map(s => `<tr><td>${s.email}</td><td><span class="badge ${s.reason}">${s.reason}</span></td><td>${s.source||'-'}</td><td>${new Date(s.created_at).toLocaleDateString()}</td><td><button class="btn btn-secondary btn-sm" onclick="removeSup('${s.email}')">Remove</button></td></tr>`).join('');
}

async function addSuppression() {
    await api('/suppressions', {method:'POST', body:JSON.stringify({email:document.getElementById('sup-email').value, reason:document.getElementById('sup-reason').value})});
    closeModal('sup-modal');
    toast('Email suppressed');
    loadSuppressions();
}

async function bulkSuppressCSV() {
    const file = document.getElementById('sup-bulk-file').files[0];
    if (!file) return toast('Select a CSV file first', 'error');

    const text = await file.text();
    const lines = text.split('\n').map(l => l.trim()).filter(l => l);
    if (lines.length < 2) return toast('CSV is empty', 'error');

    const header = lines[0].toLowerCase().split(',').map(h => h.trim().replace(/"/g, ''));
    const emailCol = header.indexOf('email');
    if (emailCol === -1) return toast('CSV must have an "email" column', 'error');

    const emails = [];
    for (let i = 1; i < lines.length; i++) {
        const cols = lines[i].split(',').map(c => c.trim().replace(/"/g, ''));
        const email = cols[emailCol];
        if (email && email.includes('@')) emails.push(email.toLowerCase());
    }

    if (emails.length === 0) return toast('No valid emails found in CSV', 'error');

    const reason = document.getElementById('sup-bulk-reason').value;
    const resultEl = document.getElementById('sup-bulk-result');
    resultEl.innerHTML = `<span class="loading"></span> Processing ${emails.length} emails...`;

    let added = 0, skipped = 0;
    for (const email of emails) {
        try {
            await api('/suppressions', {method:'POST', body:JSON.stringify({email, reason})});
            added++;
        } catch { skipped++; }
    }

    resultEl.innerHTML = `<div class="import-success"><span class="badge suppressed">Suppressed: ${added}</span> <span class="badge cold">Already suppressed: ${skipped}</span></div>`;
    toast(`${added} emails suppressed from CSV`);
    loadSuppressions();
}

async function removeSup(email) { if (!confirm('Remove '+email+'?')) return; await api('/suppressions/'+email, {method:'DELETE'}); toast('Suppression removed'); loadSuppressions(); }

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
        <p class="text-muted">Open: ${d.rates?.open_rate} | Click: ${d.rates?.click_rate} | Bounce: ${d.rates?.bounce_rate}</p>
        <button class="btn btn-secondary btn-sm mt-2" onclick="exportCSV('campaign/${id}')">Export CSV</button>`;
}

async function loadContactReport() {
    const email = document.getElementById('report-email').value;
    if (!email) return;
    try {
        const d = await api('/reports/contact/' + email);
        const c = d.contact; const eng = c.engagement || {};
        document.getElementById('report-contact').innerHTML = `<div class="card mt-2">
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
    try {
        const pts = document.getElementById('ai-points').value.split('\n').filter(p=>p.trim());
        const d = await api('/ai/draft-email', {method:'POST', body:JSON.stringify({purpose:document.getElementById('ai-purpose').value, audience:document.getElementById('ai-audience').value, tone:document.getElementById('ai-tone').value, key_points:pts.length?pts:null})});
        document.getElementById('ai-draft-out').innerHTML = `<div class="ai-response mt-2">${d.content}</div>`;
    } catch(e) { toast(e.message, 'error'); }
    btn.disabled=false; btn.textContent='Generate';
}
async function aiBounce(btn) {
    btn.disabled=true; btn.innerHTML='<span class="loading"></span>';
    try {
        const d = await api('/ai/classify-bounce', {method:'POST', body:JSON.stringify({bounce_message:document.getElementById('ai-bmsg').value, smtp_code:document.getElementById('ai-bcode').value})});
        document.getElementById('ai-bounce-out').innerHTML = `<div class="ai-response mt-2">${d.classification}</div>`;
    } catch(e) { toast(e.message, 'error'); }
    btn.disabled=false; btn.textContent='Classify';
}
async function aiAnalyze(btn) {
    const id = document.getElementById('ai-camp').value; if (!id) return;
    btn.disabled=true; btn.innerHTML='<span class="loading"></span> Analyzing...';
    try {
        const d = await api('/ai/analyze-campaign/'+id, {method:'POST'});
        document.getElementById('ai-analyze-out').innerHTML = `<div class="ai-response mt-2">${d.analysis}</div>`;
    } catch(e) { toast(e.message, 'error'); }
    btn.disabled=false; btn.textContent='Analyze';
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
    closeModal('user-modal'); toast('User created'); loadUsers();
}
async function resetPassword(id) {
    const d = await api('/auth/users/'+id+'/reset-password', {method:'POST'});
    toast('New password: ' + d.new_password, 'warning');
}

// --- CSV Export ---
function exportCSV(type) {
    window.open('/csv/export-' + type, '_blank');
}

// --- Domains ---
async function loadDomains() {
    const d = await api('/domains');
    document.getElementById('domains-tbody').innerHTML = d.domains.map(dm => {
        const statusClass = dm.status === 'verified' ? 'active' : dm.status === 'failed' ? 'suppressed' : 'draft';
        return `<tr>
            <td><strong>${dm.full_domain}</strong><br><span class="text-muted">${dm.domain}</span></td>
            <td><span class="badge ${dm.stream}">${dm.stream}</span></td>
            <td><span class="badge ${statusClass}">${dm.status}</span></td>
            <td>${dm.ip_pool_id ? '<span class="badge active">Assigned</span>' : '<span class="text-muted">None</span>'}</td>
            <td>
                <button class="btn btn-secondary btn-sm" onclick="showDNSRecords('${dm._id}')">DNS Records</button>
                <button class="btn btn-primary btn-sm" onclick="verifyDomain('${dm._id}')">Verify</button>
                <button class="btn btn-danger btn-sm" onclick="deleteDomain('${dm._id}')">Del</button>
            </td>
        </tr>`;
    }).join('');
}

async function addDomain() {
    const body = {
        domain: document.getElementById('dom-domain').value,
        stream: document.getElementById('dom-stream').value,
        subdomain_prefix: document.getElementById('dom-prefix').value || undefined,
    };
    const d = await api('/domains', { method: 'POST', body: JSON.stringify(body) });
    closeModal('domain-modal');
    toast(`Domain ${d.full_domain} added. Configure DNS records now.`);
    loadDomains();
    showDNSRecords(d.id);
}

async function showDNSRecords(domainId) {
    const d = await api('/domains/' + domainId);
    const panel = document.getElementById('dns-records-panel');
    panel.classList.remove('hidden');
    document.getElementById('dns-records-content').innerHTML = `
        <p class="mb-2"><strong>${d.full_domain}</strong> — Add these records at your domain provider:</p>
        <table><thead><tr><th>Type</th><th>Hostname</th><th>Value</th><th>Status</th></tr></thead><tbody>
        ${d.dns_records.map(r => `<tr>
            <td><strong>${r.record_type}</strong></td>
            <td><code style="font-size:11px">${r.hostname}</code></td>
            <td><code style="font-size:11px;word-break:break-all">${r.value}</code></td>
            <td>${r.verified ? '<span class="badge active">Verified</span>' : '<span class="badge draft">Pending</span>'}</td>
        </tr>`).join('')}
        </tbody></table>`;
}

async function verifyDomain(id) {
    const d = await api('/domains/' + id + '/verify', { method: 'POST' });
    toast(d.all_passed ? `${d.domain} verified!` : `${d.domain}: some records not found yet`, d.all_passed ? 'success' : 'warning');
    loadDomains();
    showDNSRecords(id);
}

async function deleteDomain(id) {
    if (!confirm('Delete this domain?')) return;
    await api('/domains/' + id, { method: 'DELETE' });
    toast('Domain deleted'); loadDomains();
    document.getElementById('dns-records-panel').classList.add('hidden');
}

// --- IP Pools ---
async function loadIPPools() {
    const [overview, pools, ips] = await Promise.all([api('/ip-pools/overview'), api('/ip-pools'), api('/ip-pools/ips')]);

    document.getElementById('ip-stats').innerHTML = `
        <div class="stat-card"><div class="label">Total IPs</div><div class="value blue">${overview.total_ips}</div></div>
        <div class="stat-card"><div class="label">Total Pools</div><div class="value blue">${overview.total_pools}</div></div>
        ${Object.entries(overview.by_status || {}).map(([s,c]) => `<div class="stat-card"><div class="label">${s}</div><div class="value">${c}</div></div>`).join('')}
    `;

    document.getElementById('pools-tbody').innerHTML = pools.pools.map(p => `<tr>
        <td><strong>${p.name}</strong><br><span class="text-muted">${p.description||''}</span></td>
        <td><span class="badge ${p.stream}">${p.stream}</span></td>
        <td>${p.ip_count || 0}</td>
        <td>${(p.domain_ids||[]).length}</td>
        <td><button class="btn btn-danger btn-sm" onclick="deletePool('${p._id}')">Del</button></td>
    </tr>`).join('');

    document.getElementById('ips-tbody').innerHTML = ips.ips.map(ip => `<tr>
        <td><strong>${ip.ip}</strong></td>
        <td><span class="badge">${ip.ip_type}</span></td>
        <td><span class="badge ${ip.stream}">${ip.stream}</span></td>
        <td><span class="badge ${ip.status === 'active' ? 'active' : ip.status === 'blocklisted' ? 'suppressed' : 'draft'}">${ip.status}</span></td>
        <td>${ip.domain_name || '-'}</td>
        <td>${ip.pool_name || '-'}</td>
        <td>${ip.daily_cap}</td>
        <td><button class="btn btn-danger btn-sm" onclick="deleteIP('${ip._id}')">Del</button></td>
    </tr>`).join('');

    // Populate pool selector in IP modal
    const poolSel = document.getElementById('ip-pool');
    poolSel.innerHTML = '<option value="">None</option>' + pools.pools.map(p => `<option value="${p._id}">${p.name}</option>`).join('');
}

async function createPool() {
    await api('/ip-pools', { method: 'POST', body: JSON.stringify({ name: document.getElementById('pool-name').value, stream: document.getElementById('pool-stream').value, description: document.getElementById('pool-desc').value }) });
    closeModal('pool-modal'); toast('Pool created'); loadIPPools();
}

async function addIP() {
    await api('/ip-pools/ips', { method: 'POST', body: JSON.stringify({
        ip: document.getElementById('ip-addr').value,
        hostname: document.getElementById('ip-hostname').value,
        ip_type: document.getElementById('ip-type').value,
        stream: document.getElementById('ip-stream').value,
        daily_cap: parseInt(document.getElementById('ip-cap').value) || 100,
        pool_id: document.getElementById('ip-pool').value || undefined,
    })});
    closeModal('ip-modal'); toast('IP added'); loadIPPools();
}

async function deletePool(id) { if (!confirm('Delete this pool?')) return; await api('/ip-pools/' + id, {method:'DELETE'}); toast('Pool deleted'); loadIPPools(); }
async function deleteIP(id) { if (!confirm('Delete this IP?')) return; await api('/ip-pools/ips/' + id, {method:'DELETE'}); toast('IP deleted'); loadIPPools(); }

// --- Admin ---
async function loadAdmin() {
    const [health, users, audit] = await Promise.all([api('/admin/system-health'), api('/admin/per-user-stats'), api('/admin/audit-log')]);

    document.getElementById('admin-health').innerHTML = Object.entries(health.services).map(([s, v]) =>
        `<span class="badge ${v === 'connected' || v === 'reachable' ? 'active' : 'suppressed'}" style="margin-right:8px">${s}: ${v}</span>`
    ).join('');

    document.getElementById('admin-collections').innerHTML = `<table><thead><tr><th>Collection</th><th>Documents</th></tr></thead><tbody>${Object.entries(health.collections).map(([c,n]) => `<tr><td>${c}</td><td>${n}</td></tr>`).join('')}</tbody></table>`;

    document.getElementById('admin-users-tbody').innerHTML = users.users.map(u => `<tr>
        <td>${u.email}</td><td><span class="badge ${u.role}">${u.role}</span></td>
        <td>${u.campaigns}</td><td>${u.total_sent}</td><td>${u.total_opened}</td><td>${u.total_bounced}</td>
    </tr>`).join('');

    document.getElementById('admin-audit').innerHTML = `
        <h3 style="font-size:13px;margin-bottom:8px">Recent Campaigns</h3>
        <table><thead><tr><th>Name</th><th>Status</th><th>Created</th></tr></thead><tbody>
        ${audit.recent_campaigns.map(c => `<tr><td>${c.name}</td><td><span class="badge ${c.status}">${c.status}</span></td><td>${new Date(c.created_at).toLocaleString()}</td></tr>`).join('')}
        </tbody></table>
        <h3 style="font-size:13px;margin:12px 0 8px">Recent Logins</h3>
        <table><thead><tr><th>User</th><th>Last Login</th></tr></thead><tbody>
        ${audit.recent_logins.map(l => `<tr><td>${l.email}</td><td>${new Date(l.last_login_at).toLocaleString()}</td></tr>`).join('')}
        </tbody></table>`;
}

// --- Init ---
document.getElementById('login-password').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
if (TOKEN && USER) showApp();
