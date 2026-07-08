let TOKEN = localStorage.getItem('token');
let USER = JSON.parse(localStorage.getItem('user') || 'null');
let ALL_LISTS = [];
let ALL_TEMPLATES = [];
let editingTemplateId = null;

// --- API ---
async function api(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (!opts.body || typeof opts.body === 'string') headers['Content-Type'] = 'application/json';
    if (TOKEN) headers['Authorization'] = 'Bearer ' + TOKEN;
    delete opts.headers;
    const res = await fetch(path, { headers, ...opts });
    if (res.status === 401) {
        // Only logout if this was an auth-required endpoint, not login itself
        if (!path.includes('/auth/login')) { doLogout(); }
        throw new Error('Unauthorized');
    }
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || res.statusText);
    }
    if (res.headers.get('content-type')?.includes('text/csv')) return res;
    return res.json();
}

// --- Auth Fetch (for multipart/FormData uploads that can't use api()) ---
async function authFetch(url, opts = {}) {
    const headers = { Authorization: 'Bearer ' + TOKEN, ...(opts.headers || {}) };
    const res = await fetch(url, { ...opts, headers });
    if (res.status === 401) {
        doLogout();
        throw new Error('Session expired — please log in again');
    }
    return res;
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
    // Clear any stale state before attempting login
    TOKEN = null;
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    try {
        const data = await api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
        TOKEN = data.access_token;
        USER = data.user;
        localStorage.setItem('token', TOKEN);
        localStorage.setItem('user', JSON.stringify(USER));
        document.getElementById('login-error').textContent = '';
        showApp();
    } catch (e) { document.getElementById('login-error').textContent = e.message; }
}

function doLogout() {
    TOKEN = null; USER = null;
    localStorage.removeItem('token'); localStorage.removeItem('user');
    document.getElementById('app').classList.add('hidden');
    document.getElementById('login-page').style.display = 'flex';
}

async function showApp() {
    document.getElementById('login-page').style.display = 'none';
    document.getElementById('app').classList.remove('hidden');
    // Top bar user badge
    if (USER) {
        document.getElementById('top-user-name').textContent = USER.name;
        const roleEl = document.getElementById('top-user-role');
        roleEl.textContent = USER.role;
        roleEl.className = `role-chip ${USER.role}`;
    }
    document.getElementById('sidebar-user').textContent = USER?.email || '';
    if (USER?.role === 'admin') document.getElementById('admin-nav').classList.remove('hidden');
    else document.getElementById('admin-nav').classList.add('hidden');
    try { await loadAllLists(); } catch(e) { console.warn('loadAllLists failed:', e); }
    try { await loadDashboard(); } catch(e) { console.warn('loadDashboard failed:', e); }
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
    const m = { dashboard: loadDashboard, contactlists: loadContactLists, contacts: loadContacts, lists: loadLists, templates: loadTemplates, campaigns: loadCampaigns, suppressions: loadSuppressions, reports: loadReports, cleaning: ()=>{}, ai: loadAI, users: loadUsers, domains: loadDomains, ippools: loadIPPools, admin: loadAdmin };
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
    display.onclick = () => {
        dropdown.classList.toggle('open');
        display.classList.toggle('ms-open', dropdown.classList.contains('open'));
    };

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

// --- Contact Lists ---
let clContactsPage = 0;
let currentListId = null;
let currentListName = null;
const CL_PER_PAGE = 50;

function showCLView(view) {
    ['list', 'upload', 'contact'].forEach(v =>
        document.getElementById('cl-' + v + '-view').classList.toggle('hidden', v !== view)
    );
    if (view === 'list') loadContactLists();
    if (view === 'upload') {
        document.getElementById('cl-upload-result').innerHTML = '';
        document.getElementById('cl-csv-file').value = '';
        document.getElementById('cl-list-name').value = '';
        document.getElementById('cl-split-check').checked = false;
        document.getElementById('cl-split-sub').classList.add('hidden');
        document.querySelector('input[name="cl-dup"][value="skip"]').checked = true;
    }
}

function toggleCLSplit() {
    document.getElementById('cl-split-sub').classList.toggle('hidden', !document.getElementById('cl-split-check').checked);
}

async function loadContactLists() {
    const search = (document.getElementById('cl-search')?.value || '').toLowerCase();
    await loadAllLists();
    const filtered = ALL_LISTS.filter(l => !search || l.name.toLowerCase().includes(search));
    document.getElementById('cl-tbody').innerHTML = filtered.length
        ? filtered.map(l => {
            const stream = l.stream || 'import';
            const badgeClass = stream === 'optin' ? 'optin' : stream === 'engaged' ? 'engaged' : stream === 'cold' ? 'cold' : 'draft';
            return `<tr>
                <td><strong>${l.name}</strong></td>
                <td class="text-muted">${l.source_file || '—'}</td>
                <td class="text-muted">${l.batch_number ? `${l.batch_number} / ${l.total_batches || l.batch_number}` : '—'}</td>
                <td>${(l.contact_count || 0).toLocaleString()}</td>
                <td><span class="badge ${badgeClass}">${stream}</span></td>
                <td>${new Date(l.created_at).toLocaleDateString()}</td>
                <td>
                    <button class="btn btn-secondary btn-sm" onclick="viewListContacts('${l._id}','${l.name}',${l.contact_count||0})">View</button>
                    <button class="btn btn-success btn-sm" onclick="exportListCSV('${l._id}')">Export</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteCLList('${l._id}','${l.name}')">Delete</button>
                </td>
            </tr>`;
          }).join('')
        : '<tr><td colspan="7" style="text-align:center;padding:24px;color:#888">No lists found. Upload a CSV to get started.</td></tr>';
}

async function viewListContacts(listId, listName, total) {
    currentListId = listId;
    currentListName = listName;
    clContactsPage = 0;
    document.getElementById('cl-view-title').textContent = listName;
    document.getElementById('cl-view-subtitle').textContent = `${total.toLocaleString()} contacts in this list`;
    document.getElementById('cl-export-btn').onclick = () => exportListCSV(listId);
    document.getElementById('cl-contact-search').value = '';
    showCLView('contact');
    await loadCLContacts();
}

async function loadCLContacts() {
    const search = (document.getElementById('cl-contact-search')?.value || '').trim();
    let url = `/contacts?limit=${CL_PER_PAGE}&skip=${clContactsPage * CL_PER_PAGE}&list_id=${currentListId}`;
    if (search) url += '&search=' + encodeURIComponent(search);
    const d = await api(url);
    document.getElementById('cl-contacts-tbody').innerHTML = d.contacts.length
        ? d.contacts.map(c => {
            const attrs = c.attributes || {};
            return `<tr>
                <td>${c.email}</td>
                <td>${[c.first_name, c.last_name].filter(Boolean).join(' ') || attrs.full_name || '—'}</td>
                <td>${attrs.phone || '—'}</td>
                <td>${attrs.company || '—'}</td>
                <td>${attrs.city || '—'}</td>
                <td><span class="badge ${c.status}">${c.status}</span></td>
            </tr>`;
          }).join('')
        : '<tr><td colspan="6" style="text-align:center;padding:24px;color:#888">No contacts found</td></tr>';

    const total = d.total;
    const totalPages = Math.ceil(total / CL_PER_PAGE) || 1;
    document.getElementById('cl-contacts-info').innerHTML =
        `<span>Page ${clContactsPage + 1} of ${totalPages} — ${total.toLocaleString()} total</span>
         ${clContactsPage > 0 ? `<button class="btn btn-secondary btn-sm" onclick="clContactsPage--;loadCLContacts()">Previous</button>` : ''}
         ${clContactsPage < totalPages - 1 ? `<button class="btn btn-secondary btn-sm" onclick="clContactsPage++;loadCLContacts()">Next</button>` : ''}`;
}

async function exportListCSV(listId) {
    try {
        const res = await api('/csv/export-contacts?list_id=' + listId);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'contacts_list.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (e) {
        toast('Export failed: ' + e.message, 'error');
    }
}

async function deleteCLList(listId, listName) {
    if (!confirm(`Delete list "${listName}"? Contacts will be kept but removed from this list.`)) return;
    await api(`/lists/${listId}/delete`, { method: 'DELETE' });
    toast(`List "${listName}" deleted`);
    loadContactLists();
}

async function uploadAndSplit(btn) {
    const file = document.getElementById('cl-csv-file').files[0];
    if (!file) return toast('Please select a CSV file', 'error');

    let name = document.getElementById('cl-list-name').value.trim();
    if (!name) name = file.name.replace(/\.csv$/i, '').replace(/[^a-zA-Z0-9_\-]/g, '_');

    const stream = document.getElementById('cl-stream').value;
    const doSplit = document.getElementById('cl-split-check').checked;
    const splitSize = parseInt(document.getElementById('cl-split-size').value) || 10000;
    const dupAction = document.querySelector('input[name="cl-dup"]:checked').value;

    const form = new FormData();
    form.append('file', file);
    form.append('name_prefix', name);
    form.append('stream', stream);
    form.append('do_split', doSplit);
    form.append('split_size', splitSize);
    form.append('duplicate_action', dupAction);

    btn.disabled = true;
    btn.textContent = 'Uploading…';
    document.getElementById('cl-upload-result').innerHTML = '';

    try {
        const res = await authFetch('/csv/upload-and-split', {
            method: 'POST',
            body: form,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Upload failed');

        const dupLine = data.total_added_to_list > 0
            ? `<span class="badge sending">Added to list: ${data.total_added_to_list}</span> `
            : '';
        document.getElementById('cl-upload-result').innerHTML = `
            <div class="import-success">
                <strong>Upload complete!</strong><br><br>
                <span class="badge active">Imported: ${data.total_imported}</span>
                ${dupLine}<span class="badge cold">Skipped: ${data.total_skipped}</span>
                <span class="badge draft">Lists created: ${data.batches}</span>
                <br><br>
                ${data.lists.map(l => `<div style="font-size:12px;margin-top:4px">✓ <strong>${l.list_name}</strong> — ${l.imported} new, ${l.added_to_list} added to list, ${l.skipped} skipped</div>`).join('')}
            </div>`;
        toast(`${data.total_imported} contacts imported into ${data.batches} list(s)`);
        await loadAllLists();
    } catch (e) {
        toast('Upload failed: ' + e.message, 'error');
        document.getElementById('cl-upload-result').innerHTML = `<div style="color:red;font-size:13px;margin-top:8px">${e.message}</div>`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Upload and Import';
    }
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
        const res = await authFetch('/csv/import-contacts', { method: 'POST', body: form });
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
            <button class="btn btn-primary btn-sm" onclick="openAddToListModal('${l._id}','${l.name}')">Add Contacts</button>
            <button class="btn btn-danger btn-sm" onclick="deleteList('${l._id}','${l.name}',false)">Delete</button>
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

function openAddToListModal(listId, listName) {
    const sel = document.getElementById('atl-list');
    sel.innerHTML = `<option value="${listId}">${listName}</option>`;
    document.getElementById('atl-result').innerHTML = '';
    openModal('add-to-list-modal');
}

function switchATLTab(tab, el) {
    document.querySelectorAll('#add-to-list-modal .tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    document.getElementById('atl-all-tab').classList.toggle('hidden', tab !== 'all');
    document.getElementById('atl-filter-tab').classList.toggle('hidden', tab !== 'filter');
    document.getElementById('atl-manual-tab').classList.toggle('hidden', tab !== 'manual');
}

async function addContactsToList() {
    const listId = document.getElementById('atl-list').value;
    let emails = [];

    try {
        if (!document.getElementById('atl-manual-tab').classList.contains('hidden')) {
            const text = document.getElementById('atl-emails').value;
            emails = text.split(/[\n,]/).map(e => e.trim()).filter(e => e && e.includes('@'));
        } else if (!document.getElementById('atl-filter-tab').classList.contains('hidden')) {
            const stream = document.getElementById('atl-stream').value;
            const d = await api(`/contacts?stream=${stream}&limit=5000`);
            emails = d.contacts.map(c => c.email);
        } else {
            const d = await api('/contacts?limit=5000');
            emails = d.contacts.map(c => c.email);
        }

        if (emails.length === 0) return toast('No contacts found', 'error');

        const d = await api(`/lists/${listId}/contacts`, { method: 'POST', body: JSON.stringify(emails) });
        document.getElementById('atl-result').innerHTML = `<div class="import-success"><span class="badge active">Matched: ${d.matched}</span> <span class="badge active">Added: ${d.modified}</span></div>`;
        toast(`${d.modified} contacts added to list`);
        loadLists();
    } catch (e) {
        toast('Error: ' + e.message, 'error');
    }
}

// --- Templates ---
async function loadTemplates() {
    const d = await api('/templates');
    ALL_TEMPLATES = d.templates || [];
    document.getElementById('templates-tbody').innerHTML = ALL_TEMPLATES.map(t => `<tr>
        <td>${t.name}</td><td><span class="badge">${t.category}</span></td><td>${t.subject}</td>
        <td>${new Date(t.created_at).toLocaleDateString()}</td>
        <td>
            <button class="btn btn-secondary btn-sm" onclick="viewTemplate('${t._id}')">View</button>
            <button class="btn btn-secondary btn-sm" onclick="editTemplate('${t._id}')">Edit</button>
            <button class="btn btn-secondary btn-sm" onclick="cloneTemplate('${t._id}','${t.name}')">Clone</button>
            <button class="btn btn-danger btn-sm" onclick="deleteTemplate('${t._id}')">Del</button>
        </td>
    </tr>`).join('');
}

function openNewTemplateModal() {
    editingTemplateId = null;
    document.querySelector('#template-modal h2').textContent = 'Create Template';
    ['tpl-name','tpl-subject','tpl-preheader','tpl-html'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('tpl-cat').value = 'other';
    const prev = document.getElementById('tpl-preview');
    prev.classList.add('hidden'); prev.innerHTML = '';
    openModal('template-modal');
}

async function editTemplate(id) {
    const t = await api('/templates/' + id);
    editingTemplateId = id;
    document.querySelector('#template-modal h2').textContent = 'Edit Template';
    document.getElementById('tpl-name').value = t.name || '';
    document.getElementById('tpl-cat').value = t.category || 'other';
    document.getElementById('tpl-subject').value = t.subject || '';
    document.getElementById('tpl-preheader').value = t.preheader || '';
    document.getElementById('tpl-html').value = t.html_body || '';
    const prev = document.getElementById('tpl-preview');
    prev.classList.add('hidden'); prev.innerHTML = '';
    openModal('template-modal');
}

async function viewTemplate(id) {
    const t = await api('/templates/' + id);
    window._viewingTplId = id;
    document.getElementById('vtpl-title').textContent = t.name;
    document.getElementById('vtpl-subject').textContent = `Subject: ${t.subject}`;
    const html = (t.html_body || '')
        .replace(/\{\{first_name\}\}/g, 'John')
        .replace(/\{\{last_name\}\}/g, 'Doe')
        .replace(/\{\{email\}\}/g, 'john@example.com');
    document.getElementById('vtpl-frame').srcdoc = html;
    openModal('view-template-modal');
}

async function createTemplate() {
    const body = {
        name: document.getElementById('tpl-name').value,
        category: document.getElementById('tpl-cat').value,
        subject: document.getElementById('tpl-subject').value,
        preheader: document.getElementById('tpl-preheader').value,
        html_body: document.getElementById('tpl-html').value,
    };
    if (editingTemplateId) {
        await api(`/templates/${editingTemplateId}`, { method: 'PUT', body: JSON.stringify(body) });
        toast('Template updated');
    } else {
        await api('/templates', { method: 'POST', body: JSON.stringify(body) });
        toast('Template created');
    }
    editingTemplateId = null;
    document.querySelector('#template-modal h2').textContent = 'Create Template';
    closeModal('template-modal');
    loadTemplates();
}

function previewTemplate() {
    const html = document.getElementById('tpl-html').value
        .replace(/\{\{first_name\}\}/g, 'John')
        .replace(/\{\{last_name\}\}/g, 'Doe')
        .replace(/\{\{email\}\}/g, 'john@example.com');
    const el = document.getElementById('tpl-preview');
    el.classList.remove('hidden');
    el.innerHTML = `<iframe srcdoc="${html.replace(/"/g, '&quot;')}" style="width:100%;height:400px;border:none;border-radius:8px;display:block"></iframe>`;
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
    const [d] = await Promise.all([
        api('/campaigns'),
        loadAllLists(),
        api('/templates').then(t => { ALL_TEMPLATES = t.templates || []; }),
    ]);
    document.getElementById('campaigns-tbody').innerHTML = d.campaigns.map(c => {
        const s = c.stats || {};

        let actions = '';
        if (c.status === 'draft' || c.status === 'scheduled') actions += `<button class="btn btn-success btn-sm" onclick="launchCampaign('${c._id}')">Launch</button> `;
        else if (c.status === 'sending') actions += `<button class="btn btn-secondary btn-sm" onclick="pauseCampaign('${c._id}')">Pause</button> `;
        else if (c.status === 'paused') actions += `<button class="btn btn-primary btn-sm" onclick="resumeCampaign('${c._id}')">Resume</button> `;
        actions += `<button class="btn btn-secondary btn-sm" onclick="duplicateCampaign('${c._id}')">Clone</button> `;
        actions += `<button class="btn btn-secondary btn-sm" onclick="showCampaignDetails('${c._id}')">Details</button> `;
        if (c.status !== 'sending') {
            if (USER?.role === 'admin') actions += `<button class="btn btn-danger btn-sm" onclick="deleteCampaign('${c._id}')">Del</button>`;
            else actions += `<button class="btn btn-secondary btn-sm" onclick="archiveCampaign('${c._id}')">Archive</button>`;
        }

        const sentDate = c.completed_at
            ? new Date(c.completed_at).toLocaleDateString('en-IN', {day:'2-digit',month:'short',year:'2-digit'})
            : (c.status === 'draft' || c.status === 'scheduled') ? '—'
            : new Date(c.created_at).toLocaleDateString('en-IN', {day:'2-digit',month:'short',year:'2-digit'});

        const archived = c.archived ? ' <span class="badge suppressed">archived</span>' : '';
        const total = s.total_recipients || 0;
        const processed = (s.sent||0) + (s.bounced||0) + (s.skipped||0);
        const pct = total > 0 ? Math.min(100, Math.round(processed / total * 100)) : 0;
        const progressBar = (c.status === 'sending' && total > 0) ? `
            <div style="margin-top:4px;font-size:11px;color:var(--muted)">${processed}/${total} &nbsp;${pct}%</div>
            <div style="height:4px;background:var(--border);border-radius:2px;margin-top:3px;min-width:80px">
                <div style="height:100%;width:${pct}%;background:var(--primary);border-radius:2px"></div>
            </div>` : '';
        const statusCell = `<span class="badge ${c.status}">${c.status}</span>${progressBar}`;

        return `<tr>
            <td>${c.name}${archived}</td>
            <td><span class="badge ${c.stream}">${c.stream}</span></td>
            <td style="min-width:120px">${statusCell}</td>
            <td>${s.sent||0}/${total}</td>
            <td>${s.opened||0}</td>
            <td>${s.bounced||0}</td>
            <td style="white-space:nowrap;font-size:12px;color:#6b7280">${sentDate}</td>
            <td style="white-space:nowrap">${actions}</td>
        </tr>`;
    }).join('');
    ['report-campaign','ai-camp'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<option value="">Select...</option>' + d.campaigns.map(c => `<option value="${c._id}">${c.name} (${c.status})</option>`).join('');
    });
    // Auto-refresh while any campaign is sending
    clearTimeout(window._campRefreshTimer);
    if (d.campaigns.some(c => c.status === 'sending')) {
        window._campRefreshTimer = setTimeout(() => {
            if (document.getElementById('campaigns-tbody')) loadCampaigns();
        }, 4000);
    }
}

async function openCampaignModal() {
    await loadAllLists();
    const tplData = await api('/templates');
    const tplSel = document.getElementById('camp-tpl');
    tplSel.innerHTML = '<option value="">— None (custom) —</option>' + tplData.templates.map(t => `<option value="${t._id}" data-subject="${t.subject}" data-preheader="${t.preheader||''}" data-html="${encodeURIComponent(t.html_body)}">${t.name}</option>`).join('');
    filterCampLists();
    openModal('campaign-modal');
}

function updateFromPreview() {
    const local = (document.getElementById('camp-from-local').value || 'hello').trim();
    const domain = document.getElementById('camp-from-domain').value;
    document.getElementById('camp-from-preview').textContent = `${local}@${domain}`;
}

function filterCampLists() {
    const stream = document.getElementById('camp-stream').value;
    const filtered = ALL_LISTS.filter(l => l.stream === stream);
    const listOpts = filtered.map(l => ({ value: l._id, label: `${l.name} (${(l.contact_count||0).toLocaleString()})` }));
    createMultiSelect('camp-lists-ms', listOpts, `Select ${stream} lists...`);

    const totalContacts = filtered.reduce((s, l) => s + (l.contact_count || 0), 0);
    document.getElementById('camp-lists-info').textContent = filtered.length
        ? `${filtered.length} list${filtered.length > 1 ? 's' : ''} available — ${totalContacts.toLocaleString()} total contacts`
        : `No ${stream} lists found. Upload a CSV with ${stream} stream first.`;
}

function selectAllCampLists() {
    document.querySelectorAll('#camp-lists-ms input[type="checkbox"]').forEach(c => c.checked = true);
    updateMultiSelectDisplay('camp-lists-ms', 'Select target lists...');
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
        from_email: `${(document.getElementById('camp-from-local').value || 'hello').trim()}@${document.getElementById('camp-from-domain').value}`,
        stream: document.getElementById('camp-stream').value,
        target_list_ids: listIds,
        html_body: document.getElementById('camp-html').value,
        auto_suppress: document.getElementById('camp-auto-suppress').checked,
        scheduled_at: schedule ? new Date(schedule).toISOString() : undefined,
    };
    await api('/campaigns', { method: 'POST', body: JSON.stringify(body) });
    closeModal('campaign-modal');
    toast('Campaign created');
    loadCampaigns();
}

async function duplicateCampaign(id) {
    const camp = await api('/campaigns/' + id);
    await loadAllLists();
    const tplData = await api('/templates');
    const tplSel = document.getElementById('camp-tpl');
    tplSel.innerHTML = '<option value="">— None (custom) —</option>' + tplData.templates.map(t => `<option value="${t._id}" data-subject="${t.subject}" data-preheader="${t.preheader||''}" data-html="${encodeURIComponent(t.html_body)}">${t.name}</option>`).join('');

    document.getElementById('camp-name').value = camp.name + ' (copy)';
    document.getElementById('camp-stream').value = camp.stream || 'cold';
    filterCampLists();

    document.getElementById('camp-subject').value = camp.subject || '';
    document.getElementById('camp-preheader').value = camp.preheader || '';
    document.getElementById('camp-from-name').value = camp.from_name || '';
    const [localPart, domainPart] = (camp.from_email || '@').split('@');
    document.getElementById('camp-from-local').value = localPart || '';
    const domainSel = document.getElementById('camp-from-domain');
    if ([...domainSel.options].some(o => o.value === domainPart)) domainSel.value = domainPart;
    updateFromPreview();

    document.getElementById('camp-html').value = camp.html_body || '';
    document.getElementById('camp-auto-suppress').checked = camp.auto_suppress !== false;
    document.getElementById('camp-schedule').value = '';

    if (camp.template_id) tplSel.value = camp.template_id;

    if (camp.target_list_ids?.length) {
        setTimeout(() => {
            camp.target_list_ids.forEach(listId => {
                const cb = document.querySelector(`#camp-lists-ms input[value="${listId}"]`);
                if (cb) cb.checked = true;
            });
            updateMultiSelectDisplay('camp-lists-ms', 'Select target lists...');
        }, 50);
    }

    openModal('campaign-modal');
}

async function showCampaignDetails(id) {
    const camp = await api('/campaigns/' + id);
    const listNames = (camp.target_list_ids || []).map(lid => {
        const l = ALL_LISTS.find(l => l._id === lid);
        return l ? `${l.name} (${(l.contact_count||0).toLocaleString()})` : lid;
    }).join('<br>') || '—';
    const tplName = camp.template_id
        ? (ALL_TEMPLATES.find(t => t._id === camp.template_id)?.name || 'Template')
        : '—';
    document.getElementById('cdm-title').textContent = camp.name;
    document.getElementById('cdm-body').innerHTML = `
        <table style="width:100%;font-size:13px;border-collapse:collapse">
            <tr><td style="padding:7px 0;color:#6b7280;width:90px">From</td><td style="padding:7px 0;font-weight:500">${camp.from_name ? camp.from_name + ' &lt;' + (camp.from_email||'') + '&gt;' : (camp.from_email||'—')}</td></tr>
            <tr style="border-top:1px solid #f3f4f6"><td style="padding:7px 0;color:#6b7280">Template</td><td style="padding:7px 0;font-weight:500">${tplName}</td></tr>
            <tr style="border-top:1px solid #f3f4f6"><td style="padding:7px 0;color:#6b7280;vertical-align:top">Lists</td><td style="padding:7px 0;font-weight:500;line-height:1.8">${listNames}</td></tr>
        </table>`;
    openModal('camp-details-modal');
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

async function saveContact() {
    const email = document.getElementById('nc-email').value.trim();
    if (!email) return toast('Email is required', 'error');
    try {
        await api('/contacts', {method:'POST', body:JSON.stringify({
            email,
            first_name: document.getElementById('nc-first').value.trim(),
            last_name: document.getElementById('nc-last').value.trim(),
            stream: document.getElementById('nc-stream').value,
        })});
        closeModal('add-contact-modal');
        document.getElementById('nc-email').value = '';
        document.getElementById('nc-first').value = '';
        document.getElementById('nc-last').value = '';
        toast('Contact added');
        loadContacts();
    } catch (e) {
        toast(e.message || 'Failed to add contact', 'error');
    }
}

async function addSuppression() {
    const email = document.getElementById('sup-email').value.trim();
    if (!email) return toast('Email is required', 'error');
    try {
        await api('/suppressions', {method:'POST', body:JSON.stringify({email, reason:document.getElementById('sup-reason').value})});
        closeModal('sup-modal');
        document.getElementById('sup-email').value = '';
        toast('Email suppressed');
        loadSuppressions();
    } catch (e) {
        toast(e.message || 'Failed to suppress email', 'error');
    }
}

async function bulkSuppressCSV() {
    const file = document.getElementById('sup-bulk-file').files[0];
    if (!file) return toast('Select a CSV file first', 'error');

    const reason = document.getElementById('sup-bulk-reason').value;
    const resultEl = document.getElementById('sup-bulk-result');
    resultEl.innerHTML = `<span class="loading"></span> Uploading...`;

    const form = new FormData();
    form.append('file', file);
    form.append('reason', reason);

    const res = await authFetch('/suppressions/bulk-csv', {
        method: 'POST',
        body: form,
    });
    const data = await res.json();

    resultEl.innerHTML = `<div class="import-success"><span class="badge suppressed">Suppressed: ${data.added}</span> <span class="badge cold">Already suppressed: ${data.skipped}</span></div>`;
    toast(`${data.added} emails suppressed from CSV`);
    loadSuppressions();
    document.getElementById('sup-bulk-file').value = '';
    setTimeout(() => closeModal('sup-bulk-modal'), 2000);
}

async function removeSup(email) {
    if (!confirm('Remove ' + email + ' from suppression list?')) return;
    try {
        await api('/suppressions?email=' + encodeURIComponent(email), {method: 'DELETE'});
        toast('Suppression removed');
        loadSuppressions();
    } catch (e) {
        toast('Remove failed: ' + e.message, 'error');
    }
}

async function backfillHardBounces() {
    if (!confirm('Scan all bounce events and suppress any hard-bounce emails not yet in the list?')) return;
    const d = await api('/admin/backfill-hard-bounces', {method:'POST'});
    toast(`Backfill done — added: ${d.added}, already suppressed: ${d.already_suppressed}, total bounce events: ${d.total_hard_bounces_in_events}`);
    loadSuppressions();
}

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
    const r = d.rates || {};
    const total = s.total_recipients || 0;
    const processed = (s.sent||0) + (s.bounced||0) + (s.skipped||0);
    const pct = total > 0 ? Math.min(100, Math.round(processed / total * 100)) : 0;
    document.getElementById('report-detail').innerHTML = `
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
            <span class="badge ${d.status}">${d.status}</span>
            <span class="badge ${d.stream}">${d.stream}</span>
            ${d.started_at ? `<span class="text-muted">Started: ${new Date(d.started_at).toLocaleString()}</span>` : ''}
            ${d.completed_at ? `<span class="text-muted">Completed: ${new Date(d.completed_at).toLocaleString()}</span>` : ''}
        </div>
        ${total > 0 ? `<div style="margin-bottom:14px">
            <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-bottom:4px">
                <span>Progress: ${processed} / ${total} processed</span><span>${pct}%</span>
            </div>
            <div style="height:6px;background:var(--border);border-radius:3px;overflow:hidden">
                <div style="height:100%;width:${pct}%;background:var(--primary);border-radius:3px;transition:width .4s"></div>
            </div>
        </div>` : ''}
        <div class="stats-grid" style="grid-template-columns:repeat(auto-fit,minmax(110px,1fr))">
            <div class="stat-card">
                <div class="label">Sent</div>
                <div class="value blue">${(s.sent||0).toLocaleString()}</div>
                <div class="rate">of ${total.toLocaleString()} total</div>
            </div>
            <div class="stat-card">
                <div class="label">Delivered</div>
                <div class="value green">${(s.delivered||0).toLocaleString()}</div>
                <div class="rate">${r.delivery_rate||'0%'}</div>
            </div>
            <div class="stat-card">
                <div class="label">Opened</div>
                <div class="value green">${(s.opened||0).toLocaleString()}</div>
                <div class="rate">${r.open_rate||'0%'}</div>
            </div>
            <div class="stat-card">
                <div class="label">Clicked</div>
                <div class="value blue">${(s.clicked||0).toLocaleString()}</div>
                <div class="rate">${r.click_rate||'0%'}</div>
            </div>
            <div class="stat-card">
                <div class="label">Bounced</div>
                <div class="value orange">${(s.bounced||0).toLocaleString()}</div>
                <div class="rate">${r.bounce_rate||'0%'}</div>
            </div>
            <div class="stat-card">
                <div class="label">Suppressed</div>
                <div class="value" style="color:var(--muted)">${(s.skipped||0).toLocaleString()}</div>
                <div class="rate">skipped at send</div>
            </div>
            <div class="stat-card">
                <div class="label">Unsubscribed</div>
                <div class="value red">${(s.unsubscribed||0).toLocaleString()}</div>
                <div class="rate">${r.unsubscribe_rate||'0%'}</div>
            </div>
            <div class="stat-card">
                <div class="label">Complaints</div>
                <div class="value red">${(s.complained||0).toLocaleString()}</div>
                <div class="rate">${r.complaint_rate||'0%'}</div>
            </div>
        </div>
        <div class="btn-row mt-2">
            <button class="btn btn-secondary btn-sm" onclick="exportCSV('campaign/${id}')">Export CSV</button>
            <button class="btn btn-primary btn-sm" onclick="loadRecipientList('${id}','sent')">Sent</button>
            <button class="btn btn-primary btn-sm" onclick="loadRecipientList('${id}','opened')">Opened</button>
            <button class="btn btn-success btn-sm" onclick="loadRecipientList('${id}','clicked')">Clicked</button>
            <button class="btn btn-secondary btn-sm" onclick="loadRecipientList('${id}','bounced')">Bounced</button>
            <button class="btn btn-secondary btn-sm" onclick="loadRecipientList('${id}','skipped')">Suppressed</button>
            <button class="btn btn-danger btn-sm" onclick="loadRecipientList('${id}','complained')">Complaints</button>
        </div>
        <div id="recipient-list-${id}" class="mt-2"></div>`;
}

async function loadRecipientList(campaignId, eventType) {
    const el = document.getElementById(`recipient-list-${campaignId}`);
    el.innerHTML = '<span class="loading"></span>';
    const d = await api(`/reports/campaign/${campaignId}/recipients?event_type=${eventType}&limit=100`);
    const label = { sent: 'Sent', opened: 'Opened', clicked: 'Clicked', bounced: 'Bounced', skipped: 'Suppressed', complained: 'Complaints', delivered: 'Delivered' }[eventType] || eventType;
    el.innerHTML = `<div class="card mt-2">
        <h2 style="font-size:14px;margin-bottom:12px">${label} — ${d.total} contacts</h2>
        ${d.events.length ? `<div style="overflow-x:auto"><table>
            <thead><tr><th>Email</th><th>Detail</th><th>Date</th></tr></thead>
            <tbody>${d.events.map(e=>`<tr>
                <td>${e.email || '<span class="text-muted">—</span>'}</td>
                <td class="text-muted" style="font-size:12px">${e.bounce_message||e.reason||e.click_url||''}</td>
                <td class="text-muted" style="white-space:nowrap">${new Date(e.created_at).toLocaleString()}</td>
            </tr>`).join('')}</tbody>
        </table></div>
        ${d.total > 100 ? `<p class="text-muted mt-1">Showing first 100 of ${d.total}. Export CSV for full list.</p>` : ''}` : '<p class="text-muted">No records found.</p>'}
    </div>`;
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

function switchCleanTab(tab, el) {
    document.querySelectorAll('#page-cleaning .tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    document.getElementById('clean-paste-tab').classList.toggle('hidden', tab !== 'paste');
    document.getElementById('clean-csv-tab').classList.toggle('hidden', tab !== 'csv');
}

async function bulkCleanCSV() {
    const file = document.getElementById('clean-csv-file').files[0];
    if (!file) return toast('Select a CSV file first', 'error');

    const form = new FormData();
    form.append('file', file);

    const res = await fetch('/cleaning/bulk-csv', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + TOKEN },
        body: form,
    });
    const d = await res.json();
    const s = d.summary;
    document.getElementById('bulk-result').innerHTML = `<div class="stats-grid mt-2"><div class="stat-card"><div class="label">Valid</div><div class="value green">${s.valid}</div></div><div class="stat-card"><div class="label">Invalid</div><div class="value red">${s.invalid_syntax}</div></div><div class="stat-card"><div class="label">No MX</div><div class="value red">${s.no_mx}</div></div><div class="stat-card"><div class="label">Disposable</div><div class="value orange">${s.disposable}</div></div><div class="stat-card"><div class="label">Role</div><div class="value orange">${s.role}</div></div><div class="stat-card"><div class="label">Duplicate</div><div class="value">${s.duplicate}</div></div></div>`;
    toast(`Cleaned ${Object.values(s).reduce((a,b)=>a+b,0)} emails from CSV`);
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
        <td>
            <button class="btn btn-secondary btn-sm" onclick="openResetPasswordModal('${u._id}', '${u.email}')">Reset PW</button>
            <button class="btn btn-danger btn-sm" onclick="deleteUser('${u._id}', '${u.email}')">Delete</button>
        </td>
    </tr>`).join('');
}
async function createUser() {
    await api('/auth/users', {method:'POST', body:JSON.stringify({email:document.getElementById('usr-email').value, name:document.getElementById('usr-name').value, password:document.getElementById('usr-pass').value, role:document.getElementById('usr-role').value})});
    closeModal('user-modal'); toast('User created'); loadUsers();
}
function openResetPasswordModal(id, email) {
    document.getElementById('reset-pw-user-id').value = id;
    document.getElementById('reset-pw-label').textContent = 'Reset password for: ' + email;
    document.getElementById('reset-pw-new').value = '';
    document.getElementById('reset-pw-confirm').value = '';
    openModal('reset-pw-modal');
}
async function confirmResetPassword() {
    const id = document.getElementById('reset-pw-user-id').value;
    const newPw = document.getElementById('reset-pw-new').value;
    const confirmPw = document.getElementById('reset-pw-confirm').value;
    if (!newPw) return toast('Enter a new password', 'error');
    if (newPw !== confirmPw) return toast('Passwords do not match', 'error');
    if (newPw.length < 6) return toast('Password must be at least 6 characters', 'error');
    await api('/auth/users/'+id+'/reset-password', {method:'POST', body:JSON.stringify({new_password:newPw})});
    closeModal('reset-pw-modal'); toast('Password updated');
}
async function deleteUser(id, email) {
    if (!confirm('Delete user ' + email + '? This cannot be undone.')) return;
    await api('/auth/users/'+id, {method:'DELETE'});
    toast('User deleted'); loadUsers();
}

// --- CSV Export ---
async function exportCSV(type) {
    try {
        const res = await api('/csv/export-' + type);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = type.replace('/', '_') + '.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (e) {
        toast('Export failed: ' + e.message, 'error');
    }
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
        </tbody></table>
        <div class="btn-row" style="margin-top:16px">
            <button class="btn btn-secondary btn-sm" onclick="repairBounceEmails()">Repair Bounce Emails</button>
        </div>`;
}

async function repairBounceEmails() {
    if (!confirm('Match empty-email bounce events to sent events by postal_message_id?')) return;
    try {
        const d = await api('/admin/repair-bounce-emails', {method: 'POST'});
        toast(`Repaired ${d.fixed} of ${d.total_empty} empty bounce emails`);
    } catch (e) {
        toast('Repair failed: ' + e.message, 'error');
    }
}

// --- Init ---
document.getElementById('login-password').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
if (TOKEN && USER) showApp();
