/**
 * APU Marketplace — SPA Principal
 * Vanilla JS, sin frameworks. PWA-ready.
 */

// ── State ──────────────────────────────────────────────────────
const state = {
    user: null,
    token: null,
    refreshToken: null,
    currentPage: 'dashboard',
};

// ── API Client ─────────────────────────────────────────────────
const API_BASE = '/api/v1';

const API = {
    async _fetch(path, opts = {}) {
        const headers = { 'Content-Type': 'application/json', ...opts.headers };
        if (state.token) headers['Authorization'] = `Bearer ${state.token}`;

        const resp = await fetch(`${API_BASE}${path}`, { ...opts, headers });

        if (resp.status === 401 && state.refreshToken) {
            const refreshed = await this._refresh();
            if (refreshed) {
                headers['Authorization'] = `Bearer ${state.token}`;
                return fetch(`${API_BASE}${path}`, { ...opts, headers });
            }
            logout();
            return resp;
        }
        return resp;
    },

    async _refresh() {
        try {
            const resp = await fetch(`${API_BASE}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: state.refreshToken }),
            });
            if (!resp.ok) return false;
            const data = await resp.json();
            state.token = data.access_token;
            state.refreshToken = data.refresh_token;
            localStorage.setItem('_mkt_token', state.token);
            localStorage.setItem('_mkt_refresh', state.refreshToken);
            return true;
        } catch { return false; }
    },

    async get(path) { return (await this._fetch(path)).json(); },
    async post(path, body) {
        return (await this._fetch(path, { method: 'POST', body: JSON.stringify(body) })).json();
    },
    async put(path, body) {
        return (await this._fetch(path, { method: 'PUT', body: JSON.stringify(body) })).json();
    },
    async del(path) { return (await this._fetch(path, { method: 'DELETE' })).json(); },
    async upload(path, formData) {
        const headers = {};
        if (state.token) headers['Authorization'] = `Bearer ${state.token}`;
        return (await fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: formData })).json();
    },

    // Auth
    login: (email, password) => API.post('/auth/login', { email, password }),
    register: (data) => API.post('/auth/register', data),

    // Suppliers
    suppliers: (params = '') => API.get(`/suppliers${params}`),
    supplier: (id) => API.get(`/suppliers/${id}`),
    createSupplier: (data) => API.post('/suppliers', data),
    updateSupplier: (id, data) => API.put(`/suppliers/${id}`, data),

    // Quotations
    quotations: (params = '') => API.get(`/quotations${params}`),
    quotation: (id) => API.get(`/quotations/${id}`),
    createQuotation: (data) => API.post('/quotations', data),
    processQuotation: (id) => API.post(`/quotations/${id}/process`),
    uploadQuotation: (formData) => API.upload('/quotations/upload', formData),

    // Prices
    publicPrices: (params = '') => API.get(`/prices/public${params}`),
    searchPrices: (q, region) => API.get(`/prices/public/search?q=${encodeURIComponent(q)}${region ? '&region=' + region : ''}`),
    insumos: (params = '') => API.get(`/prices${params}`),
    insumo: (id) => API.get(`/prices/${id}`),
    createInsumo: (data) => API.post('/prices', data),
    categories: () => API.get('/prices/categories/list'),
    regions: () => API.get('/prices/regions/list'),

    // RFQ
    rfqs: (params = '') => API.get(`/rfq${params}`),
    rfq: (id) => API.get(`/rfq/${id}`),
    createRFQ: (data) => API.post('/rfq', data),
    sendRFQ: (id) => API.post(`/rfq/${id}/send`),

    // Admin
    stats: () => API.get('/admin/stats'),
};

// ── Router ─────────────────────────────────────────────────────
const PAGES = {
    dashboard: { title: 'Dashboard', icon: 'home', render: renderDashboard },
    prices: { title: 'Precios', icon: 'tag', render: renderPrices },
    suppliers: { title: 'Proveedores', icon: 'users', render: renderSuppliers },
    quotations: { title: 'Cotizaciones', icon: 'file-text', render: renderQuotations },
    rfq: { title: 'RFQ', icon: 'send', render: renderRFQ },
};

function navigate(page) {
    state.currentPage = page;
    renderApp();
}

// ── Icons (inline SVG) ─────────────────────────────────────────
const ICONS = {
    home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9,22 9,12 15,12 15,22"/></svg>',
    tag: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>',
    users: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4-4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>',
    'file-text': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22,2 15,22 11,13 2,9"/></svg>',
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
    upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17,8 12,3 7,8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
    logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16,17 21,12 16,7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
};

function icon(name, size = 20) {
    return `<span class="icon" style="width:${size}px;height:${size}px;display:inline-flex">${ICONS[name] || ''}</span>`;
}

// ── Render: App shell ──────────────────────────────────────────
function renderApp() {
    const app = document.getElementById('app');
    if (!state.user) {
        renderLogin();
        return;
    }

    app.innerHTML = `
        ${renderTopbar()}
        <div class="app-container">
            <div class="page" id="page-content"></div>
        </div>
        ${renderBottombar()}
        <div id="toast-container" class="toast-container"></div>
    `;

    const pageConfig = PAGES[state.currentPage];
    if (pageConfig) pageConfig.render();

    // Update active tab
    document.querySelectorAll('.bottombar-item').forEach(el => {
        el.classList.toggle('active', el.dataset.page === state.currentPage);
    });
}

function renderTopbar() {
    return `
        <div class="topbar">
            <div class="topbar-logo">
                <svg width="32" height="32" viewBox="0 0 48 48" fill="none">
                    <rect width="48" height="48" rx="10" fill="rgba(255,255,255,0.2)"/>
                    <path d="M12 36V16l12-6 12 6v20" stroke="white" stroke-width="2.5" fill="none"/>
                    <path d="M20 36V26h8v10" stroke="white" stroke-width="2"/>
                </svg>
                APU MKT
            </div>
            <div class="topbar-spacer"></div>
            <div class="topbar-actions">
                <span class="topbar-user">${state.user.full_name}</span>
                <button class="topbar-btn" onclick="logout()" title="Cerrar sesion">
                    ${icon('logout', 18)}
                </button>
            </div>
        </div>
    `;
}

function renderBottombar() {
    const items = Object.entries(PAGES).map(([key, cfg]) => `
        <button class="bottombar-item${state.currentPage === key ? ' active' : ''}"
                data-page="${key}" onclick="navigate('${key}')">
            ${icon(cfg.icon, 22)}
            <span>${cfg.title}</span>
        </button>
    `).join('');
    return `<div class="bottombar">${items}</div>`;
}

// ── Render: Login ──────────────────────────────────────────────
function renderLogin() {
    const app = document.getElementById('app');
    app.innerHTML = `
        <div class="login-page">
            <div class="login-card">
                <div class="login-logo">
                    <svg width="64" height="64" viewBox="0 0 48 48" fill="none">
                        <rect width="48" height="48" rx="10" fill="#1e40af"/>
                        <path d="M12 36V16l12-6 12 6v20" stroke="white" stroke-width="2.5" fill="none"/>
                        <path d="M20 36V26h8v10" stroke="white" stroke-width="2"/>
                    </svg>
                </div>
                <h1 class="login-title">APU Marketplace</h1>
                <p class="login-subtitle">Portal de Precios Unitarios de Construccion</p>
                <form id="login-form" onsubmit="handleLogin(event)">
                    <div class="form-group">
                        <label class="form-label">Email</label>
                        <input class="form-input" type="email" name="email" required placeholder="correo@empresa.com">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Contrasena</label>
                        <input class="form-input" type="password" name="password" required placeholder="********">
                    </div>
                    <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;padding:10px">
                        Iniciar Sesion
                    </button>
                </form>
                <div class="login-footer">
                    No tienes cuenta? <a href="#" onclick="showRegister(event)">Registrate</a>
                </div>
            </div>
        </div>
    `;
}

async function handleLogin(e) {
    e.preventDefault();
    const form = e.target;
    const email = form.email.value;
    const password = form.password.value;

    try {
        const data = await API.login(email, password);
        if (data.access_token) {
            state.token = data.access_token;
            state.refreshToken = data.refresh_token;
            state.user = data.user;
            localStorage.setItem('_mkt_token', state.token);
            localStorage.setItem('_mkt_refresh', state.refreshToken);
            localStorage.setItem('_mkt_user', JSON.stringify(state.user));
            renderApp();
        } else {
            toast(data.detail || 'Error al iniciar sesion', 'error');
        }
    } catch (err) {
        toast('Error de conexion', 'error');
    }
}

function showRegister(e) {
    e && e.preventDefault();
    showModal('Registrarse', `
        <form id="register-form" onsubmit="handleRegister(event)">
            <div class="form-group">
                <label class="form-label">Nombre completo</label>
                <input class="form-input" name="full_name" required>
            </div>
            <div class="form-group">
                <label class="form-label">Email</label>
                <input class="form-input" type="email" name="email" required>
            </div>
            <div class="form-group">
                <label class="form-label">Empresa (opcional)</label>
                <input class="form-input" name="company_name">
            </div>
            <div class="form-group">
                <label class="form-label">Telefono (opcional)</label>
                <input class="form-input" name="phone">
            </div>
            <div class="form-group">
                <label class="form-label">Contrasena</label>
                <input class="form-input" type="password" name="password" required minlength="6">
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center">Crear Cuenta</button>
        </form>
    `);
}

async function handleRegister(e) {
    e.preventDefault();
    const form = e.target;
    const data = {
        full_name: form.full_name.value,
        email: form.email.value,
        company_name: form.company_name.value || null,
        phone: form.phone.value || null,
        password: form.password.value,
    };

    try {
        const resp = await API.register(data);
        if (resp.access_token) {
            state.token = resp.access_token;
            state.refreshToken = resp.refresh_token;
            state.user = resp.user;
            localStorage.setItem('_mkt_token', state.token);
            localStorage.setItem('_mkt_refresh', state.refreshToken);
            localStorage.setItem('_mkt_user', JSON.stringify(state.user));
            closeModal();
            renderApp();
            toast('Cuenta creada exitosamente', 'success');
        } else {
            toast(resp.detail || 'Error al registrarse', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

function logout() {
    state.user = null;
    state.token = null;
    state.refreshToken = null;
    localStorage.removeItem('_mkt_token');
    localStorage.removeItem('_mkt_refresh');
    localStorage.removeItem('_mkt_user');
    renderApp();
}

// ── Render: Dashboard ──────────────────────────────────────────
async function renderDashboard() {
    const page = document.getElementById('page-content');
    page.innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Dashboard</h1>
            <p class="page-subtitle">Resumen general del marketplace</p>
        </div>
        <div class="stats-grid" id="stats-grid">
            <div class="stat-card"><div class="stat-value">-</div><div class="stat-label">Cargando...</div></div>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Acciones rapidas</span></div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                <button class="btn btn-primary" onclick="navigate('prices')">${icon('search',16)} Buscar Precios</button>
                <button class="btn btn-secondary" onclick="navigate('quotations')">${icon('upload',16)} Subir Cotizacion</button>
                <button class="btn btn-secondary" onclick="navigate('rfq')">${icon('send',16)} Nueva RFQ</button>
            </div>
        </div>
    `;

    try {
        const resp = await API.stats();
        if (resp.ok) {
            const s = resp.data;
            document.getElementById('stats-grid').innerHTML = `
                <div class="stat-card"><div class="stat-value">${s.insumos}</div><div class="stat-label">Insumos</div></div>
                <div class="stat-card"><div class="stat-value">${s.suppliers}</div><div class="stat-label">Proveedores</div></div>
                <div class="stat-card"><div class="stat-value">${s.quotations}</div><div class="stat-label">Cotizaciones</div></div>
                <div class="stat-card"><div class="stat-value">${s.regions}</div><div class="stat-label">Regiones</div></div>
                <div class="stat-card"><div class="stat-value">${s.users}</div><div class="stat-label">Usuarios</div></div>
            `;
        }
    } catch {}
}

// ── Render: Prices ─────────────────────────────────────────────
async function renderPrices() {
    const page = document.getElementById('page-content');
    page.innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Precios Unitarios</h1>
            <p class="page-subtitle">Catalogo centralizado de insumos y precios</p>
        </div>
        <div class="search-bar">
            <input class="form-input" id="price-search" placeholder="Buscar insumo..." oninput="searchPrices()">
            <button class="btn btn-primary" onclick="showNewInsumoModal()">${icon('plus',16)} Nuevo</button>
        </div>
        <div id="prices-list"></div>
    `;
    await loadPrices();
}

async function loadPrices(q = '') {
    const params = q ? `?q=${encodeURIComponent(q)}` : '';
    try {
        const resp = await API.insumos(params);
        if (resp.ok) {
            const container = document.getElementById('prices-list');
            if (!resp.data.length) {
                container.innerHTML = '<div class="empty-state"><p>No se encontraron insumos</p></div>';
                return;
            }
            container.innerHTML = `
                <div class="table-wrap"><table>
                    <thead><tr><th>Nombre</th><th>UOM</th><th>Categoria</th><th>Precio Ref.</th></tr></thead>
                    <tbody>${resp.data.map(i => `
                        <tr onclick="showInsumoDetail(${i.id})" style="cursor:pointer">
                            <td><strong>${esc(i.name)}</strong>${i.code ? ` <span class="badge badge-gray">${esc(i.code)}</span>` : ''}</td>
                            <td>${esc(i.uom)}</td>
                            <td>${i.category ? esc(i.category) : '-'}</td>
                            <td>${i.ref_price ? `${i.ref_price.toFixed(2)} ${esc(i.ref_currency)}` : '-'}</td>
                        </tr>
                    `).join('')}</tbody>
                </table></div>
                <p style="margin-top:8px;font-size:13px;color:var(--gray-500)">${resp.total} insumos encontrados</p>
            `;
        }
    } catch { toast('Error cargando precios', 'error'); }
}

let _searchTimer;
function searchPrices() {
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => {
        const q = document.getElementById('price-search')?.value || '';
        loadPrices(q);
    }, 300);
}

async function showInsumoDetail(id) {
    try {
        const resp = await API.insumo(id);
        if (!resp.ok) return;
        const i = resp.data;
        const regPrices = (i.regional_prices || []).map(rp => `
            <tr><td>${esc(rp.region)}</td><td>${rp.price.toFixed(2)} ${esc(rp.currency)}</td>
            <td>${rp.sample_count}</td><td>${(rp.confidence * 100).toFixed(0)}%</td></tr>
        `).join('');

        showModal(i.name, `
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
                <div><span class="form-label">Codigo</span><p>${i.code || '-'}</p></div>
                <div><span class="form-label">UOM</span><p>${esc(i.uom)}</p></div>
                <div><span class="form-label">Categoria</span><p>${i.category || '-'}</p></div>
                <div><span class="form-label">Precio Ref.</span><p>${i.ref_price ? i.ref_price.toFixed(2) + ' ' + i.ref_currency : '-'}</p></div>
            </div>
            ${i.description ? `<p style="margin-bottom:16px;color:var(--gray-600)">${esc(i.description)}</p>` : ''}
            <h3 style="font-size:14px;margin-bottom:8px">Precios Regionales</h3>
            ${regPrices ? `<div class="table-wrap"><table>
                <thead><tr><th>Region</th><th>Precio</th><th>Muestras</th><th>Confianza</th></tr></thead>
                <tbody>${regPrices}</tbody>
            </table></div>` : '<p style="color:var(--gray-400)">Sin precios regionales</p>'}
        `);
    } catch {}
}

function showNewInsumoModal() {
    showModal('Nuevo Insumo', `
        <form id="new-insumo-form" onsubmit="handleCreateInsumo(event)">
            <div class="form-group"><label class="form-label">Nombre</label><input class="form-input" name="name" required></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">UOM</label>
                    <select class="form-select" name="uom" required>
                        <option value="m3">m3</option><option value="m2">m2</option><option value="ml">ml</option>
                        <option value="kg">kg</option><option value="tn">tn</option><option value="pza">pza</option>
                        <option value="bls">bls</option><option value="lt">lt</option><option value="gl">gl</option>
                        <option value="glb">glb</option>
                    </select>
                </div>
                <div class="form-group"><label class="form-label">Codigo</label><input class="form-input" name="code"></div>
            </div>
            <div class="form-group"><label class="form-label">Categoria</label><input class="form-input" name="category"></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Precio Ref.</label><input class="form-input" type="number" step="0.01" name="ref_price"></div>
                <div class="form-group"><label class="form-label">Moneda</label>
                    <select class="form-select" name="ref_currency"><option value="BOB">BOB</option><option value="USD">USD</option></select>
                </div>
            </div>
            <div class="form-group"><label class="form-label">Descripcion</label><textarea class="form-input" name="description"></textarea></div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center">Crear Insumo</button>
        </form>
    `);
}

async function handleCreateInsumo(e) {
    e.preventDefault();
    const f = e.target;
    const data = {
        name: f.name.value,
        uom: f.uom.value,
        code: f.code.value || null,
        category: f.category.value || null,
        ref_price: f.ref_price.value ? parseFloat(f.ref_price.value) : null,
        ref_currency: f.ref_currency.value,
        description: f.description.value || null,
    };
    const resp = await API.createInsumo(data);
    if (resp.ok) { closeModal(); toast('Insumo creado', 'success'); loadPrices(); }
    else toast(resp.detail || 'Error', 'error');
}

// ── Render: Suppliers ──────────────────────────────────────────
async function renderSuppliers() {
    const page = document.getElementById('page-content');
    page.innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Proveedores</h1>
        </div>
        <div class="search-bar">
            <input class="form-input" id="supplier-search" placeholder="Buscar proveedor...">
            <button class="btn btn-primary" onclick="showNewSupplierModal()">${icon('plus',16)} Nuevo</button>
        </div>
        <div id="suppliers-list"></div>
    `;
    await loadSuppliers();
}

async function loadSuppliers(q = '') {
    const params = q ? `?q=${encodeURIComponent(q)}` : '';
    try {
        const resp = await API.suppliers(params);
        if (resp.ok) {
            const container = document.getElementById('suppliers-list');
            if (!resp.data.length) {
                container.innerHTML = '<div class="empty-state"><p>No hay proveedores registrados</p></div>';
                return;
            }
            container.innerHTML = `<div class="table-wrap"><table>
                <thead><tr><th>Nombre</th><th>Ciudad</th><th>Canal</th><th>Estado</th><th>Cotizaciones</th></tr></thead>
                <tbody>${resp.data.map(s => `
                    <tr>
                        <td><strong>${esc(s.name)}</strong>${s.nit ? `<br><small>${esc(s.nit)}</small>` : ''}</td>
                        <td>${s.city || '-'}</td>
                        <td><span class="badge badge-gray">${esc(s.preferred_channel)}</span></td>
                        <td><span class="badge badge-${s.verification_state === 'verified' ? 'success' : s.verification_state === 'rejected' ? 'danger' : 'warning'}">${esc(s.verification_state)}</span></td>
                        <td>${s.quotation_count}</td>
                    </tr>
                `).join('')}</tbody>
            </table></div>`;
        }
    } catch { toast('Error cargando proveedores', 'error'); }
}

function showNewSupplierModal() {
    showModal('Nuevo Proveedor', `
        <form id="new-supplier-form" onsubmit="handleCreateSupplier(event)">
            <div class="form-group"><label class="form-label">Nombre / Razon Social</label><input class="form-input" name="name" required></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">NIT</label><input class="form-input" name="nit"></div>
                <div class="form-group"><label class="form-label">Email</label><input class="form-input" type="email" name="email"></div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Telefono</label><input class="form-input" name="phone"></div>
                <div class="form-group"><label class="form-label">WhatsApp</label><input class="form-input" name="whatsapp"></div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Ciudad</label><input class="form-input" name="city"></div>
                <div class="form-group"><label class="form-label">Departamento</label>
                    <select class="form-select" name="department">
                        <option value="">Seleccionar...</option>
                        <option>Santa Cruz</option><option>La Paz</option><option>Cochabamba</option>
                        <option>Tarija</option><option>Sucre</option><option>Oruro</option>
                        <option>Potosi</option><option>Beni</option><option>Pando</option>
                    </select>
                </div>
            </div>
            <div class="form-group"><label class="form-label">Canal preferido</label>
                <select class="form-select" name="preferred_channel">
                    <option value="email">Email</option><option value="whatsapp">WhatsApp</option><option value="telegram">Telegram</option>
                </select>
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center">Crear Proveedor</button>
        </form>
    `);
}

async function handleCreateSupplier(e) {
    e.preventDefault();
    const f = e.target;
    const data = {
        name: f.name.value,
        nit: f.nit.value || null,
        email: f.email.value || null,
        phone: f.phone.value || null,
        whatsapp: f.whatsapp.value || null,
        city: f.city.value || null,
        department: f.department.value || null,
        preferred_channel: f.preferred_channel.value,
    };
    const resp = await API.createSupplier(data);
    if (resp.ok) { closeModal(); toast('Proveedor creado', 'success'); loadSuppliers(); }
    else toast(resp.detail || 'Error', 'error');
}

// ── Render: Quotations ─────────────────────────────────────────
async function renderQuotations() {
    const page = document.getElementById('page-content');
    page.innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Cotizaciones</h1>
        </div>
        <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
            <button class="btn btn-primary" onclick="showUploadQuotationModal()">${icon('upload',16)} Subir Archivo</button>
            <button class="btn btn-secondary" onclick="showManualQuotationModal()">${icon('plus',16)} Manual</button>
        </div>
        <div id="quotations-list"></div>
    `;
    await loadQuotations();
}

async function loadQuotations() {
    try {
        const resp = await API.quotations();
        if (resp.ok) {
            const container = document.getElementById('quotations-list');
            if (!resp.data.length) {
                container.innerHTML = '<div class="empty-state"><p>No hay cotizaciones</p></div>';
                return;
            }
            container.innerHTML = `<div class="table-wrap"><table>
                <thead><tr><th>Ref.</th><th>Origen</th><th>Estado</th><th>Lineas</th><th>Matched</th><th>Fecha</th></tr></thead>
                <tbody>${resp.data.map(q => `
                    <tr>
                        <td><strong>${esc(q.reference)}</strong></td>
                        <td><span class="badge badge-gray">${esc(q.source)}</span></td>
                        <td><span class="badge badge-${q.state === 'matched' || q.state === 'validated' ? 'success' : q.state === 'processing' ? 'warning' : 'primary'}">${esc(q.state)}</span></td>
                        <td>${q.line_count}</td>
                        <td>${q.matched_count}</td>
                        <td>${q.received_at ? new Date(q.received_at).toLocaleDateString('es') : '-'}</td>
                    </tr>
                `).join('')}</tbody>
            </table></div>`;
        }
    } catch { toast('Error cargando cotizaciones', 'error'); }
}

function showUploadQuotationModal() {
    showModal('Subir Cotizacion', `
        <form id="upload-quot-form" onsubmit="handleUploadQuotation(event)">
            <div class="form-group"><label class="form-label">Proveedor ID</label><input class="form-input" type="number" name="supplier_id" required></div>
            <div class="form-group"><label class="form-label">Archivo (Excel, PDF o Foto)</label>
                <input class="form-input" type="file" name="file" accept=".xlsx,.xls,.pdf,image/*" required>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Region</label><input class="form-input" name="region" placeholder="Ej: Santa Cruz"></div>
                <div class="form-group"><label class="form-label">Moneda</label>
                    <select class="form-select" name="currency"><option value="BOB">BOB</option><option value="USD">USD</option></select>
                </div>
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center">Subir y Procesar</button>
        </form>
    `);
}

async function handleUploadQuotation(e) {
    e.preventDefault();
    const f = e.target;
    const fd = new FormData();
    fd.append('supplier_id', f.supplier_id.value);
    fd.append('file', f.file.files[0]);
    fd.append('region', f.region.value);
    fd.append('currency', f.currency.value);

    const resp = await API.uploadQuotation(fd);
    if (resp.ok) {
        closeModal();
        toast(`Cotizacion creada: ${resp.extracted_lines} lineas extraidas`, 'success');
        loadQuotations();
    } else toast(resp.detail || 'Error al procesar archivo', 'error');
}

function showManualQuotationModal() {
    showModal('Cotizacion Manual', `
        <p style="color:var(--gray-500);margin-bottom:16px">Ingrese los datos de la cotizacion manualmente</p>
        <form id="manual-quot-form" onsubmit="handleManualQuotation(event)">
            <div class="form-group"><label class="form-label">Proveedor ID</label><input class="form-input" type="number" name="supplier_id" required></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Region</label><input class="form-input" name="region"></div>
                <div class="form-group"><label class="form-label">Moneda</label>
                    <select class="form-select" name="currency"><option value="BOB">BOB</option><option value="USD">USD</option></select>
                </div>
            </div>
            <div id="manual-lines">
                <h3 style="font-size:14px;margin-bottom:8px">Lineas</h3>
                <div class="manual-line" style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:8px;margin-bottom:8px">
                    <input class="form-input" name="line_name_0" placeholder="Nombre del producto" required>
                    <input class="form-input" name="line_uom_0" placeholder="UOM">
                    <input class="form-input" type="number" step="0.01" name="line_price_0" placeholder="Precio" required>
                </div>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" onclick="addManualLine()" style="margin-bottom:16px">+ Agregar linea</button>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center">Crear Cotizacion</button>
        </form>
    `);
}

let _manualLineCount = 1;
function addManualLine() {
    const i = _manualLineCount++;
    const container = document.getElementById('manual-lines');
    const div = document.createElement('div');
    div.className = 'manual-line';
    div.style = 'display:grid;grid-template-columns:2fr 1fr 1fr;gap:8px;margin-bottom:8px';
    div.innerHTML = `
        <input class="form-input" name="line_name_${i}" placeholder="Nombre del producto" required>
        <input class="form-input" name="line_uom_${i}" placeholder="UOM">
        <input class="form-input" type="number" step="0.01" name="line_price_${i}" placeholder="Precio" required>
    `;
    container.appendChild(div);
}

async function handleManualQuotation(e) {
    e.preventDefault();
    const f = e.target;
    const lines = [];
    for (let i = 0; i < 100; i++) {
        const name = f[`line_name_${i}`]?.value;
        if (!name) break;
        lines.push({
            product_name: name,
            uom: f[`line_uom_${i}`]?.value || null,
            unit_price: parseFloat(f[`line_price_${i}`]?.value || 0),
        });
    }
    const data = {
        supplier_id: parseInt(f.supplier_id.value),
        region: f.region.value || null,
        currency: f.currency.value,
        lines,
    };
    const resp = await API.createQuotation(data);
    if (resp.ok) { closeModal(); toast('Cotizacion creada', 'success'); loadQuotations(); }
    else toast(resp.detail || 'Error', 'error');
}

// ── Render: RFQ ────────────────────────────────────────────────
async function renderRFQ() {
    const page = document.getElementById('page-content');
    page.innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Solicitudes de Cotizacion</h1>
        </div>
        <button class="btn btn-primary" onclick="showNewRFQModal()" style="margin-bottom:16px">${icon('plus',16)} Nueva RFQ</button>
        <div id="rfq-list"></div>
    `;
    await loadRFQs();
}

async function loadRFQs() {
    try {
        const resp = await API.rfqs();
        if (resp.ok) {
            const container = document.getElementById('rfq-list');
            if (!resp.data.length) {
                container.innerHTML = '<div class="empty-state"><p>No hay solicitudes de cotizacion</p></div>';
                return;
            }
            container.innerHTML = `<div class="table-wrap"><table>
                <thead><tr><th>Ref.</th><th>Titulo</th><th>Estado</th><th>Proveedores</th><th>Respuestas</th><th>Canales</th></tr></thead>
                <tbody>${resp.data.map(r => `
                    <tr>
                        <td><strong>${esc(r.reference)}</strong></td>
                        <td>${esc(r.title)}</td>
                        <td><span class="badge badge-${r.state === 'sent' ? 'success' : r.state === 'closed' ? 'gray' : 'primary'}">${esc(r.state)}</span></td>
                        <td>${r.supplier_count}</td>
                        <td>${r.response_count}</td>
                        <td>${(r.channels_used || []).map(c => `<span class="chip">${esc(c)}</span>`).join(' ')}</td>
                    </tr>
                `).join('')}</tbody>
            </table></div>`;
        }
    } catch { toast('Error cargando RFQs', 'error'); }
}

function showNewRFQModal() {
    showModal('Nueva Solicitud de Cotizacion', `
        <form id="new-rfq-form" onsubmit="handleCreateRFQ(event)">
            <div class="form-group"><label class="form-label">Titulo</label><input class="form-input" name="title" required placeholder="Ej: Materiales para obra X"></div>
            <div class="form-group"><label class="form-label">Descripcion</label><textarea class="form-input" name="description"></textarea></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Region</label><input class="form-input" name="region" placeholder="Santa Cruz"></div>
                <div class="form-group"><label class="form-label">Fecha limite</label><input class="form-input" type="date" name="deadline"></div>
            </div>
            <div class="form-group"><label class="form-label">IDs de proveedores (separados por coma)</label><input class="form-input" name="supplier_ids" required placeholder="1,2,3"></div>
            <div class="form-group"><label class="form-label">Canales de envio</label>
                <div style="display:flex;gap:12px">
                    <label><input type="checkbox" name="ch_email" checked> Email</label>
                    <label><input type="checkbox" name="ch_whatsapp"> WhatsApp</label>
                    <label><input type="checkbox" name="ch_telegram"> Telegram</label>
                </div>
            </div>
            <div id="rfq-items"><h3 style="font-size:14px;margin:12px 0 8px">Items</h3>
                <div style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:8px;margin-bottom:8px">
                    <input class="form-input" name="item_name_0" placeholder="Nombre" required>
                    <input class="form-input" name="item_uom_0" placeholder="UOM">
                    <input class="form-input" type="number" step="0.01" name="item_qty_0" placeholder="Cantidad" value="1">
                </div>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" onclick="addRFQItem()" style="margin-bottom:16px">+ Agregar item</button>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center">Crear RFQ</button>
        </form>
    `);
}

let _rfqItemCount = 1;
function addRFQItem() {
    const i = _rfqItemCount++;
    const container = document.getElementById('rfq-items');
    const div = document.createElement('div');
    div.style = 'display:grid;grid-template-columns:2fr 1fr 1fr;gap:8px;margin-bottom:8px';
    div.innerHTML = `
        <input class="form-input" name="item_name_${i}" placeholder="Nombre" required>
        <input class="form-input" name="item_uom_${i}" placeholder="UOM">
        <input class="form-input" type="number" step="0.01" name="item_qty_${i}" placeholder="Cantidad" value="1">
    `;
    container.appendChild(div);
}

async function handleCreateRFQ(e) {
    e.preventDefault();
    const f = e.target;
    const items = [];
    for (let i = 0; i < 100; i++) {
        const name = f[`item_name_${i}`]?.value;
        if (!name) break;
        items.push({
            name, uom: f[`item_uom_${i}`]?.value || null,
            quantity: parseFloat(f[`item_qty_${i}`]?.value || 1),
        });
    }
    const channels = [];
    if (f.ch_email.checked) channels.push('email');
    if (f.ch_whatsapp.checked) channels.push('whatsapp');
    if (f.ch_telegram.checked) channels.push('telegram');

    const data = {
        title: f.title.value,
        description: f.description.value || null,
        region: f.region.value || null,
        deadline: f.deadline.value || null,
        supplier_ids: f.supplier_ids.value.split(',').map(s => parseInt(s.trim())).filter(Boolean),
        channels,
        items,
    };
    const resp = await API.createRFQ(data);
    if (resp.ok) { closeModal(); toast('RFQ creada', 'success'); loadRFQs(); }
    else toast(resp.detail || 'Error', 'error');
}

// ── Modal utility ──────────────────────────────────────────────
function showModal(title, bodyHtml) {
    const existing = document.querySelector('.modal-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };
    overlay.innerHTML = `
        <div class="modal">
            <div class="modal-header">
                <span class="modal-title">${title}</span>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">${bodyHtml}</div>
        </div>
    `;
    document.body.appendChild(overlay);
}

function closeModal() {
    document.querySelector('.modal-overlay')?.remove();
}

// ── Toast utility ──────────────────────────────────────────────
function toast(msg, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4000);
}

// ── Helpers ────────────────────────────────────────────────────
function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── Init ───────────────────────────────────────────────────────
function init() {
    // Restore session
    state.token = localStorage.getItem('_mkt_token');
    state.refreshToken = localStorage.getItem('_mkt_refresh');
    try { state.user = JSON.parse(localStorage.getItem('_mkt_user')); } catch {}

    // Hide loading
    const loading = document.getElementById('loading-screen');
    if (loading) loading.classList.add('hidden');

    // Register service worker
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
    }

    renderApp();
}

// Start
document.addEventListener('DOMContentLoaded', init);
