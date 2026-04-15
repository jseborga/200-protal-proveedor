/**
 * APU Marketplace — Portal Publico de Precios de Construccion
 * Public-first SPA. No login required to browse prices and suppliers.
 */

// ── State ──────────────────────────────────────────────────────
const state = {
    user: null,
    token: null,
    refreshToken: null,
    currentPage: 'home',
    searchQuery: '',
    selectedCategory: null,
    selectedDepartment: null,
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

    // Public — no auth
    publicPrices: (params = '') => API.get(`/prices/public${params}`),
    searchPrices: (q) => API.get(`/prices/public/search?q=${encodeURIComponent(q)}`),
    publicSuppliers: (params = '') => API.get(`/suppliers/public${params}`),
    supplierCategories: () => API.get('/suppliers/public/categories'),
    supplierCities: () => API.get('/suppliers/public/cities'),
    priceCategories: () => API.get('/prices/categories/list'),

    // Authenticated
    suppliers: (params = '') => API.get(`/suppliers${params}`),
    supplier: (id) => API.get(`/suppliers/${id}`),
    createSupplier: (data) => API.post('/suppliers', data),
    updateSupplier: (id, data) => API.put(`/suppliers/${id}`, data),
    quotations: (params = '') => API.get(`/quotations${params}`),
    quotation: (id) => API.get(`/quotations/${id}`),
    createQuotation: (data) => API.post('/quotations', data),
    processQuotation: (id) => API.post(`/quotations/${id}/process`),
    uploadQuotation: (formData) => API.upload('/quotations/upload', formData),
    insumos: (params = '') => API.get(`/prices${params}`),
    insumo: (id) => API.get(`/prices/${id}`),
    createInsumo: (data) => API.post('/prices', data),
    rfqs: (params = '') => API.get(`/rfq${params}`),
    createRFQ: (data) => API.post('/rfq', data),
    stats: () => API.get('/admin/stats'),

    // Admin — user management
    adminUsers: (params = '') => API.get(`/admin/users${params}`),
    adminCreateUser: (data) => API.post('/admin/users', data),
    adminUpdateUser: (id, data) => API.put(`/admin/users/${id}`, data),
    adminResetPassword: (id) => API.post(`/admin/users/${id}/reset-password`),

    // Admin — API keys
    apiKeys: () => API.get('/admin/api-keys'),
    createApiKey: (data) => API.post('/admin/api-keys', data),
    updateApiKey: (id, data) => API.put(`/admin/api-keys/${id}`, data),
    revokeApiKey: (id) => API.del(`/admin/api-keys/${id}`),

    // Admin — catalog (categories & UOMs)
    adminCategories: () => API.get('/admin/categories'),
    adminCreateCategory: (data) => API.post('/admin/categories', data),
    adminUpdateCategory: (id, data) => API.put(`/admin/categories/${id}`, data),
    adminDeleteCategory: (id) => API.del(`/admin/categories/${id}`),
    adminUoms: () => API.get('/admin/uoms'),
    adminCreateUom: (data) => API.post('/admin/uoms', data),
    adminUpdateUom: (id, data) => API.put(`/admin/uoms/${id}`, data),
    adminDeleteUom: (id) => API.del(`/admin/uoms/${id}`),

    // Public catalog
    catalogCategories: () => API.get('/admin/catalog/categories'),
    catalogUoms: () => API.get('/admin/catalog/uoms'),
};

// ── Categories & UOMs (loaded from API) ───────────────────────
let CATEGORY_META = {};
let UOM_LIST = [];

async function loadCatalogData() {
    try {
        const [catResp, uomResp] = await Promise.all([
            API.catalogCategories(),
            API.catalogUoms(),
        ]);
        if (catResp.ok) {
            CATEGORY_META = {};
            catResp.data.forEach(c => {
                CATEGORY_META[c.key] = { label: c.label, icon: c.icon || '' };
            });
        }
        if (uomResp.ok) {
            UOM_LIST = uomResp.data;
        }
    } catch {}
}

const DEPARTMENTS = [
    'Santa Cruz', 'La Paz', 'Cochabamba', 'Tarija',
    'Sucre', 'Oruro', 'Potosi', 'Beni', 'Pando',
];

// ── Icons (inline SVG) ─────────────────────────────────────────
const ICONS = {
    home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9,22 9,12 15,12 15,22"/></svg>',
    tag: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>',
    users: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4-4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>',
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    'file-text': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22,2 15,22 11,13 2,9"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
    upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17,8 12,3 7,8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
    login: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4"/><polyline points="10,17 15,12 10,7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>',
    logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16,17 21,12 16,7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
    phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg>',
    whatsapp: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>',
    map: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>',
    star: '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1"><polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/></svg>',
    'bar-chart': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>',
    'trending-up': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23,6 13.5,15.5 8.5,10.5 1,18"/><polyline points="17,6 23,6 23,12"/></svg>',
    settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>',
    edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3,6 5,6 21,6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>',
    'user-plus': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4-4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>',
    key: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>',
};

function icon(name, size = 20) {
    return `<span class="icon" style="width:${size}px;height:${size}px;display:inline-flex">${ICONS[name] || ''}</span>`;
}

// ── Navigation ─────────────────────────────────────────────────
function navigate(page) {
    state.currentPage = page;
    window.scrollTo(0, 0);
    renderApp();
}

// ── Render: App shell ──────────────────────────────────────────
function renderApp() {
    const app = document.getElementById('app');

    const publicPages = {
        home:      { title: 'Inicio',       icon: 'home',     render: renderHome },
        prices:    { title: 'Precios',       icon: 'tag',      render: renderPublicPrices },
        suppliers: { title: 'Proveedores',   icon: 'users',    render: renderPublicSuppliers },
    };

    const authPages = {
        quotations: { title: 'Cotizaciones', icon: 'file-text', render: renderQuotations },
        rfq:        { title: 'RFQ',          icon: 'send',      render: renderRFQ },
    };

    const staffPages = isStaff() ? {
        admin:     { title: 'Admin',        icon: 'settings',   render: renderAdmin },
    } : {};

    const allPages = { ...publicPages, ...(state.user ? { ...authPages, ...staffPages } : {}) };

    app.innerHTML = `
        ${renderTopbar(publicPages, { ...authPages, ...staffPages })}
        <div class="app-container">
            <div class="page" id="page-content"></div>
        </div>
        <div class="footer">
            APU Marketplace &mdash; Portal de Precios de Construccion
        </div>
        <div id="toast-container" class="toast-container"></div>
    `;

    const pageConfig = allPages[state.currentPage];
    if (pageConfig) {
        pageConfig.render();
    } else {
        navigate('home');
        return;
    }
}

function renderTopbar(publicPages, authPages) {
    const navItems = Object.entries(publicPages).map(([key, cfg]) => `
        <button class="topbar-nav-item${state.currentPage === key ? ' active' : ''}"
                onclick="navigate('${key}')">
            ${cfg.title}
        </button>
    `).join('');

    const authNav = state.user
        ? Object.entries(authPages).map(([key, cfg]) => `
            <button class="topbar-nav-item${state.currentPage === key ? ' active' : ''}"
                    onclick="navigate('${key}')">
                ${cfg.title}
            </button>
        `).join('')
        : '';

    const userActions = state.user
        ? `<span class="topbar-btn" style="cursor:default;font-size:13px">${esc(state.user.full_name)}</span>
           <button class="topbar-btn" onclick="logout()" title="Cerrar sesion">${icon('logout', 16)}</button>`
        : `<button class="topbar-btn-accent topbar-btn" onclick="showLoginModal()">
               ${icon('login', 16)} Ingresar
           </button>`;

    return `
        <div class="topbar">
            <div class="topbar-logo" onclick="navigate('home')">
                <svg width="32" height="32" viewBox="0 0 48 48" fill="none">
                    <rect width="48" height="48" rx="10" fill="rgba(255,255,255,0.2)"/>
                    <path d="M12 36V16l12-6 12 6v20" stroke="white" stroke-width="2.5" fill="none"/>
                    <path d="M20 36V26h8v10" stroke="white" stroke-width="2"/>
                </svg>
                APU MKT
            </div>
            <div class="topbar-nav">
                ${navItems}${authNav}
            </div>
            <div class="topbar-spacer"></div>
            <div class="topbar-actions">
                ${userActions}
            </div>
        </div>
    `;
}

// ── Render: Home (public) ──────────────────────────────────────
async function renderHome() {
    const page = document.getElementById('page-content');
    page.innerHTML = `
        <div class="hero">
            <h1 class="hero-title">Precios de Construccion en Bolivia</h1>
            <p class="hero-subtitle">Busca materiales, compara precios y contacta proveedores directamente</p>
            <div class="hero-search">
                <input class="form-input" id="hero-search-input"
                       placeholder="Buscar cemento, acero, arena, tuberias..."
                       value="${esc(state.searchQuery)}"
                       onkeydown="if(event.key==='Enter')heroSearch()">
                <button class="btn btn-primary" onclick="heroSearch()">
                    ${icon('search', 18)} Buscar
                </button>
            </div>
        </div>

        <div class="categories-bar" id="home-categories">
            <span class="chip${!state.selectedCategory ? ' active' : ''}" onclick="selectCategory(null)">Todos</span>
        </div>

        <div id="home-stats" class="stats-grid" style="margin-top:16px"></div>

        <h2 style="font-size:18px;font-weight:600;margin:20px 0 12px">Proveedores destacados</h2>
        <div class="supplier-grid" id="home-suppliers">
            <div class="empty-state"><p>Cargando proveedores...</p></div>
        </div>

        <h2 style="font-size:18px;font-weight:600;margin:24px 0 12px">Precios recientes</h2>
        <div class="price-grid" id="home-prices">
            <div class="empty-state"><p>Cargando precios...</p></div>
        </div>
    `;

    // Load all data in parallel
    loadHomeCategories();
    loadHomeSuppliers();
    loadHomePrices();
    loadHomeStats();
}

async function loadHomeCategories() {
    try {
        const resp = await API.supplierCategories();
        if (resp.ok && resp.data.length) {
            const container = document.getElementById('home-categories');
            const chips = resp.data.map(c => {
                const meta = CATEGORY_META[c.name] || { label: c.name, icon: '' };
                return `<span class="chip${state.selectedCategory === c.name ? ' active' : ''}"
                              onclick="selectCategory('${esc(c.name)}')">${meta.icon} ${esc(meta.label || c.name)} <small>(${c.count})</small></span>`;
            }).join('');
            container.innerHTML = `
                <span class="chip${!state.selectedCategory ? ' active' : ''}" onclick="selectCategory(null)">Todos</span>
                ${chips}
            `;
        }
    } catch {}
}

async function loadHomeSuppliers() {
    let params = '?limit=6';
    if (state.selectedCategory) params += `&category=${encodeURIComponent(state.selectedCategory)}`;
    if (state.selectedDepartment) params += `&department=${encodeURIComponent(state.selectedDepartment)}`;

    try {
        const resp = await API.publicSuppliers(params);
        const container = document.getElementById('home-suppliers');
        if (resp.ok && resp.data.length) {
            container.innerHTML = resp.data.map(renderSupplierCard).join('');
        } else {
            container.innerHTML = '<div class="empty-state"><p>No hay proveedores registrados aun. Estamos trabajando para traerte los mejores.</p></div>';
        }
    } catch {
        document.getElementById('home-suppliers').innerHTML = '<div class="empty-state"><p>No se pudo cargar proveedores</p></div>';
    }
}

async function loadHomePrices() {
    let params = '?limit=8';
    if (state.selectedCategory) params += `&category=${encodeURIComponent(state.selectedCategory)}`;

    try {
        const resp = await API.publicPrices(params);
        const container = document.getElementById('home-prices');
        if (resp.ok && resp.data.length) {
            container.innerHTML = resp.data.map(renderPriceCard).join('');
        } else {
            container.innerHTML = '<div class="empty-state"><p>Pronto tendras precios actualizados aqui</p></div>';
        }
    } catch {
        document.getElementById('home-prices').innerHTML = '';
    }
}

async function loadHomeStats() {
    try {
        const [prices, suppliers] = await Promise.all([
            API.publicPrices('?limit=1'),
            API.publicSuppliers('?limit=1'),
        ]);
        const container = document.getElementById('home-stats');
        const totalPrices = prices.ok ? prices.total : 0;
        const totalSuppliers = suppliers.ok ? suppliers.total : 0;
        if (totalPrices > 0 || totalSuppliers > 0) {
            container.innerHTML = `
                <div class="stat-card"><div class="stat-value">${totalSuppliers}</div><div class="stat-label">Proveedores</div></div>
                <div class="stat-card"><div class="stat-value">${totalPrices}</div><div class="stat-label">Precios</div></div>
                <div class="stat-card"><div class="stat-value">${DEPARTMENTS.length}</div><div class="stat-label">Departamentos</div></div>
                <div class="stat-card"><div class="stat-value">${Object.keys(CATEGORY_META).length}+</div><div class="stat-label">Categorias</div></div>
            `;
        }
    } catch {}
}

function selectCategory(cat) {
    state.selectedCategory = cat;
    // Re-render chips + data
    loadHomeCategories();
    loadHomeSuppliers();
    loadHomePrices();
}

function heroSearch() {
    const input = document.getElementById('hero-search-input');
    state.searchQuery = (input?.value || '').trim();
    if (state.searchQuery.length >= 2) {
        navigate('prices');
    }
}

// ── Render: Supplier card (reusable) ───────────────────────────
function renderSupplierCard(s) {
    const cats = (s.categories || []).map(c => {
        const meta = CATEGORY_META[c] || { label: c };
        return `<span class="supplier-cat">${esc(meta.label || c)}</span>`;
    }).join('');

    const location = [s.city, s.department].filter(Boolean).join(', ');

    const waBtn = s.whatsapp
        ? `<a href="https://wa.me/${s.whatsapp.replace(/[^0-9]/g, '')}" target="_blank" rel="noopener"
              class="btn-whatsapp" onclick="event.stopPropagation()">
              ${icon('whatsapp', 16)} WhatsApp
           </a>`
        : '';

    const callBtn = s.phone
        ? `<a href="tel:${s.phone}" class="btn-call" onclick="event.stopPropagation()">
              ${icon('phone', 16)} Llamar
           </a>`
        : '';

    const rating = s.rating > 0
        ? `<span style="color:#f59e0b;font-size:13px">${icon('star', 14)} ${s.rating.toFixed(1)}</span>`
        : '';

    return `
        <div class="supplier-card">
            <div class="supplier-card-header">
                <div>
                    <div class="supplier-name">${esc(s.trade_name || s.name)}</div>
                    <div class="supplier-location">${icon('map', 14)} ${location || 'Bolivia'}</div>
                </div>
                ${rating}
            </div>
            <div class="supplier-categories">${cats || '<span style="font-size:12px;color:var(--gray-400)">Sin categorias</span>'}</div>
            <div class="supplier-actions">
                ${waBtn}
                ${callBtn}
            </div>
        </div>
    `;
}

// ── Render: Price card (reusable) ──────────────────────────────
function renderPriceCard(p) {
    return `
        <div class="price-card">
            <div class="price-info">
                <div class="price-name">${esc(p.name)}</div>
                <div class="price-detail">${p.category ? esc(p.category) : ''} ${p.uom ? '&middot; ' + esc(p.uom) : ''}</div>
            </div>
            <div class="price-value">
                ${p.ref_price ? p.ref_price.toFixed(2) : '--.--'}
                <span class="price-currency">${esc(p.ref_currency || 'BOB')}</span>
            </div>
        </div>
    `;
}

// ── Render: Public Prices page ─────────────────────────────────
async function renderPublicPrices() {
    const page = document.getElementById('page-content');
    page.innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Precios de Materiales</h1>
            <p class="page-subtitle">Catalogo publico de precios unitarios de construccion</p>
        </div>
        <div class="search-bar">
            <input class="form-input" id="price-search" placeholder="Buscar material, insumo..."
                   value="${esc(state.searchQuery)}" oninput="debouncePriceSearch()">
        </div>
        <div class="categories-bar" id="price-categories"></div>
        <div id="prices-list"><div class="empty-state"><p>Cargando...</p></div></div>
        <div id="prices-pagination" style="text-align:center;margin-top:16px"></div>
    `;

    loadPriceCategories();

    if (state.searchQuery.length >= 2) {
        searchPublicPrices(state.searchQuery);
    } else {
        loadPublicPrices();
    }
}

async function loadPriceCategories() {
    try {
        const resp = await API.priceCategories();
        if (resp.ok && resp.data.length) {
            const container = document.getElementById('price-categories');
            container.innerHTML = `
                <span class="chip${!state.selectedCategory ? ' active' : ''}" onclick="filterPriceCategory(null)">Todos</span>
                ${resp.data.map(c => `
                    <span class="chip${state.selectedCategory === c.name ? ' active' : ''}"
                          onclick="filterPriceCategory('${esc(c.name)}')">${esc(c.name)} (${c.count})</span>
                `).join('')}
            `;
        }
    } catch {}
}

function filterPriceCategory(cat) {
    state.selectedCategory = cat;
    state.searchQuery = '';
    const searchInput = document.getElementById('price-search');
    if (searchInput) searchInput.value = '';
    loadPriceCategories();
    loadPublicPrices();
}

let _priceTimer;
function debouncePriceSearch() {
    clearTimeout(_priceTimer);
    _priceTimer = setTimeout(() => {
        const q = document.getElementById('price-search')?.value?.trim() || '';
        state.searchQuery = q;
        if (q.length >= 2) {
            searchPublicPrices(q);
        } else {
            loadPublicPrices();
        }
    }, 350);
}

async function loadPublicPrices(offset = 0) {
    let params = `?offset=${offset}&limit=30`;
    if (state.selectedCategory) params += `&category=${encodeURIComponent(state.selectedCategory)}`;

    try {
        const resp = await API.publicPrices(params);
        const container = document.getElementById('prices-list');
        if (!resp.ok) { container.innerHTML = '<div class="empty-state"><p>Error cargando precios</p></div>'; return; }
        if (!resp.data.length) { container.innerHTML = '<div class="empty-state"><p>No se encontraron materiales</p></div>'; return; }

        container.innerHTML = `
            <div class="price-grid">${resp.data.map(renderPriceCard).join('')}</div>
        `;
        renderPagination(resp.total, offset, 30, loadPublicPrices);
    } catch { document.getElementById('prices-list').innerHTML = '<div class="empty-state"><p>Error de conexion</p></div>'; }
}

async function searchPublicPrices(q) {
    try {
        const resp = await API.searchPrices(q);
        const container = document.getElementById('prices-list');
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = `<div class="empty-state"><p>No se encontraron resultados para "${esc(q)}"</p></div>`;
            return;
        }
        container.innerHTML = `
            <p style="font-size:13px;color:var(--gray-500);margin-bottom:12px">${resp.data.length} resultados para "${esc(q)}"</p>
            <div class="price-grid">${resp.data.map(p => renderPriceCard({
                ...p, ref_currency: 'BOB',
            })).join('')}</div>
        `;
    } catch {
        document.getElementById('prices-list').innerHTML = '<div class="empty-state"><p>Error buscando</p></div>';
    }
}

function renderPagination(total, offset, limit, loadFn) {
    const container = document.getElementById('prices-pagination');
    if (!container || total <= limit) { if (container) container.innerHTML = ''; return; }

    const pages = Math.ceil(total / limit);
    const current = Math.floor(offset / limit);
    let html = '';
    for (let i = 0; i < pages && i < 10; i++) {
        html += `<button class="btn btn-sm ${i === current ? 'btn-primary' : 'btn-secondary'}"
                         onclick="(${loadFn.name})(${i * limit})" style="min-width:36px">${i + 1}</button> `;
    }
    container.innerHTML = html;
}

// ── Render: Public Suppliers page ──────────────────────────────
async function renderPublicSuppliers() {
    const page = document.getElementById('page-content');
    page.innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Directorio de Proveedores</h1>
            <p class="page-subtitle">Encuentra proveedores de materiales de construccion en Bolivia</p>
        </div>
        <div class="search-bar">
            <input class="form-input" id="supplier-search" placeholder="Buscar proveedor..." oninput="debounceSupplierSearch()">
            <select class="form-select" id="supplier-dept-filter" onchange="filterSupplierDept()" style="max-width:180px">
                <option value="">Todos los departamentos</option>
                ${DEPARTMENTS.map(d => `<option value="${d}"${state.selectedDepartment === d ? ' selected' : ''}>${d}</option>`).join('')}
            </select>
        </div>
        <div class="categories-bar" id="supplier-categories"></div>
        <div class="supplier-grid" id="suppliers-list">
            <div class="empty-state"><p>Cargando...</p></div>
        </div>
    `;

    loadSupplierCategoryChips();
    loadPublicSuppliers();
}

async function loadSupplierCategoryChips() {
    try {
        const resp = await API.supplierCategories();
        if (resp.ok && resp.data.length) {
            const container = document.getElementById('supplier-categories');
            if (!container) return;
            container.innerHTML = `
                <span class="chip${!state.selectedCategory ? ' active' : ''}" onclick="filterSupplierCategory(null)">Todos</span>
                ${resp.data.map(c => {
                    const meta = CATEGORY_META[c.name] || { label: c.name, icon: '' };
                    return `<span class="chip${state.selectedCategory === c.name ? ' active' : ''}"
                                  onclick="filterSupplierCategory('${esc(c.name)}')">${meta.icon} ${esc(meta.label || c.name)}</span>`;
                }).join('')}
            `;
        }
    } catch {}
}

function filterSupplierCategory(cat) {
    state.selectedCategory = cat;
    loadSupplierCategoryChips();
    loadPublicSuppliers();
}

function filterSupplierDept() {
    state.selectedDepartment = document.getElementById('supplier-dept-filter')?.value || null;
    loadPublicSuppliers();
}

let _supplierTimer;
function debounceSupplierSearch() {
    clearTimeout(_supplierTimer);
    _supplierTimer = setTimeout(loadPublicSuppliers, 350);
}

async function loadPublicSuppliers() {
    const q = document.getElementById('supplier-search')?.value?.trim() || '';
    let params = '?limit=50';
    if (q) params += `&q=${encodeURIComponent(q)}`;
    if (state.selectedCategory) params += `&category=${encodeURIComponent(state.selectedCategory)}`;
    if (state.selectedDepartment) params += `&department=${encodeURIComponent(state.selectedDepartment)}`;

    try {
        const resp = await API.publicSuppliers(params);
        const container = document.getElementById('suppliers-list');
        if (!container) return;
        if (resp.ok && resp.data.length) {
            container.innerHTML = resp.data.map(renderSupplierCard).join('');
        } else {
            container.innerHTML = '<div class="empty-state"><p>No se encontraron proveedores con esos filtros</p></div>';
        }
    } catch {
        const container = document.getElementById('suppliers-list');
        if (container) container.innerHTML = '<div class="empty-state"><p>Error cargando proveedores</p></div>';
    }
}

// ── Login Modal (not a page) ───────────────────────────────────
function showLoginModal() {
    showModal('Iniciar Sesion', `
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
            <div style="text-align:center;margin-top:12px;font-size:13px;color:var(--gray-500)">
                No tienes cuenta? <a href="#" onclick="showRegisterModal(event)">Registrate</a>
            </div>
        </form>
    `);
}

async function handleLogin(e) {
    e.preventDefault();
    const form = e.target;
    try {
        const data = await API.login(form.email.value, form.password.value);
        if (data.access_token) {
            state.token = data.access_token;
            state.refreshToken = data.refresh_token;
            state.user = data.user;
            localStorage.setItem('_mkt_token', state.token);
            localStorage.setItem('_mkt_refresh', state.refreshToken);
            localStorage.setItem('_mkt_user', JSON.stringify(state.user));
            closeModal();
            toast('Bienvenido, ' + (state.user.full_name || ''), 'success');
            renderApp();
        } else {
            toast(data.detail || 'Credenciales invalidas', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

function showRegisterModal(e) {
    e && e.preventDefault();
    showModal('Crear Cuenta', `
        <form id="register-form" onsubmit="handleRegister(event)">
            <div class="form-group"><label class="form-label">Nombre completo</label><input class="form-input" name="full_name" required></div>
            <div class="form-group"><label class="form-label">Email</label><input class="form-input" type="email" name="email" required></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Empresa (opcional)</label><input class="form-input" name="company_name"></div>
                <div class="form-group"><label class="form-label">Telefono</label><input class="form-input" name="phone"></div>
            </div>
            <div class="form-group"><label class="form-label">Contrasena</label><input class="form-input" type="password" name="password" required minlength="6"></div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center">Crear Cuenta</button>
            <div style="text-align:center;margin-top:12px;font-size:13px;color:var(--gray-500)">
                Ya tienes cuenta? <a href="#" onclick="showLoginModal()">Ingresa aqui</a>
            </div>
        </form>
    `);
}

async function handleRegister(e) {
    e.preventDefault();
    const f = e.target;
    try {
        const resp = await API.register({
            full_name: f.full_name.value,
            email: f.email.value,
            company_name: f.company_name.value || null,
            phone: f.phone.value || null,
            password: f.password.value,
        });
        if (resp.access_token) {
            state.token = resp.access_token;
            state.refreshToken = resp.refresh_token;
            state.user = resp.user;
            localStorage.setItem('_mkt_token', state.token);
            localStorage.setItem('_mkt_refresh', state.refreshToken);
            localStorage.setItem('_mkt_user', JSON.stringify(state.user));
            closeModal();
            toast('Cuenta creada. Bienvenido!', 'success');
            renderApp();
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
    state.currentPage = 'home';
    toast('Sesion cerrada', 'info');
    renderApp();
}

// ── Role helpers ───────────────────────────────────────────────
const STAFF_ROLES = ['admin', 'superadmin', 'manager', 'field_agent'];
const MANAGER_ROLES = ['admin', 'superadmin', 'manager'];

function isStaff() { return state.user && STAFF_ROLES.includes(state.user.role); }
function isManager() { return state.user && MANAGER_ROLES.includes(state.user.role); }
function isAdmin() { return state.user && ['admin', 'superadmin'].includes(state.user.role); }

const ROLE_LABELS = {
    admin: 'Administrador',
    superadmin: 'Super Admin',
    manager: 'Gestor',
    field_agent: 'Agente de Campo',
    user: 'Usuario',
    supplier: 'Proveedor',
};

const ROLE_COLORS = {
    admin: 'danger', superadmin: 'danger', manager: 'warning',
    field_agent: 'primary', user: 'gray', supplier: 'success',
};

// ── Admin state ────────────────────────────────────────────────
let _adminTab = 'dashboard';

// ── Render: Admin panel ────────────────────────────────────────
async function renderAdmin() {
    if (!isStaff()) { showLoginModal(); navigate('home'); return; }

    const page = document.getElementById('page-content');
    const tabs = [
        { key: 'dashboard', label: 'Dashboard', icon: 'bar-chart' },
        { key: 'suppliers', label: 'Proveedores', icon: 'users' },
        { key: 'products', label: 'Productos', icon: 'tag' },
    ];
    if (isAdmin()) tabs.push({ key: 'categories', label: 'Categorias', icon: 'tag' });
    if (isAdmin()) tabs.push({ key: 'uoms', label: 'Unidades', icon: 'settings' });
    if (isManager()) tabs.push({ key: 'users', label: 'Usuarios', icon: 'user-plus' });
    if (isAdmin()) tabs.push({ key: 'apikeys', label: 'API Keys', icon: 'key' });

    page.innerHTML = `
        <div class="page-header">
            <h1 class="page-title">${icon('settings', 24)} Panel de Administracion</h1>
            <p class="page-subtitle">Gestion de datos para trabajo de campo</p>
        </div>
        <div class="admin-tabs">
            ${tabs.map(t => `
                <button class="admin-tab${_adminTab === t.key ? ' active' : ''}"
                        onclick="switchAdminTab('${t.key}')">
                    ${icon(t.icon, 16)} ${t.label}
                </button>
            `).join('')}
        </div>
        <div id="admin-content"></div>
    `;

    renderAdminTab();
}

function switchAdminTab(tab) {
    _adminTab = tab;
    renderAdmin();
}

function renderAdminTab() {
    switch (_adminTab) {
        case 'dashboard': renderAdminDashboard(); break;
        case 'suppliers': renderAdminSuppliers(); break;
        case 'products': renderAdminProducts(); break;
        case 'categories': renderAdminCategories(); break;
        case 'uoms': renderAdminUoms(); break;
        case 'users': renderAdminUsers(); break;
        case 'apikeys': renderAdminApiKeys(); break;
    }
}

// ── Admin: Dashboard ───────────────────────────────────────────
async function renderAdminDashboard() {
    const c = document.getElementById('admin-content');
    c.innerHTML = `
        <div class="stats-grid" id="admin-stats">
            <div class="stat-card"><div class="stat-value">-</div><div class="stat-label">Cargando...</div></div>
        </div>
        <div class="card" style="margin-top:16px">
            <div class="card-header"><span class="card-title">Acciones rapidas</span></div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                <button class="btn btn-primary" onclick="switchAdminTab('suppliers')">${icon('plus',16)} Nuevo Proveedor</button>
                <button class="btn btn-secondary" onclick="switchAdminTab('products')">${icon('plus',16)} Nuevo Producto</button>
                ${isManager() ? `<button class="btn btn-secondary" onclick="switchAdminTab('users')">${icon('user-plus',16)} Crear Agente</button>` : ''}
            </div>
        </div>
    `;
    try {
        const resp = await API.stats();
        if (resp.ok) {
            const s = resp.data;
            document.getElementById('admin-stats').innerHTML = `
                <div class="stat-card"><div class="stat-value">${s.suppliers}</div><div class="stat-label">Proveedores</div></div>
                <div class="stat-card"><div class="stat-value">${s.insumos}</div><div class="stat-label">Productos</div></div>
                <div class="stat-card"><div class="stat-value">${s.quotations}</div><div class="stat-label">Cotizaciones</div></div>
                <div class="stat-card"><div class="stat-value">${s.users}</div><div class="stat-label">Usuarios</div></div>
                <div class="stat-card"><div class="stat-value">${s.regions}</div><div class="stat-label">Regiones</div></div>
            `;
        }
    } catch {}
}

// ── Admin: Suppliers ───────────────────────────────────────────
async function renderAdminSuppliers() {
    const c = document.getElementById('admin-content');
    c.innerHTML = `
        <div class="search-bar">
            <input class="form-input" id="admin-supplier-search" placeholder="Buscar proveedor..." oninput="debounceAdminSuppliers()">
            <select class="form-select" id="admin-supplier-state" onchange="loadAdminSuppliers()" style="max-width:160px">
                <option value="">Todos los estados</option>
                <option value="pending">Pendiente</option>
                <option value="verified">Verificado</option>
                <option value="rejected">Rechazado</option>
            </select>
            <button class="btn btn-primary" onclick="showAdminSupplierForm()">
                ${icon('plus',16)} Nuevo
            </button>
        </div>
        <div id="admin-suppliers-list"></div>
    `;
    loadAdminSuppliers();
}

let _admSupTimer;
function debounceAdminSuppliers() {
    clearTimeout(_admSupTimer);
    _admSupTimer = setTimeout(loadAdminSuppliers, 300);
}

async function loadAdminSuppliers() {
    const q = document.getElementById('admin-supplier-search')?.value?.trim() || '';
    const st = document.getElementById('admin-supplier-state')?.value || '';
    let params = '?limit=100';
    if (q) params += `&q=${encodeURIComponent(q)}`;
    if (st) params += `&state=${encodeURIComponent(st)}`;

    try {
        const resp = await API.suppliers(params);
        const container = document.getElementById('admin-suppliers-list');
        if (!container) return;
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = '<div class="empty-state"><p>No hay proveedores</p></div>';
            return;
        }
        container.innerHTML = `
            <div class="table-wrap"><table>
                <thead><tr>
                    <th>Nombre</th><th>Ciudad</th><th>Depto.</th><th>WhatsApp</th>
                    <th>Categorias</th><th>Estado</th><th>Acciones</th>
                </tr></thead>
                <tbody>${resp.data.map(s => `
                    <tr>
                        <td><strong>${esc(s.name)}</strong>${s.trade_name ? `<br><small style="color:var(--gray-500)">${esc(s.trade_name)}</small>` : ''}</td>
                        <td>${esc(s.city) || '-'}</td>
                        <td>${esc(s.department) || '-'}</td>
                        <td>${s.whatsapp ? `<a href="https://wa.me/${s.whatsapp.replace(/[^0-9]/g,'')}" target="_blank" style="color:var(--whatsapp)">${esc(s.whatsapp)}</a>` : '-'}</td>
                        <td>${(s.categories || []).map(c => `<span class="supplier-cat">${esc(c)}</span>`).join(' ') || '-'}</td>
                        <td><span class="badge badge-${s.verification_state === 'verified' ? 'success' : s.verification_state === 'rejected' ? 'danger' : 'warning'}">${esc(s.verification_state)}</span></td>
                        <td style="white-space:nowrap">
                            <button class="btn btn-sm btn-secondary" onclick="showSupplierProducts(${s.id}, '${esc(s.name)}')" title="Ver productos">${icon('tag',14)}</button>
                            <button class="btn btn-sm btn-secondary" onclick="showAdminSupplierForm(${s.id})" title="Editar">${icon('edit',14)}</button>
                            ${isManager() ? `<button class="btn btn-sm btn-secondary" onclick="verifySupplier(${s.id},'verified')" title="Verificar" style="color:var(--success)">&#10003;</button>` : ''}
                        </td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
            <p style="margin-top:8px;font-size:13px;color:var(--gray-500)">${resp.total} proveedores</p>
        `;
    } catch { document.getElementById('admin-suppliers-list').innerHTML = '<div class="empty-state"><p>Error cargando</p></div>'; }
}

async function verifySupplier(id, newState) {
    try {
        const resp = await API.updateSupplier(id, { verification_state: newState });
        if (resp.ok) { toast('Proveedor actualizado', 'success'); loadAdminSuppliers(); }
        else toast(resp.detail || 'Error', 'error');
    } catch { toast('Error de conexion', 'error'); }
}

async function showSupplierProducts(supplierId, name) {
    showModal(`Productos de: ${name}`, `
        <div id="sp-content"><p style="text-align:center;color:var(--gray-500)">Cargando...</p></div>
    `);
    try {
        const resp = await API.get(`/suppliers/${supplierId}/products`);
        const c = document.getElementById('sp-content');
        if (!resp.ok || !resp.data || !resp.data.length) {
            c.innerHTML = '<div class="empty-state"><p>Sin historial de compras registrado</p></div>';
            return;
        }
        c.innerHTML = `
            <p style="font-size:13px;color:var(--gray-500);margin-bottom:8px">${resp.data.length} productos vendidos</p>
            <div class="table-wrap"><table>
                <thead><tr>
                    <th>Producto</th><th>Categoria</th><th>UOM</th>
                    <th>Pedidos</th><th>Precio Med.</th><th>Min</th><th>Max</th>
                    <th>Ultimo Ped.</th>
                </tr></thead>
                <tbody>${resp.data.map(r => `
                    <tr>
                        <td><strong>${esc(r.product_name)}</strong></td>
                        <td>${r.category ? `<span class="badge badge-gray">${esc(r.category)}</span>` : '-'}</td>
                        <td>${esc(r.uom)}</td>
                        <td>${r.order_count}</td>
                        <td><strong>${Number(r.median_price).toFixed(2)}</strong></td>
                        <td>${Number(r.min_price).toFixed(2)}</td>
                        <td>${Number(r.max_price).toFixed(2)}</td>
                        <td>${r.last_order || '-'}</td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
        `;
    } catch (e) {
        document.getElementById('sp-content').innerHTML = `<p style="color:var(--danger)">Error: ${e.message}</p>`;
    }
}

function showAdminSupplierForm(editId) {
    const title = editId ? 'Editar Proveedor' : 'Nuevo Proveedor (Campo)';
    const catOptions = Object.entries(CATEGORY_META).map(([k, v]) =>
        `<label style="display:flex;align-items:center;gap:4px;font-size:13px">
            <input type="checkbox" name="cat_${k}" value="${k}"> ${v.icon} ${v.label}
        </label>`
    ).join('');

    showModal(title, `
        <form id="admin-supplier-form" onsubmit="handleAdminSupplier(event, ${editId || 'null'})">
            <div class="form-group">
                <label class="form-label">Nombre / Razon Social *</label>
                <input class="form-input" name="name" required placeholder="Ferreteria El Constructor">
            </div>
            <div class="form-group">
                <label class="form-label">Nombre comercial</label>
                <input class="form-input" name="trade_name" placeholder="El Constructor">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">NIT</label><input class="form-input" name="nit" placeholder="1234567890"></div>
                <div class="form-group"><label class="form-label">Email</label><input class="form-input" type="email" name="email" placeholder="contacto@empresa.com"></div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Telefono</label><input class="form-input" name="phone" placeholder="33445566"></div>
                <div class="form-group"><label class="form-label">WhatsApp *</label><input class="form-input" name="whatsapp" required placeholder="59177889900"></div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Ciudad *</label><input class="form-input" name="city" required placeholder="Santa Cruz de la Sierra"></div>
                <div class="form-group"><label class="form-label">Departamento *</label>
                    <select class="form-select" name="department" required>
                        <option value="">Seleccionar...</option>
                        ${DEPARTMENTS.map(d => `<option value="${d}">${d}</option>`).join('')}
                    </select>
                </div>
            </div>
            <div class="form-group"><label class="form-label">Direccion</label><input class="form-input" name="address" placeholder="Av. Principal #123, Zona Centro"></div>
            <div class="form-group">
                <label class="form-label">Categorias de productos *</label>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:4px">
                    ${catOptions}
                </div>
            </div>
            <div class="form-group"><label class="form-label">Canal preferido</label>
                <select class="form-select" name="preferred_channel">
                    <option value="whatsapp">WhatsApp</option>
                    <option value="email">Email</option>
                    <option value="telegram">Telegram</option>
                </select>
            </div>
            ${isManager() ? `
            <div class="form-group"><label class="form-label">Estado de verificacion</label>
                <select class="form-select" name="verification_state">
                    <option value="pending">Pendiente</option>
                    <option value="verified">Verificado</option>
                    <option value="rejected">Rechazado</option>
                </select>
            </div>` : ''}
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;padding:10px">
                ${editId ? 'Guardar Cambios' : 'Registrar Proveedor'}
            </button>
        </form>
    `);

    // If editing, load existing data
    if (editId) loadSupplierIntoForm(editId);
}

async function loadSupplierIntoForm(id) {
    try {
        const resp = await API.supplier(id);
        if (!resp.ok) return;
        const s = resp.data;
        const f = document.getElementById('admin-supplier-form');
        if (!f) return;
        if (s.name) f.name.value = s.name;
        if (s.trade_name) f.trade_name.value = s.trade_name;
        if (s.nit) f.nit.value = s.nit;
        if (s.email) f.email.value = s.email;
        if (s.phone) f.phone.value = s.phone;
        if (s.whatsapp) f.whatsapp.value = s.whatsapp;
        if (s.city) f.city.value = s.city;
        if (s.department) f.department.value = s.department;
        if (s.address) f.address.value = s.address;
        if (s.preferred_channel) f.preferred_channel.value = s.preferred_channel;
        if (f.verification_state && s.verification_state) f.verification_state.value = s.verification_state;
        // Check category checkboxes
        (s.categories || []).forEach(c => {
            const cb = f[`cat_${c}`];
            if (cb) cb.checked = true;
        });
    } catch {}
}

async function handleAdminSupplier(e, editId) {
    e.preventDefault();
    const f = e.target;

    // Collect checked categories
    const categories = Object.keys(CATEGORY_META).filter(k => f[`cat_${k}`]?.checked);

    const data = {
        name: f.name.value,
        trade_name: f.trade_name.value || null,
        nit: f.nit.value || null,
        email: f.email.value || null,
        phone: f.phone.value || null,
        whatsapp: f.whatsapp.value || null,
        city: f.city.value || null,
        department: f.department.value || null,
        address: f.address.value || null,
        categories: categories.length ? categories : null,
        preferred_channel: f.preferred_channel.value,
    };

    if (f.verification_state) {
        data.verification_state = f.verification_state.value;
    }

    try {
        const resp = editId
            ? await API.updateSupplier(editId, data)
            : await API.createSupplier(data);
        if (resp.ok) {
            closeModal();
            toast(editId ? 'Proveedor actualizado' : 'Proveedor registrado', 'success');
            loadAdminSuppliers();
        } else {
            toast(resp.detail || 'Error', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

// ── Admin: Products ────────────────────────────────────────────
async function renderAdminProducts() {
    const c = document.getElementById('admin-content');
    c.innerHTML = `
        <div class="search-bar">
            <input class="form-input" id="admin-product-search" placeholder="Buscar producto/insumo..." oninput="debounceAdminProducts()">
            <button class="btn btn-primary" onclick="showAdminProductForm()">
                ${icon('plus',16)} Nuevo
            </button>
        </div>
        <div id="admin-products-list"></div>
    `;
    loadAdminProducts();
}

let _admProdTimer;
function debounceAdminProducts() {
    clearTimeout(_admProdTimer);
    _admProdTimer = setTimeout(loadAdminProducts, 300);
}

async function loadAdminProducts() {
    const q = document.getElementById('admin-product-search')?.value?.trim() || '';
    let params = '?limit=100';
    if (q) params += `&q=${encodeURIComponent(q)}`;

    try {
        const resp = await API.insumos(params);
        const container = document.getElementById('admin-products-list');
        if (!container) return;
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = '<div class="empty-state"><p>No hay productos</p></div>';
            return;
        }
        container.innerHTML = `
            <div class="table-wrap"><table>
                <thead><tr>
                    <th>Nombre</th><th>Codigo</th><th>UOM</th><th>Categoria</th><th>Precio Ref.</th><th>Acciones</th>
                </tr></thead>
                <tbody>${resp.data.map(p => `
                    <tr>
                        <td><strong>${esc(p.name)}</strong></td>
                        <td>${p.code ? `<span class="badge badge-gray">${esc(p.code)}</span>` : '-'}</td>
                        <td>${esc(p.uom)}</td>
                        <td>${p.category ? esc(p.category) : '-'}</td>
                        <td>${p.ref_price ? `${p.ref_price.toFixed(2)} ${esc(p.ref_currency)}` : '-'}</td>
                        <td style="white-space:nowrap">
                            <button class="btn btn-sm btn-secondary" onclick="showPriceHistory(${p.id}, '${esc(p.name)}')" title="Ver historial de precios">${icon('trending-up',14)}</button>
                            <button class="btn btn-sm btn-secondary" onclick="showAdminProductForm(${p.id})">${icon('edit',14)}</button>
                        </td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
            <p style="margin-top:8px;font-size:13px;color:var(--gray-500)">${resp.total} productos</p>
        `;
    } catch { document.getElementById('admin-products-list').innerHTML = '<div class="empty-state"><p>Error cargando</p></div>'; }
}

function showAdminProductForm(editId) {
    const title = editId ? 'Editar Producto' : 'Nuevo Producto';
    const catSuggestions = Object.values(CATEGORY_META).map(v => v.label).join(', ') || 'Ferreteria, Acero, Cemento...';

    showModal(title, `
        <form id="admin-product-form" onsubmit="handleAdminProduct(event, ${editId || 'null'})">
            <div class="form-group">
                <label class="form-label">Nombre del producto *</label>
                <input class="form-input" name="name" required placeholder="Ej: Cemento Portland IP-30">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Unidad de medida *</label>
                    <select class="form-select" name="uom" required>
                        ${UOM_LIST.length ? UOM_LIST.map(u => `<option value="${esc(u.key)}">${esc(u.key)} - ${esc(u.label)}</option>`).join('') :
                        `<option value="bls">bls (Bolsa)</option><option value="kg">kg</option><option value="tn">tn (Tonelada)</option>
                        <option value="m3">m3</option><option value="m2">m2</option><option value="ml">ml (Metro lineal)</option>
                        <option value="pza">pza (Pieza)</option><option value="lt">lt (Litro)</option><option value="gl">gl (Galon)</option>
                        <option value="glb">glb (Global)</option><option value="rollo">rollo</option><option value="varilla">varilla</option>`}
                    </select>
                </div>
                <div class="form-group"><label class="form-label">Codigo</label><input class="form-input" name="code" placeholder="CEM-001"></div>
            </div>
            <div class="form-group">
                <label class="form-label">Categoria</label>
                <input class="form-input" name="category" placeholder="${catSuggestions}" list="cat-suggestions">
                <datalist id="cat-suggestions">
                    ${Object.values(CATEGORY_META).map(v => `<option value="${v.label}">`).join('')}
                </datalist>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Precio referencial</label><input class="form-input" type="number" step="0.01" name="ref_price" placeholder="0.00"></div>
                <div class="form-group"><label class="form-label">Moneda</label>
                    <select class="form-select" name="ref_currency"><option value="BOB">BOB</option><option value="USD">USD</option></select>
                </div>
            </div>
            <div class="form-group"><label class="form-label">Descripcion</label><textarea class="form-input" name="description" placeholder="Descripcion adicional del producto..."></textarea></div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;padding:10px">
                ${editId ? 'Guardar Cambios' : 'Crear Producto'}
            </button>
        </form>
    `);

    if (editId) loadProductIntoForm(editId);
}

async function loadProductIntoForm(id) {
    try {
        const resp = await API.insumo(id);
        if (!resp.ok) return;
        const p = resp.data;
        const f = document.getElementById('admin-product-form');
        if (!f) return;
        if (p.name) f.name.value = p.name;
        if (p.uom) f.uom.value = p.uom;
        if (p.code) f.code.value = p.code;
        if (p.category) f.category.value = p.category;
        if (p.ref_price) f.ref_price.value = p.ref_price;
        if (p.ref_currency) f.ref_currency.value = p.ref_currency;
        if (p.description) f.description.value = p.description;
    } catch {}
}

async function handleAdminProduct(e, editId) {
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

    try {
        const resp = editId
            ? await API.put(`/prices/${editId}`, data)
            : await API.createInsumo(data);
        if (resp.ok) {
            closeModal();
            toast(editId ? 'Producto actualizado' : 'Producto creado', 'success');
            loadAdminProducts();
        } else {
            toast(resp.detail || 'Error', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

// ── Price History Modal ───────────────────────────────────────
async function showPriceHistory(insumoId, name) {
    showModal(`Historial de Precios: ${name}`, `
        <div id="ph-content" style="min-height:200px">
            <p style="text-align:center;color:var(--gray-500)">Cargando historial...</p>
        </div>
    `);

    const container = document.getElementById('ph-content');
    try {
        const [evoResp, histResp, supResp] = await Promise.all([
            API.get(`/prices/${insumoId}/evolution`),
            API.get(`/prices/${insumoId}/history?limit=30`),
            API.get(`/prices/${insumoId}/suppliers`),
        ]);

        let html = '';

        // Evolution table
        if (evoResp.ok && evoResp.evolution && evoResp.evolution.length > 0) {
            html += `
                <div style="margin-bottom:16px">
                    <h4 style="margin:0 0 8px;font-size:14px;color:var(--gray-700)">Evolucion por anio (${evoResp.total_records} registros totales)</h4>
                    <div class="table-wrap"><table>
                        <thead><tr>
                            <th>Anio</th><th>Muestras</th><th>Mediana</th><th>Promedio</th><th>Min</th><th>Max</th>
                        </tr></thead>
                        <tbody>${evoResp.evolution.map(r => `
                            <tr>
                                <td><strong>${r.year}</strong></td>
                                <td>${r.samples}</td>
                                <td><strong>${Number(r.median_price).toFixed(2)}</strong></td>
                                <td>${Number(r.avg_price).toFixed(2)}</td>
                                <td>${Number(r.min_price).toFixed(2)}</td>
                                <td>${Number(r.max_price).toFixed(2)}</td>
                            </tr>
                        `).join('')}</tbody>
                    </table></div>
                </div>

                <div style="margin-bottom:16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                    <button class="btn btn-primary btn-sm" onclick="refreshPrice(${insumoId})">
                        ${icon('trending-up', 14)} Actualizar precio ref. (mediana 12 meses)
                    </button>
                    <button class="btn btn-secondary btn-sm" onclick="showAddPriceForm(${insumoId}, '${esc(name)}')">
                        ${icon('plus', 14)} Agregar precio manual
                    </button>
                    <span id="refresh-result" style="font-size:13px;color:var(--gray-500)"></span>
                </div>
            `;

            // Simple bar chart visualization
            const maxMedian = Math.max(...evoResp.evolution.map(r => Number(r.median_price)));
            html += `
                <div style="margin-bottom:16px">
                    <h4 style="margin:0 0 8px;font-size:14px;color:var(--gray-700)">Tendencia de precio (mediana)</h4>
                    <div style="display:flex;align-items:flex-end;gap:4px;height:120px;padding:8px;background:var(--gray-50);border-radius:8px">
                        ${evoResp.evolution.map(r => {
                            const pct = maxMedian > 0 ? (Number(r.median_price) / maxMedian * 100) : 0;
                            return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px">
                                <span style="font-size:10px;color:var(--gray-600)">${Number(r.median_price).toFixed(0)}</span>
                                <div style="width:100%;background:var(--primary);border-radius:4px 4px 0 0;height:${Math.max(pct, 3)}%" title="${r.year}: ${Number(r.median_price).toFixed(2)} Bs"></div>
                                <span style="font-size:10px;color:var(--gray-500)">${r.year}</span>
                            </div>`;
                        }).join('')}
                    </div>
                </div>
            `;
        } else {
            html += `
                <div class="empty-state" style="margin-bottom:16px">
                    <p>Sin historial de precios</p>
                    <button class="btn btn-primary btn-sm" onclick="showAddPriceForm(${insumoId}, '${esc(name)}')">
                        ${icon('plus', 14)} Agregar primer precio
                    </button>
                </div>
            `;
        }

        // Suppliers for this product
        if (supResp.ok && supResp.data && supResp.data.length > 0) {
            html += `
                <div style="margin-bottom:16px">
                    <h4 style="margin:0 0 8px;font-size:14px;color:var(--gray-700)">Proveedores (${supResp.data.length})</h4>
                    <div class="table-wrap"><table>
                        <thead><tr>
                            <th>Proveedor</th><th>Ciudad</th><th>Pedidos</th>
                            <th>Precio Med.</th><th>Min</th><th>Max</th><th>Ultimo Ped.</th>
                        </tr></thead>
                        <tbody>${supResp.data.map(r => `
                            <tr>
                                <td><strong>${esc(r.supplier_name)}</strong></td>
                                <td>${r.city || r.department || '-'}</td>
                                <td>${r.order_count}</td>
                                <td><strong>${Number(r.median_price).toFixed(2)}</strong></td>
                                <td>${Number(r.min_price).toFixed(2)}</td>
                                <td>${Number(r.max_price).toFixed(2)}</td>
                                <td>${r.last_order || '-'}</td>
                            </tr>
                        `).join('')}</tbody>
                    </table></div>
                </div>
            `;
        }

        // Recent records
        if (histResp.ok && histResp.data && histResp.data.length > 0) {
            html += `
                <div>
                    <h4 style="margin:0 0 8px;font-size:14px;color:var(--gray-700)">Ultimos registros</h4>
                    <div class="table-wrap"><table>
                        <thead><tr>
                            <th>Fecha</th><th>Precio Unit.</th><th>Cantidad</th><th>Fuente</th><th>Ref.</th>
                        </tr></thead>
                        <tbody>${histResp.data.map(r => `
                            <tr>
                                <td>${r.observed_date}</td>
                                <td><strong>${r.unit_price.toFixed(2)} ${esc(r.currency)}</strong></td>
                                <td>${r.quantity || '-'}</td>
                                <td><span class="badge badge-${r.source === 'manual' ? 'warning' : 'gray'}">${esc(r.source)}</span></td>
                                <td>${r.source_ref ? esc(r.source_ref) : '-'}</td>
                            </tr>
                        `).join('')}</tbody>
                    </table></div>
                </div>
            `;
        }

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><p>Error cargando historial: ${e.message}</p></div>`;
    }
}

function showAddPriceForm(insumoId, name) {
    const today = new Date().toISOString().split('T')[0];
    showModal(`Agregar precio: ${name}`, `
        <form id="add-price-form" onsubmit="handleAddPrice(event, ${insumoId}, '${esc(name)}')">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Precio unitario *</label>
                    <input class="form-input" type="number" step="0.01" name="unit_price" required placeholder="0.00">
                </div>
                <div class="form-group">
                    <label class="form-label">Moneda</label>
                    <select class="form-select" name="currency">
                        <option value="BOB">BOB (Bolivianos)</option>
                        <option value="USD">USD (Dolares)</option>
                    </select>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Fecha *</label>
                    <input class="form-input" type="date" name="observed_date" required value="${today}">
                </div>
                <div class="form-group">
                    <label class="form-label">Cantidad</label>
                    <input class="form-input" type="number" step="0.01" name="quantity" placeholder="1">
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Fuente</label>
                <select class="form-select" name="source">
                    <option value="manual">Manual</option>
                    <option value="cotizacion">Cotizacion</option>
                    <option value="pedido">Pedido</option>
                </select>
            </div>
            <div class="form-group">
                <label class="form-label">Referencia / Nota</label>
                <input class="form-input" name="source_ref" placeholder="Ej: cotizacion proveedor X, precio mercado abril 2026...">
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;padding:10px">
                Guardar precio
            </button>
        </form>
    `);
}

async function handleAddPrice(e, insumoId, name) {
    e.preventDefault();
    const f = e.target;
    try {
        const resp = await API.post(`/prices/${insumoId}/add-price`, {
            unit_price: parseFloat(f.unit_price.value),
            currency: f.currency.value,
            observed_date: f.observed_date.value,
            quantity: f.quantity.value ? parseFloat(f.quantity.value) : null,
            source: f.source.value,
            source_ref: f.source_ref.value || null,
        });
        if (resp.ok) {
            closeModal();
            toast('Precio agregado', 'success');
            showPriceHistory(insumoId, name);
        } else {
            toast(resp.detail || 'Error', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

async function refreshPrice(insumoId) {
    const resultSpan = document.getElementById('refresh-result');
    if (resultSpan) resultSpan.textContent = 'Calculando...';
    try {
        const resp = await API.post(`/prices/${insumoId}/refresh-price`);
        if (resp.ok) {
            const msg = `Precio actualizado: ${resp.ref_price} Bs (${resp.sample_count} muestras, ${resp.period})`;
            if (resultSpan) resultSpan.textContent = msg;
            toast(msg, 'success');
            loadAdminProducts();
        } else {
            if (resultSpan) resultSpan.textContent = resp.detail || 'Error';
            toast(resp.detail || 'Error', 'error');
        }
    } catch {
        if (resultSpan) resultSpan.textContent = 'Error de conexion';
    }
}

// ── Admin: Categories ─────────────────────────────────────────
async function renderAdminCategories() {
    if (!isAdmin()) { toast('Sin permisos', 'error'); return; }
    const c = document.getElementById('admin-content');
    c.innerHTML = `
        <div class="search-bar">
            <span style="font-size:14px;color:var(--gray-500)">Gestionar categorias de materiales y proveedores</span>
            <button class="btn btn-primary" onclick="showCategoryForm()">
                ${icon('plus',16)} Nueva Categoria
            </button>
        </div>
        <div id="admin-categories-list"></div>
    `;
    loadAdminCategories();
}

async function loadAdminCategories() {
    try {
        const resp = await API.adminCategories();
        const container = document.getElementById('admin-categories-list');
        if (!container) return;
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = '<div class="empty-state"><p>No hay categorias</p></div>';
            return;
        }
        container.innerHTML = `
            <div class="table-wrap"><table>
                <thead><tr>
                    <th>Orden</th><th>Key</th><th>Nombre</th><th>Icono</th><th>Activa</th><th>Acciones</th>
                </tr></thead>
                <tbody>${resp.data.map(c => `
                    <tr>
                        <td>${c.sort_order}</td>
                        <td><code>${esc(c.key)}</code></td>
                        <td><strong>${esc(c.label)}</strong>${c.description ? `<br><small style="color:var(--gray-500)">${esc(c.description)}</small>` : ''}</td>
                        <td style="font-size:20px">${c.icon || '-'}</td>
                        <td>${c.is_active ? '<span style="color:var(--success)">Si</span>' : '<span style="color:var(--danger)">No</span>'}</td>
                        <td style="white-space:nowrap">
                            <button class="btn btn-sm btn-secondary" onclick="showCategoryForm(${c.id})" title="Editar">${icon('edit',14)}</button>
                            <button class="btn btn-sm btn-secondary" onclick="deleteCategory(${c.id}, '${esc(c.label)}')" title="Eliminar" style="color:var(--danger)">${icon('trash',14)}</button>
                        </td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
            <p style="margin-top:8px;font-size:13px;color:var(--gray-500)">${resp.data.length} categorias</p>
        `;
    } catch { document.getElementById('admin-categories-list').innerHTML = '<div class="empty-state"><p>Error cargando</p></div>'; }
}

function showCategoryForm(editId) {
    const title = editId ? 'Editar Categoria' : 'Nueva Categoria';
    showModal(title, `
        <form id="admin-category-form" onsubmit="handleCategory(event, ${editId || 'null'})">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Key (identificador unico) *</label>
                    <input class="form-input" name="key" required placeholder="ej: ferreteria" pattern="[a-z0-9_]+" title="Solo minusculas, numeros y guion bajo">
                </div>
                <div class="form-group">
                    <label class="form-label">Nombre visible *</label>
                    <input class="form-input" name="label" required placeholder="Ferreteria">
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Icono (HTML entity o emoji)</label>
                    <input class="form-input" name="icon" placeholder="&#128295; o pegar emoji">
                </div>
                <div class="form-group">
                    <label class="form-label">Orden</label>
                    <input class="form-input" type="number" name="sort_order" value="0" min="0">
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Descripcion</label>
                <input class="form-input" name="description" placeholder="Descripcion opcional de la categoria">
            </div>
            ${editId ? `
            <div class="form-group">
                <label class="form-label">Estado</label>
                <select class="form-select" name="is_active">
                    <option value="true">Activa</option>
                    <option value="false">Inactiva</option>
                </select>
            </div>` : ''}
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;padding:10px">
                ${editId ? 'Guardar Cambios' : 'Crear Categoria'}
            </button>
        </form>
    `);

    if (editId) loadCategoryIntoForm(editId);
}

async function loadCategoryIntoForm(id) {
    try {
        const resp = await API.adminCategories();
        if (!resp.ok) return;
        const cat = resp.data.find(c => c.id === id);
        if (!cat) return;
        const f = document.getElementById('admin-category-form');
        if (!f) return;
        f.key.value = cat.key;
        f.label.value = cat.label;
        if (cat.icon) f.icon.value = cat.icon;
        f.sort_order.value = cat.sort_order;
        if (cat.description) f.description.value = cat.description;
        if (f.is_active) f.is_active.value = cat.is_active ? 'true' : 'false';
    } catch {}
}

async function handleCategory(e, editId) {
    e.preventDefault();
    const f = e.target;
    const data = {
        key: f.key.value.trim(),
        label: f.label.value.trim(),
        icon: f.icon.value.trim() || null,
        sort_order: parseInt(f.sort_order.value) || 0,
        description: f.description.value.trim() || null,
    };
    if (editId && f.is_active) {
        data.is_active = f.is_active.value === 'true';
    }

    try {
        const resp = editId
            ? await API.adminUpdateCategory(editId, data)
            : await API.adminCreateCategory(data);
        if (resp.ok) {
            closeModal();
            toast(editId ? 'Categoria actualizada' : 'Categoria creada', 'success');
            loadAdminCategories();
            loadCatalogData();
        } else {
            toast(resp.detail || 'Error', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

async function deleteCategory(id, name) {
    if (!confirm(`Eliminar la categoria "${name}"? Esta accion no se puede deshacer.`)) return;
    try {
        const resp = await API.adminDeleteCategory(id);
        if (resp.ok) {
            toast('Categoria eliminada', 'success');
            loadAdminCategories();
            loadCatalogData();
        } else {
            toast(resp.detail || 'Error', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

// ── Admin: Units of Measure ───────────────────────────────────
async function renderAdminUoms() {
    if (!isAdmin()) { toast('Sin permisos', 'error'); return; }
    const c = document.getElementById('admin-content');
    c.innerHTML = `
        <div class="search-bar">
            <span style="font-size:14px;color:var(--gray-500)">Gestionar unidades de medida y sus aliases para el matching</span>
            <button class="btn btn-primary" onclick="showUomForm()">
                ${icon('plus',16)} Nueva Unidad
            </button>
        </div>
        <div id="admin-uoms-list"></div>
    `;
    loadAdminUoms();
}

async function loadAdminUoms() {
    try {
        const resp = await API.adminUoms();
        const container = document.getElementById('admin-uoms-list');
        if (!container) return;
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = '<div class="empty-state"><p>No hay unidades</p></div>';
            return;
        }
        container.innerHTML = `
            <div class="table-wrap"><table>
                <thead><tr>
                    <th>Orden</th><th>Key</th><th>Nombre</th><th>Aliases</th><th>Activa</th><th>Acciones</th>
                </tr></thead>
                <tbody>${resp.data.map(u => `
                    <tr>
                        <td>${u.sort_order}</td>
                        <td><code>${esc(u.key)}</code></td>
                        <td><strong>${esc(u.label)}</strong></td>
                        <td>${(u.aliases || []).map(a => `<span class="supplier-cat">${esc(a)}</span>`).join(' ') || '-'}</td>
                        <td>${u.is_active ? '<span style="color:var(--success)">Si</span>' : '<span style="color:var(--danger)">No</span>'}</td>
                        <td style="white-space:nowrap">
                            <button class="btn btn-sm btn-secondary" onclick="showUomForm(${u.id})" title="Editar">${icon('edit',14)}</button>
                            <button class="btn btn-sm btn-secondary" onclick="deleteUom(${u.id}, '${esc(u.label)}')" title="Eliminar" style="color:var(--danger)">${icon('trash',14)}</button>
                        </td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
            <p style="margin-top:8px;font-size:13px;color:var(--gray-500)">${resp.data.length} unidades de medida</p>
        `;
    } catch { document.getElementById('admin-uoms-list').innerHTML = '<div class="empty-state"><p>Error cargando</p></div>'; }
}

function showUomForm(editId) {
    const title = editId ? 'Editar Unidad de Medida' : 'Nueva Unidad de Medida';
    showModal(title, `
        <form id="admin-uom-form" onsubmit="handleUom(event, ${editId || 'null'})">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Key (abreviatura) *</label>
                    <input class="form-input" name="key" required placeholder="ej: m3, kg, pza">
                </div>
                <div class="form-group">
                    <label class="form-label">Nombre descriptivo *</label>
                    <input class="form-input" name="label" required placeholder="Metro cubico (m3)">
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Aliases (separados por coma)</label>
                <input class="form-input" name="aliases" placeholder="metro cubico, metros cubicos, m&#179;">
                <small style="color:var(--gray-500)">Nombres alternativos que el sistema reconoce como esta unidad</small>
            </div>
            <div class="form-group">
                <label class="form-label">Orden</label>
                <input class="form-input" type="number" name="sort_order" value="0" min="0">
            </div>
            ${editId ? `
            <div class="form-group">
                <label class="form-label">Estado</label>
                <select class="form-select" name="is_active">
                    <option value="true">Activa</option>
                    <option value="false">Inactiva</option>
                </select>
            </div>` : ''}
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;padding:10px">
                ${editId ? 'Guardar Cambios' : 'Crear Unidad'}
            </button>
        </form>
    `);

    if (editId) loadUomIntoForm(editId);
}

async function loadUomIntoForm(id) {
    try {
        const resp = await API.adminUoms();
        if (!resp.ok) return;
        const uom = resp.data.find(u => u.id === id);
        if (!uom) return;
        const f = document.getElementById('admin-uom-form');
        if (!f) return;
        f.key.value = uom.key;
        f.label.value = uom.label;
        f.aliases.value = (uom.aliases || []).join(', ');
        f.sort_order.value = uom.sort_order;
        if (f.is_active) f.is_active.value = uom.is_active ? 'true' : 'false';
    } catch {}
}

async function handleUom(e, editId) {
    e.preventDefault();
    const f = e.target;
    const aliasStr = f.aliases.value.trim();
    const aliases = aliasStr ? aliasStr.split(',').map(a => a.trim()).filter(a => a) : null;

    const data = {
        key: f.key.value.trim(),
        label: f.label.value.trim(),
        aliases: aliases,
        sort_order: parseInt(f.sort_order.value) || 0,
    };
    if (editId && f.is_active) {
        data.is_active = f.is_active.value === 'true';
    }

    try {
        const resp = editId
            ? await API.adminUpdateUom(editId, data)
            : await API.adminCreateUom(data);
        if (resp.ok) {
            closeModal();
            toast(editId ? 'Unidad actualizada' : 'Unidad creada', 'success');
            loadAdminUoms();
            loadCatalogData();
        } else {
            toast(resp.detail || 'Error', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

async function deleteUom(id, name) {
    if (!confirm(`Eliminar la unidad "${name}"? Esta accion no se puede deshacer.`)) return;
    try {
        const resp = await API.adminDeleteUom(id);
        if (resp.ok) {
            toast('Unidad eliminada', 'success');
            loadAdminUoms();
            loadCatalogData();
        } else {
            toast(resp.detail || 'Error', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

// ── Admin: Users ───────────────────────────────────────────────
async function renderAdminUsers() {
    if (!isManager()) { toast('Sin permisos', 'error'); return; }

    const c = document.getElementById('admin-content');
    c.innerHTML = `
        <div class="search-bar">
            <input class="form-input" id="admin-user-search" placeholder="Buscar por nombre o email..." oninput="debounceAdminUsers()">
            <select class="form-select" id="admin-user-role" onchange="loadAdminUsers()" style="max-width:180px">
                <option value="">Todos los roles</option>
                <option value="admin">Admin</option>
                <option value="manager">Gestor</option>
                <option value="field_agent">Agente de Campo</option>
                <option value="user">Usuario</option>
                <option value="supplier">Proveedor</option>
            </select>
            <button class="btn btn-primary" onclick="showAdminUserForm()">
                ${icon('user-plus',16)} Nuevo
            </button>
        </div>
        <div id="admin-users-list"></div>
    `;
    loadAdminUsers();
}

let _admUsrTimer;
function debounceAdminUsers() {
    clearTimeout(_admUsrTimer);
    _admUsrTimer = setTimeout(loadAdminUsers, 300);
}

async function loadAdminUsers() {
    const q = document.getElementById('admin-user-search')?.value?.trim() || '';
    const role = document.getElementById('admin-user-role')?.value || '';
    let params = '?limit=100';
    if (q) params += `&q=${encodeURIComponent(q)}`;
    if (role) params += `&role=${encodeURIComponent(role)}`;

    try {
        const resp = await API.adminUsers(params);
        const container = document.getElementById('admin-users-list');
        if (!container) return;
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = '<div class="empty-state"><p>No hay usuarios</p></div>';
            return;
        }
        container.innerHTML = `
            <div class="table-wrap"><table>
                <thead><tr>
                    <th>Nombre</th><th>Email</th><th>Rol</th><th>Empresa</th><th>Activo</th><th>Ultimo acceso</th><th>Acciones</th>
                </tr></thead>
                <tbody>${resp.data.map(u => `
                    <tr>
                        <td><strong>${esc(u.full_name)}</strong></td>
                        <td>${esc(u.email)}</td>
                        <td><span class="badge badge-${ROLE_COLORS[u.role] || 'gray'}">${ROLE_LABELS[u.role] || u.role}</span></td>
                        <td>${u.company_name ? esc(u.company_name) : '-'}</td>
                        <td>${u.is_active ? '<span style="color:var(--success)">Si</span>' : '<span style="color:var(--danger)">No</span>'}</td>
                        <td>${u.last_login ? new Date(u.last_login).toLocaleDateString('es') : 'Nunca'}</td>
                        <td style="white-space:nowrap">
                            <button class="btn btn-sm btn-secondary" onclick="showEditUserModal(${u.id}, '${esc(u.full_name)}', '${esc(u.role)}', ${u.is_active})" title="Editar">${icon('edit',14)}</button>
                            ${isAdmin() ? `<button class="btn btn-sm btn-secondary" onclick="resetUserPassword(${u.id}, '${esc(u.full_name)}')" title="Resetear contrasena">${icon('key',14)}</button>` : ''}
                        </td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
            <p style="margin-top:8px;font-size:13px;color:var(--gray-500)">${resp.total} usuarios</p>
        `;
    } catch { document.getElementById('admin-users-list').innerHTML = '<div class="empty-state"><p>Error cargando</p></div>'; }
}

function showAdminUserForm() {
    const roleOptions = isAdmin()
        ? `<option value="field_agent" selected>Agente de Campo</option>
           <option value="manager">Gestor</option>
           <option value="admin">Administrador</option>
           <option value="user">Usuario</option>`
        : `<option value="field_agent" selected>Agente de Campo</option>
           <option value="user">Usuario</option>`;

    showModal('Crear Usuario', `
        <form id="admin-user-form" onsubmit="handleCreateUser(event)">
            <div class="form-group">
                <label class="form-label">Nombre completo *</label>
                <input class="form-input" name="full_name" required placeholder="Juan Perez">
            </div>
            <div class="form-group">
                <label class="form-label">Email *</label>
                <input class="form-input" type="email" name="email" required placeholder="juan@empresa.com">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Telefono</label><input class="form-input" name="phone" placeholder="77889900"></div>
                <div class="form-group"><label class="form-label">Empresa</label><input class="form-input" name="company_name" placeholder="SSA Ingenieria"></div>
            </div>
            <div class="form-group">
                <label class="form-label">Rol *</label>
                <select class="form-select" name="role">${roleOptions}</select>
            </div>
            <div class="form-group">
                <label class="form-label">Contrasena temporal *</label>
                <input class="form-input" name="password" required minlength="6" placeholder="Min. 6 caracteres" value="${generateTempPassword()}">
                <small style="color:var(--gray-500)">El usuario debera cambiarla al ingresar</small>
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;padding:10px">
                Crear Usuario
            </button>
        </form>
    `);
}

function generateTempPassword() {
    const chars = 'abcdefghjkmnpqrstuvwxyz23456789';
    let pwd = '';
    for (let i = 0; i < 8; i++) pwd += chars[Math.floor(Math.random() * chars.length)];
    return pwd;
}

async function handleCreateUser(e) {
    e.preventDefault();
    const f = e.target;
    const data = {
        email: f.email.value,
        password: f.password.value,
        full_name: f.full_name.value,
        role: f.role.value,
        phone: f.phone.value || null,
        company_name: f.company_name.value || null,
    };
    try {
        const resp = await API.adminCreateUser(data);
        if (resp.ok) {
            closeModal();
            toast(`Usuario ${data.full_name} creado como ${ROLE_LABELS[data.role]}. Contrasena: ${data.password}`, 'success');
            loadAdminUsers();
        } else {
            toast(resp.detail || 'Error al crear usuario', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

function showEditUserModal(userId, name, currentRole, isActive) {
    const roleOptions = isAdmin()
        ? ['admin','manager','field_agent','user','supplier'].map(r =>
            `<option value="${r}"${r === currentRole ? ' selected' : ''}>${ROLE_LABELS[r]}</option>`).join('')
        : `<option value="${currentRole}" selected>${ROLE_LABELS[currentRole] || currentRole}</option>`;

    showModal(`Editar: ${name}`, `
        <form onsubmit="handleUpdateUser(event, ${userId})">
            <div class="form-group">
                <label class="form-label">Rol</label>
                <select class="form-select" name="role">${roleOptions}</select>
            </div>
            <div class="form-group">
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
                    <input type="checkbox" name="is_active" ${isActive ? 'checked' : ''}>
                    <span class="form-label" style="margin:0">Cuenta activa</span>
                </label>
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center">Guardar</button>
        </form>
    `);
}

async function handleUpdateUser(e, userId) {
    e.preventDefault();
    const f = e.target;
    try {
        const resp = await API.adminUpdateUser(userId, {
            role: f.role.value,
            is_active: f.is_active.checked,
        });
        if (resp.ok) { closeModal(); toast('Usuario actualizado', 'success'); loadAdminUsers(); }
        else toast(resp.detail || 'Error', 'error');
    } catch { toast('Error de conexion', 'error'); }
}

async function resetUserPassword(userId, name) {
    if (!confirm(`Resetear contrasena de ${name}?`)) return;
    try {
        const resp = await API.adminResetPassword(userId);
        if (resp.ok) {
            toast(`Nueva contrasena temporal para ${name}: ${resp.temp_password}`, 'success');
        } else {
            toast(resp.detail || 'Error', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

// ── Admin: API Keys ────────────────────────────────────────────
async function renderAdminApiKeys() {
    if (!isAdmin()) { toast('Sin permisos', 'error'); return; }

    const c = document.getElementById('admin-content');
    c.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
            <div>
                <p style="font-size:13px;color:var(--gray-500)">
                    Las API keys permiten a integraciones externas (n8n, MCP, Zapier) acceder a los datos.
                    <br>Endpoint base: <code>/api/v1/integration/</code> con header <code>X-API-Key</code>
                </p>
            </div>
            <button class="btn btn-primary" onclick="showCreateApiKeyModal()">
                ${icon('plus',16)} Nueva API Key
            </button>
        </div>
        <div id="admin-apikeys-list"><div class="empty-state"><p>Cargando...</p></div></div>
    `;
    loadAdminApiKeys();
}

async function loadAdminApiKeys() {
    try {
        const resp = await API.apiKeys();
        const container = document.getElementById('admin-apikeys-list');
        if (!container) return;
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = '<div class="empty-state"><p>No hay API keys creadas</p></div>';
            return;
        }
        container.innerHTML = `
            <div class="table-wrap"><table>
                <thead><tr>
                    <th>Nombre</th><th>Key</th><th>Permisos</th><th>Estado</th>
                    <th>Expiracion</th><th>Ultimo uso</th><th>Usos</th><th>Acciones</th>
                </tr></thead>
                <tbody>${resp.data.map(k => {
                    const isExpired = k.expires_at && new Date(k.expires_at) < new Date();
                    const statusBadge = !k.is_active
                        ? '<span class="badge badge-danger">Revocada</span>'
                        : isExpired
                            ? '<span class="badge badge-warning">Expirada</span>'
                            : '<span class="badge badge-success">Activa</span>';
                    const scopeBadges = (k.scopes || '').split(',').map(s =>
                        `<span class="badge badge-gray">${esc(s.trim())}</span>`).join(' ');
                    return `
                    <tr style="${!k.is_active ? 'opacity:0.5' : ''}">
                        <td><strong>${esc(k.name)}</strong>${k.description ? `<br><small style="color:var(--gray-500)">${esc(k.description)}</small>` : ''}</td>
                        <td><code>${esc(k.key_prefix)}...</code></td>
                        <td>${scopeBadges}</td>
                        <td>${statusBadge}</td>
                        <td>${k.expires_at ? new Date(k.expires_at).toLocaleDateString('es') : 'Sin expiracion'}</td>
                        <td>${k.last_used_at ? new Date(k.last_used_at).toLocaleDateString('es') : 'Nunca'}</td>
                        <td>${k.usage_count}</td>
                        <td style="white-space:nowrap">
                            <button class="btn btn-sm btn-secondary" onclick="showEditApiKeyModal(${k.id}, '${esc(k.name)}', '${esc(k.scopes)}', ${k.is_active})">${icon('edit',14)}</button>
                            ${k.is_active ? `<button class="btn btn-sm btn-secondary" style="color:var(--danger)" onclick="revokeApiKey(${k.id}, '${esc(k.name)}')" title="Revocar">${icon('trash',14)}</button>` : ''}
                        </td>
                    </tr>`;
                }).join('')}</tbody>
            </table></div>
        `;
    } catch { document.getElementById('admin-apikeys-list').innerHTML = '<div class="empty-state"><p>Error cargando</p></div>'; }
}

function showCreateApiKeyModal() {
    showModal('Crear API Key', `
        <form id="create-apikey-form" onsubmit="handleCreateApiKey(event)">
            <div class="form-group">
                <label class="form-label">Nombre *</label>
                <input class="form-input" name="name" required placeholder="Ej: n8n Produccion, MCP Claude, Zapier">
            </div>
            <div class="form-group">
                <label class="form-label">Descripcion</label>
                <input class="form-input" name="description" placeholder="Para que se usa esta key">
            </div>
            <div class="form-group">
                <label class="form-label">Permisos</label>
                <div style="display:flex;gap:12px;margin-top:4px">
                    <label style="display:flex;align-items:center;gap:4px;font-size:13px"><input type="checkbox" name="scope_read" checked> Leer</label>
                    <label style="display:flex;align-items:center;gap:4px;font-size:13px"><input type="checkbox" name="scope_write" checked> Escribir</label>
                    <label style="display:flex;align-items:center;gap:4px;font-size:13px"><input type="checkbox" name="scope_delete"> Eliminar</label>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Expiracion</label>
                <select class="form-select" name="expires_in_days">
                    <option value="">Sin expiracion</option>
                    <option value="7">7 dias</option>
                    <option value="30">30 dias</option>
                    <option value="90" selected>90 dias</option>
                    <option value="180">6 meses</option>
                    <option value="365">1 ano</option>
                </select>
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;padding:10px">
                Generar API Key
            </button>
        </form>
    `);
}

async function handleCreateApiKey(e) {
    e.preventDefault();
    const f = e.target;
    const scopes = [];
    if (f.scope_read.checked) scopes.push('read');
    if (f.scope_write.checked) scopes.push('write');
    if (f.scope_delete.checked) scopes.push('delete');

    const data = {
        name: f.name.value,
        description: f.description.value || null,
        scopes: scopes.join(',') || 'read',
        expires_in_days: f.expires_in_days.value ? parseInt(f.expires_in_days.value) : null,
    };

    try {
        const resp = await API.createApiKey(data);
        if (resp.ok) {
            closeModal();
            // Show the raw key in a special modal — only shown once!
            showModal('API Key Creada', `
                <div style="text-align:center;padding:8px 0">
                    <p style="color:var(--danger);font-weight:600;margin-bottom:12px">
                        Copia esta key ahora. No se puede recuperar despues.
                    </p>
                    <div style="background:var(--gray-100);padding:16px;border-radius:var(--radius);margin-bottom:16px;word-break:break-all">
                        <code id="raw-key-display" style="font-size:15px;user-select:all">${esc(resp.data.raw_key)}</code>
                    </div>
                    <button class="btn btn-primary" onclick="copyApiKey('${esc(resp.data.raw_key)}')" style="margin-bottom:8px">
                        Copiar al portapapeles
                    </button>
                    <p style="font-size:12px;color:var(--gray-500);margin-top:8px">
                        Usa esta key en el header <code>X-API-Key</code> de tus peticiones HTTP.
                    </p>
                </div>
            `);
            loadAdminApiKeys();
        } else {
            toast(resp.detail || 'Error al crear key', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

function copyApiKey(key) {
    navigator.clipboard.writeText(key).then(() => {
        toast('API Key copiada al portapapeles', 'success');
    }).catch(() => {
        // Fallback: select the text
        const el = document.getElementById('raw-key-display');
        if (el) {
            const range = document.createRange();
            range.selectNodeContents(el);
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(range);
            toast('Selecciona y copia manualmente (Ctrl+C)', 'info');
        }
    });
}

function showEditApiKeyModal(keyId, name, scopes, isActive) {
    const scopeList = scopes.split(',').map(s => s.trim());
    showModal(`Editar: ${name}`, `
        <form onsubmit="handleUpdateApiKey(event, ${keyId})">
            <div class="form-group">
                <label class="form-label">Nombre</label>
                <input class="form-input" name="name" value="${esc(name)}">
            </div>
            <div class="form-group">
                <label class="form-label">Permisos</label>
                <div style="display:flex;gap:12px;margin-top:4px">
                    <label style="display:flex;align-items:center;gap:4px;font-size:13px"><input type="checkbox" name="scope_read" ${scopeList.includes('read') ? 'checked' : ''}> Leer</label>
                    <label style="display:flex;align-items:center;gap:4px;font-size:13px"><input type="checkbox" name="scope_write" ${scopeList.includes('write') ? 'checked' : ''}> Escribir</label>
                    <label style="display:flex;align-items:center;gap:4px;font-size:13px"><input type="checkbox" name="scope_delete" ${scopeList.includes('delete') ? 'checked' : ''}> Eliminar</label>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Renovar expiracion</label>
                <select class="form-select" name="expires_in_days">
                    <option value="">No cambiar</option>
                    <option value="7">7 dias desde hoy</option>
                    <option value="30">30 dias desde hoy</option>
                    <option value="90">90 dias desde hoy</option>
                    <option value="365">1 ano desde hoy</option>
                </select>
            </div>
            <div class="form-group">
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
                    <input type="checkbox" name="is_active" ${isActive ? 'checked' : ''}>
                    <span class="form-label" style="margin:0">Key activa</span>
                </label>
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center">Guardar</button>
        </form>
    `);
}

async function handleUpdateApiKey(e, keyId) {
    e.preventDefault();
    const f = e.target;
    const scopes = [];
    if (f.scope_read.checked) scopes.push('read');
    if (f.scope_write.checked) scopes.push('write');
    if (f.scope_delete.checked) scopes.push('delete');

    const data = {
        name: f.name.value || undefined,
        scopes: scopes.join(',') || 'read',
        is_active: f.is_active.checked,
    };
    if (f.expires_in_days.value) data.expires_in_days = parseInt(f.expires_in_days.value);

    try {
        const resp = await API.updateApiKey(keyId, data);
        if (resp.ok) { closeModal(); toast('API Key actualizada', 'success'); loadAdminApiKeys(); }
        else toast(resp.detail || 'Error', 'error');
    } catch { toast('Error de conexion', 'error'); }
}

async function revokeApiKey(keyId, name) {
    if (!confirm(`Revocar API key "${name}"? Las integraciones que la usen dejaran de funcionar.`)) return;
    try {
        const resp = await API.revokeApiKey(keyId);
        if (resp.ok) { toast('API Key revocada', 'success'); loadAdminApiKeys(); }
        else toast(resp.detail || 'Error', 'error');
    } catch { toast('Error de conexion', 'error'); }
}

// ── Render: Quotations (auth) ──────────────────────────────────
async function renderQuotations() {
    if (!state.user) { showLoginModal(); navigate('home'); return; }

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
    if (resp.ok) { closeModal(); toast(`Cotizacion creada: ${resp.extracted_lines} lineas`, 'success'); loadQuotations(); }
    else toast(resp.detail || 'Error al procesar archivo', 'error');
}

function showManualQuotationModal() {
    showModal('Cotizacion Manual', `
        <form id="manual-quot-form" onsubmit="handleManualQuotation(event)">
            <div class="form-group"><label class="form-label">Proveedor ID</label><input class="form-input" type="number" name="supplier_id" required></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Region</label><input class="form-input" name="region"></div>
                <div class="form-group"><label class="form-label">Moneda</label>
                    <select class="form-select" name="currency"><option value="BOB">BOB</option><option value="USD">USD</option></select>
                </div>
            </div>
            <div id="manual-lines"><h3 style="font-size:14px;margin-bottom:8px">Lineas</h3>
                <div style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:8px;margin-bottom:8px">
                    <input class="form-input" name="line_name_0" placeholder="Producto" required>
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
    div.style = 'display:grid;grid-template-columns:2fr 1fr 1fr;gap:8px;margin-bottom:8px';
    div.innerHTML = `
        <input class="form-input" name="line_name_${i}" placeholder="Producto" required>
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
    const resp = await API.createQuotation({
        supplier_id: parseInt(f.supplier_id.value),
        region: f.region.value || null,
        currency: f.currency.value,
        lines,
    });
    if (resp.ok) { closeModal(); toast('Cotizacion creada', 'success'); loadQuotations(); }
    else toast(resp.detail || 'Error', 'error');
}

// ── Render: RFQ (auth) ─────────────────────────────────────────
async function renderRFQ() {
    if (!state.user) { showLoginModal(); navigate('home'); return; }

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
                <thead><tr><th>Ref.</th><th>Titulo</th><th>Estado</th><th>Proveedores</th><th>Respuestas</th></tr></thead>
                <tbody>${resp.data.map(r => `
                    <tr>
                        <td><strong>${esc(r.reference)}</strong></td>
                        <td>${esc(r.title)}</td>
                        <td><span class="badge badge-${r.state === 'sent' ? 'success' : r.state === 'closed' ? 'gray' : 'primary'}">${esc(r.state)}</span></td>
                        <td>${r.supplier_count}</td>
                        <td>${r.response_count}</td>
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
                    <input class="form-input" type="number" step="0.01" name="item_qty_0" placeholder="Cant." value="1">
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
        <input class="form-input" type="number" step="0.01" name="item_qty_${i}" placeholder="Cant." value="1">
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

    const resp = await API.createRFQ({
        title: f.title.value,
        description: f.description.value || null,
        region: f.region.value || null,
        deadline: f.deadline.value || null,
        supplier_ids: f.supplier_ids.value.split(',').map(s => parseInt(s.trim())).filter(Boolean),
        channels, items,
    });
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
async function init() {
    // Restore session (optional — app works without it)
    state.token = localStorage.getItem('_mkt_token');
    state.refreshToken = localStorage.getItem('_mkt_refresh');
    try { state.user = JSON.parse(localStorage.getItem('_mkt_user')); } catch {}

    // Load catalog data (categories & UOMs) from API
    await loadCatalogData();

    // Hide loading screen
    const loading = document.getElementById('loading-screen');
    if (loading) loading.classList.add('hidden');

    // Register service worker
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
    }

    renderApp();
}

document.addEventListener('DOMContentLoaded', init);
