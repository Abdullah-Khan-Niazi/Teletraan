/* ── API Client ────────────────────────────────────────────────── */

const API = (() => {
    const BASE = '/api/admin';

    function headers() {
        return {
            'Content-Type': 'application/json',
            'X-Admin-Key': AppState.apiKey || '',
        };
    }

    async function request(method, path, body) {
        const opts = { method, headers: headers() };
        if (body) opts.body = JSON.stringify(body);

        const url = path.startsWith('/') ? path : `${BASE}/${path}`;
        const res = await fetch(url, opts);

        if (res.status === 401 || res.status === 403) {
            AppState.logout();
            throw new Error('Authentication failed.');
        }

        const json = await res.json();
        if (!res.ok) {
            throw new Error(json.detail || json.message || `HTTP ${res.status}`);
        }
        return json;
    }

    return {
        get:    (path)       => request('GET',    `${BASE}/${path}`),
        post:   (path, body) => request('POST',   `${BASE}/${path}`, body),
        put:    (path, body) => request('PUT',    `${BASE}/${path}`, body),
        delete: (path)       => request('DELETE', `${BASE}/${path}`),

        // ── Specific endpoints ─────────────────────────────────
        // Auth probe
        probe:              () => request('GET', `${BASE}/status`),

        // Overview
        dashboardOverview:  () => request('GET', `${BASE}/dashboard/overview`),

        // Distributors
        listDistributors:   () => request('GET', `${BASE}/distributors`),
        getDistributor:     (id) => request('GET', `${BASE}/distributors/${id}`),
        createDistributor:  (data) => request('POST', `${BASE}/distributors`, data),
        suspendDistributor: (id) => request('POST', `${BASE}/distributors/${id}/suspend`),
        unsuspendDistributor: (id) => request('POST', `${BASE}/distributors/${id}/unsuspend`),
        extendSubscription: (id, data) => request('POST', `${BASE}/distributors/${id}/extend`, data),

        // Customers
        listCustomers:      (distId, limit, offset) => request('GET', `${BASE}/dashboard/distributors/${distId}/customers?limit=${limit || 100}&offset=${offset || 0}`),
        blockCustomer:      (custId, distId, reason) => request('POST', `${BASE}/dashboard/customers/${custId}/block?distributor_id=${distId}&reason=${encodeURIComponent(reason || 'Blocked by admin')}`),
        unblockCustomer:    (custId, distId) => request('POST', `${BASE}/dashboard/customers/${custId}/unblock?distributor_id=${distId}`),

        // Orders
        listOrders:         (distId, status, hours) => {
            let q = `${BASE}/dashboard/distributors/${distId}/orders?hours=${hours || 168}`;
            if (status) q += `&status_filter=${status}`;
            return request('GET', q);
        },
        getOrderDetail:     (orderId, distId) => request('GET', `${BASE}/dashboard/orders/${orderId}/detail?distributor_id=${distId}`),

        // Payments
        listPayments:       (distId, status) => {
            let q = `${BASE}/dashboard/distributors/${distId}/payments`;
            if (status) q += `?status_filter=${status}`;
            return request('GET', q);
        },

        // Sessions
        listSessions:       (distId) => request('GET', `${BASE}/dashboard/distributors/${distId}/sessions`),

        // Analytics
        listAnalytics:      (distId, evtType) => {
            let q = `${BASE}/dashboard/distributors/${distId}/analytics`;
            if (evtType) q += `?event_type=${evtType}`;
            return request('GET', q);
        },

        // System
        systemStatus:       () => request('GET', `${BASE}/status`),
        gatewayHealth:      () => request('GET', `${BASE}/health/gateway`),
        aiHealth:           () => request('GET', `${BASE}/health/ai`),
        forceSync:          () => request('POST', `${BASE}/inventory/sync`),
        sendAnnouncement:   (data) => request('POST', `${BASE}/announce`, data),
    };
})();
