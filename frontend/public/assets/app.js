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
};

// ── Categories config ──────────────────────────────────────────
const CATEGORY_META = {
    ferreteria:  { label: 'Ferreteria',  icon: '&#128295;' },
    agregados:   { label: 'Agregados',   icon: '&#9968;' },
    acero:       { label: 'Acero',       icon: '&#128681;' },
    electrico:   { label: 'Electrico',   icon: '&#9889;' },
    sanitario:   { label: 'Sanitario',   icon: '&#128703;' },
    madera:      { label: 'Madera',      icon: '&#127795;' },
    cemento:     { label: 'Cemento',     icon: '&#127959;' },
    pintura:     { label: 'Pintura',     icon: '&#127912;' },
    ceramica:    { label: 'Ceramica',    icon: '&#129521;' },
    herramientas:{ label: 'Herramientas',icon: '&#128736;' },
};

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
        dashboard:  { title: 'Dashboard',    icon: 'bar-chart', render: renderDashboard },
    };

    const allPages = { ...publicPages, ...(state.user ? authPages : {}) };

    app.innerHTML = `
        ${renderTopbar(publicPages, authPages)}
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

// ── Render: Dashboard (auth) ───────────────────────────────────
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
function init() {
    // Restore session (optional — app works without it)
    state.token = localStorage.getItem('_mkt_token');
    state.refreshToken = localStorage.getItem('_mkt_refresh');
    try { state.user = JSON.parse(localStorage.getItem('_mkt_user')); } catch {}

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
