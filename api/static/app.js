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
    const m = { dashboard: loadDashboard, contacts: loadContacts, lists: loadLists, templates: loadTemplates, campaigns: loadCampaigns, suppressions: loadSuppressions, reports: loadReports, cleaning: ()=>{}, ai: loadAI, users: loadUsers };
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

    const d = await api(url);
    let contacts = d.contacts;

    // Client-side filters
    if (listId) contacts = contacts.filter(c => c.list_ids?.includes(listId));
    if (search) contacts = contacts.filter(c => c.email.toLowerCase().includes(search.toLowerCase()));

    document.getElementById('contacts-tbody').innerHTML = contacts.map(c => {
        const lists = (c.list_ids || []).map(id => { const l = ALL_LISTS.find(l => l._id === id); return l ? l.name : ''; }).filter(n => n);
        return `<tr>
            <td>${c.email}</td><td>${c.first_name||''} ${c.last_name||''}</td>
            <td><span class="badge ${c.stream}">${c.stream}</span></td>
            <td><span class="badge ${c.status}">${c.status}</span></td>
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
        const tplName = c.template_id ? ' (from template)' : '';
        return `<tr><td>${c.name}<span class="text-muted">${tplName}</span></td><td><span class="badge ${c.stream}">${c.stream}</span></td><td><span class="badge ${c.status}">${c.status}</span></td><td>${s.sent||0}/${s.total_recipients||0}</td><td>${s.opened||0}</td><td>${s.bounced||0}</td><td>${actions}</td></tr>`;
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

async function bulkSuppressUpload() {
    const text = document.getElementById('sup-bulk-emails').value.trim();
    if (!text) return toast('Paste emails first', 'error');
    const emails = text.split('\n').map(e => e.trim()).filter(e => e);
    const reason = document.getElementById('sup-bulk-reason').value;
    let added = 0, skipped = 0;
    for (const email of emails) {
        try {
            await api('/suppressions', {method:'POST', body:JSON.stringify({email, reason})});
            added++;
        } catch { skipped++; }
    }
    toast(`Suppressed: ${added}, Skipped: ${skipped}`);
    closeModal('sup-bulk-modal');
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

// --- Init ---
document.getElementById('login-password').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
if (TOKEN && USER) showApp();
