/* ── Orders Page ───────────────────────────────────────────────── */

const OrdersPage = {
    selectedDist: null,
    statusFilter: null,
    hoursFilter: 168,

    async render(container) {
        // Auto-select first distributor if available
        if (!this.selectedDist && AppState.distributors.length > 0) {
            this.selectedDist = AppState.distributors[0].id;
        }

        container.innerHTML = `
            <div class="section-header">
                <h2 class="section-title">Orders</h2>
            </div>
            <div class="toolbar">
                ${UI.distributorSelect(this.selectedDist, (val) => {
                    this.selectedDist = val;
                    this.loadOrders();
                })}
                <select class="form-select" id="order-status-filter">
                    <option value="">All Statuses</option>
                    <option value="pending">Pending</option>
                    <option value="confirmed">Confirmed</option>
                    <option value="processing">Processing</option>
                    <option value="completed">Completed</option>
                    <option value="cancelled">Cancelled</option>
                    <option value="delivered">Delivered</option>
                </select>
                <select class="form-select" id="order-hours-filter">
                    <option value="24">Last 24h</option>
                    <option value="72">Last 3 days</option>
                    <option value="168" selected>Last 7 days</option>
                    <option value="720">Last 30 days</option>
                </select>
            </div>
            <div id="orders-content"></div>
        `;

        document.getElementById('order-status-filter').addEventListener('change', (e) => {
            this.statusFilter = e.target.value || null;
            this.loadOrders();
        });

        document.getElementById('order-hours-filter').addEventListener('change', (e) => {
            this.hoursFilter = parseInt(e.target.value) || 168;
            this.loadOrders();
        });

        if (this.selectedDist) {
            this.loadOrders();
        } else {
            document.getElementById('orders-content').innerHTML = '<div class="empty-state"><p>Select a distributor to view orders.</p></div>';
        }
    },

    async loadOrders() {
        const content = document.getElementById('orders-content');
        if (!content || !this.selectedDist) return;
        UI.showLoading(content);

        try {
            const res = await API.listOrders(this.selectedDist, this.statusFilter, this.hoursFilter);
            const orders = res.data || [];

            // KPI row
            const total = orders.length;
            const pending = orders.filter(o => o.status === 'pending').length;
            const totalRevenue = orders.reduce((s, o) => s + (o.total_paisas || 0), 0);

            content.innerHTML = `
                <div class="kpi-row">
                    <div class="kpi-item"><span class="kpi-label">Total</span><span class="kpi-value">${total}</span></div>
                    <div class="kpi-item"><span class="kpi-label">Pending</span><span class="kpi-value">${pending}</span></div>
                    <div class="kpi-item"><span class="kpi-label">Revenue</span><span class="kpi-value">${UI.formatPaisas(totalRevenue)}</span></div>
                </div>
                ${UI.buildTable([
                    { label: 'Order #',    key: 'order_number', mono: true },
                    { label: 'Status',     render: r => UI.statusBadge(r.status) },
                    { label: 'Payment',    render: r => UI.statusBadge(r.payment_status) },
                    { label: 'Method',     key: 'payment_method' },
                    { label: 'Source',     key: 'source' },
                    { label: 'Subtotal',   render: r => UI.formatPaisas(r.subtotal_paisas), align: 'right' },
                    { label: 'Discount',   render: r => UI.formatPaisas(r.discount_paisas), align: 'right' },
                    { label: 'Total',      render: r => UI.formatPaisas(r.total_paisas), align: 'right' },
                    { label: 'Created',    render: r => UI.formatDateTime(r.created_at) },
                    { label: '',           render: r => `<button class="btn btn-sm btn-ghost" onclick="OrdersPage.viewDetail('${r.id}')">Detail</button>` },
                ], orders, { emptyMsg: 'No orders match your filters.' })}
            `;
        } catch (err) {
            content.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
        }
    },

    async viewDetail(orderId) {
        try {
            const res = await API.getOrderDetail(orderId, this.selectedDist);
            const { order, items } = res.data;

            const body = `
                <div class="detail-grid mb-4">
                    <span class="detail-label">Order #</span>
                    <span class="detail-value text-mono">${order.order_number}</span>
                    <span class="detail-label">Status</span>
                    <span class="detail-value">${UI.statusBadge(order.status)}</span>
                    <span class="detail-label">Payment</span>
                    <span class="detail-value">${UI.statusBadge(order.payment_status)}</span>
                    <span class="detail-label">Source</span>
                    <span class="detail-value">${order.source || '—'}</span>
                    <span class="detail-label">Address</span>
                    <span class="detail-value">${order.delivery_address || '—'}</span>
                    <span class="detail-label">Notes</span>
                    <span class="detail-value">${order.notes || '—'}</span>
                    <span class="detail-label">Internal</span>
                    <span class="detail-value">${order.internal_notes || '—'}</span>
                    <span class="detail-label">Created</span>
                    <span class="detail-value">${UI.formatDateTime(order.created_at)}</span>
                    <span class="detail-label">Updated</span>
                    <span class="detail-value">${UI.formatDateTime(order.updated_at)}</span>
                </div>
                <div class="divider"></div>
                <h4 style="font-size:var(--text-sm);font-weight:var(--weight-semibold);margin-bottom:var(--space-3)">Line Items</h4>
                ${UI.buildTable([
                    { label: 'Medicine', key: 'medicine_name' },
                    { label: 'Qty',      key: 'quantity_ordered', align: 'right' },
                    { label: 'Fulfilled', key: 'quantity_fulfilled', align: 'right' },
                    { label: 'Unit',     key: 'unit' },
                    { label: 'Price',    render: r => UI.formatPaisas(r.price_per_unit_paisas), align: 'right' },
                    { label: 'Disc.',    render: r => UI.formatPaisas(r.discount_paisas), align: 'right' },
                    { label: 'Line',     render: r => UI.formatPaisas(r.line_total_paisas), align: 'right' },
                    { label: 'OOS',      render: r => r.is_out_of_stock_order ? UI.statusBadge('true') : '—' },
                    { label: 'Unlisted', render: r => r.is_unlisted_item ? UI.statusBadge('true') : '—' },
                ], items)}
                <div class="divider"></div>
                <div class="order-summary-row"><span>Subtotal</span><span>${UI.formatPaisas(order.subtotal_paisas)}</span></div>
                <div class="order-summary-row"><span>Discount</span><span>-${UI.formatPaisas(order.discount_paisas)}</span></div>
                <div class="order-summary-row"><span>Delivery</span><span>${UI.formatPaisas(order.delivery_charges_paisas)}</span></div>
                <div class="order-summary-row total"><span>Total</span><span>${UI.formatPaisas(order.total_paisas)}</span></div>
            `;
            UI.openModal(`Order ${order.order_number}`, body);
        } catch (err) {
            UI.error('Failed to load order detail: ' + err.message);
        }
    },
};
