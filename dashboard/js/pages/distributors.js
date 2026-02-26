/* ── Distributors Page ─────────────────────────────────────────── */

const DistributorsPage = {
    selectedId: null,

    async render(container) {
        this.selectedId = null;
        UI.showLoading(container);

        try {
            const res = await API.listDistributors();
            const distributors = res.data || [];
            AppState.distributors = distributors;

            container.innerHTML = `
                <div class="section-header">
                    <h2 class="section-title">Distributors</h2>
                    <button class="btn btn-primary" id="btn-create-dist">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                        New Distributor
                    </button>
                </div>
                <div id="dist-list-content">
                    ${UI.buildTable([
                        { label: 'Business Name', key: 'business_name' },
                        { label: 'Owner',         key: 'owner_name' },
                        { label: 'City',           key: 'city' },
                        { label: 'Phone',          render: r => UI.maskPhone(r.whatsapp_number) },
                        { label: 'Status',         render: r => UI.statusBadge(r.subscription_status) },
                        { label: 'Active',         render: r => UI.statusBadge(String(r.is_active)) },
                        { label: 'Onboarded',      render: r => UI.statusBadge(String(r.onboarding_completed)) },
                        { label: 'Created',        render: r => UI.formatDate(r.created_at) },
                    ], distributors, {
                        onRowClick: true,
                        rowDataAttr: 'id',
                        emptyMsg: 'No distributors found.',
                    })}
                </div>
                <div id="dist-detail-panel"></div>
            `;

            // Row click → detail
            container.querySelectorAll('.data-table tbody tr.clickable').forEach(row => {
                row.addEventListener('click', () => {
                    const id = row.dataset.id;
                    if (id) this.showDetail(id, container);
                });
            });

            // Create button
            document.getElementById('btn-create-dist').addEventListener('click', () => {
                this.showCreateForm();
            });

        } catch (err) {
            UI.error('Failed to load distributors: ' + err.message);
        }
    },

    async showDetail(id, pageContainer) {
        this.selectedId = id;
        const panel = document.getElementById('dist-detail-panel') || pageContainer;

        try {
            const res = await API.getDistributor(id);
            const d = res.data;

            const listContent = document.getElementById('dist-list-content');
            if (listContent) listContent.classList.add('hidden');

            panel.innerHTML = `
                <div class="back-link" id="dist-back">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
                    Back to list
                </div>

                <div class="dist-detail-header">
                    <div>
                        <h3>${d.business_name || 'Unknown'}</h3>
                        <p class="text-sm text-muted">${d.owner_name || ''} — ${d.city || ''}</p>
                    </div>
                    <div class="dist-detail-actions">
                        ${d.is_active !== false ? `
                            <button class="btn btn-sm btn-danger" id="btn-suspend-dist">Suspend</button>
                        ` : `
                            <button class="btn btn-sm btn-success" id="btn-unsuspend-dist">Reactivate</button>
                        `}
                        <button class="btn btn-sm btn-secondary" id="btn-extend-dist">Extend</button>
                    </div>
                </div>

                <div class="card mb-6">
                    <div class="card-body">
                        <div class="detail-grid">
                            <span class="detail-label">ID</span>
                            <span class="detail-value text-mono">${d.id}</span>
                            <span class="detail-label">Phone</span>
                            <span class="detail-value">${UI.maskPhone(d.whatsapp_number)}</span>
                            <span class="detail-label">Status</span>
                            <span class="detail-value">${UI.statusBadge(d.subscription_status)}</span>
                            <span class="detail-label">Active</span>
                            <span class="detail-value">${UI.statusBadge(String(d.is_active))}</span>
                            <span class="detail-label">Onboarded</span>
                            <span class="detail-value">${UI.statusBadge(String(d.onboarding_completed))}</span>
                            <span class="detail-label">Channel</span>
                            <span class="detail-value">${d.channel || '—'}</span>
                            <span class="detail-label">AI Provider</span>
                            <span class="detail-value">${d.ai_provider_override || 'default'}</span>
                            <span class="detail-label">Gateway</span>
                            <span class="detail-value">${d.payment_gateway_override || 'default'}</span>
                            <span class="detail-label">Trial Ends</span>
                            <span class="detail-value">${UI.formatDate(d.trial_ends_at)}</span>
                            <span class="detail-label">Sub Ends</span>
                            <span class="detail-value">${UI.formatDate(d.subscription_ends_at)}</span>
                            <span class="detail-label">Created</span>
                            <span class="detail-value">${UI.formatDateTime(d.created_at)}</span>
                        </div>
                    </div>
                </div>

                <!-- Tabs -->
                <div class="dist-tabs" id="dist-tabs">
                    <div class="dist-tab active" data-tab="customers">Customers</div>
                    <div class="dist-tab" data-tab="orders">Orders</div>
                    <div class="dist-tab" data-tab="payments">Payments</div>
                    <div class="dist-tab" data-tab="sessions">Sessions</div>
                </div>
                <div id="dist-tab-content"></div>
            `;

            // Back
            document.getElementById('dist-back').addEventListener('click', () => {
                this.render(pageContainer);
            });

            // Suspend / Unsuspend
            const suspendBtn = document.getElementById('btn-suspend-dist');
            if (suspendBtn) {
                suspendBtn.addEventListener('click', async () => {
                    const ok = await UI.confirm('Suspend Distributor', `Suspend ${d.business_name}? They will not be able to process orders.`);
                    if (!ok) return;
                    try {
                        await API.suspendDistributor(id);
                        UI.success('Distributor suspended.');
                        this.showDetail(id, pageContainer);
                    } catch (err) { UI.error(err.message); }
                });
            }

            const unsuspendBtn = document.getElementById('btn-unsuspend-dist');
            if (unsuspendBtn) {
                unsuspendBtn.addEventListener('click', async () => {
                    try {
                        await API.unsuspendDistributor(id);
                        UI.success('Distributor reactivated.');
                        this.showDetail(id, pageContainer);
                    } catch (err) { UI.error(err.message); }
                });
            }

            // Extend
            document.getElementById('btn-extend-dist').addEventListener('click', () => {
                this.showExtendModal(id, d.business_name);
            });

            // Tab switching
            const tabs = document.getElementById('dist-tabs');
            tabs.addEventListener('click', (e) => {
                const tab = e.target.closest('.dist-tab');
                if (!tab) return;
                tabs.querySelectorAll('.dist-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                this.loadTab(tab.dataset.tab, id);
            });

            // Load first tab
            this.loadTab('customers', id);

        } catch (err) {
            UI.error('Failed to load distributor: ' + err.message);
        }
    },

    async loadTab(tabName, distId) {
        const content = document.getElementById('dist-tab-content');
        if (!content) return;
        UI.showLoading(content);

        try {
            switch (tabName) {
                case 'customers': {
                    const res = await API.listCustomers(distId);
                    const customers = res.data || [];
                    content.innerHTML = UI.buildTable([
                        { label: 'Name',           key: 'name' },
                        { label: 'Shop',           key: 'shop_name', truncate: true },
                        { label: 'Phone',          render: r => UI.maskPhone(r.whatsapp_number) },
                        { label: 'City',           key: 'city' },
                        { label: 'Verified',       render: r => UI.statusBadge(String(r.is_verified)) },
                        { label: 'Blocked',        render: r => r.is_blocked ? UI.statusBadge('blocked') : UI.statusBadge('active') },
                        { label: 'Orders',         key: 'total_orders', align: 'right' },
                        { label: 'Total Spend',    render: r => UI.formatPaisas(r.total_spend_paisas), align: 'right' },
                        { label: 'Last Order',     render: r => UI.relativeTime(r.last_order_at) },
                        { label: 'Actions',        render: r => r.is_blocked
                            ? `<button class="btn btn-sm btn-success" onclick="DistributorsPage.unblockCustomer('${r.id}','${distId}')">Unblock</button>`
                            : `<button class="btn btn-sm btn-danger" onclick="DistributorsPage.blockCustomer('${r.id}','${distId}','${r.name}')">Block</button>`
                        },
                    ], customers, { emptyMsg: 'No customers for this distributor.' });
                    break;
                }
                case 'orders': {
                    const res = await API.listOrders(distId);
                    const orders = res.data || [];
                    content.innerHTML = UI.buildTable([
                        { label: 'Order #',     key: 'order_number', mono: true },
                        { label: 'Status',      render: r => UI.statusBadge(r.status) },
                        { label: 'Payment',     render: r => UI.statusBadge(r.payment_status) },
                        { label: 'Source',      key: 'source' },
                        { label: 'Total',       render: r => UI.formatPaisas(r.total_paisas), align: 'right' },
                        { label: 'Created',     render: r => UI.formatDateTime(r.created_at) },
                        { label: '',            render: r => `<button class="btn btn-sm btn-ghost" onclick="DistributorsPage.showOrderDetail('${r.id}','${distId}')">View</button>` },
                    ], orders, { emptyMsg: 'No orders found.' });
                    break;
                }
                case 'payments': {
                    const res = await API.listPayments(distId);
                    const payments = res.data || [];
                    content.innerHTML = UI.buildTable([
                        { label: 'Reference',   key: 'transaction_reference', mono: true, truncate: true },
                        { label: 'Gateway',      key: 'gateway' },
                        { label: 'Amount',       render: r => UI.formatPaisas(r.amount_paisas), align: 'right' },
                        { label: 'Status',       render: r => UI.statusBadge(r.status) },
                        { label: 'Paid At',      render: r => UI.formatDateTime(r.paid_at) },
                        { label: 'Created',      render: r => UI.formatDateTime(r.created_at) },
                    ], payments, { emptyMsg: 'No payments found.' });
                    break;
                }
                case 'sessions': {
                    const res = await API.listSessions(distId);
                    const sessions = res.data || [];
                    content.innerHTML = UI.buildTable([
                        { label: 'Phone',        render: r => UI.maskPhone(r.whatsapp_number) },
                        { label: 'Channel',      key: 'channel' },
                        { label: 'State',        render: r => UI.statusBadge(r.current_state) },
                        { label: 'Language',     key: 'language' },
                        { label: 'Handoff',      render: r => r.handoff_mode ? UI.statusBadge('handoff') : '—' },
                        { label: 'Last Message', render: r => UI.relativeTime(r.last_message_at) },
                        { label: 'Expires',      render: r => UI.formatDateTime(r.expires_at) },
                    ], sessions, { emptyMsg: 'No active sessions.' });
                    break;
                }
            }
        } catch (err) {
            content.innerHTML = `<div class="empty-state"><p>Error loading: ${err.message}</p></div>`;
        }
    },

    async blockCustomer(custId, distId, name) {
        const ok = await UI.confirm('Block Customer', `Block ${name}? They will not be able to place orders.`);
        if (!ok) return;
        try {
            await API.blockCustomer(custId, distId, 'Blocked by admin');
            UI.success('Customer blocked.');
            this.loadTab('customers', distId);
        } catch (err) { UI.error(err.message); }
    },

    async unblockCustomer(custId, distId) {
        try {
            await API.unblockCustomer(custId, distId);
            UI.success('Customer unblocked.');
            this.loadTab('customers', distId);
        } catch (err) { UI.error(err.message); }
    },

    async showOrderDetail(orderId, distId) {
        try {
            const res = await API.getOrderDetail(orderId, distId);
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
                    <span class="detail-value">${order.source}</span>
                    <span class="detail-label">Address</span>
                    <span class="detail-value">${order.delivery_address || '—'}</span>
                    <span class="detail-label">Notes</span>
                    <span class="detail-value">${order.notes || '—'}</span>
                    <span class="detail-label">Created</span>
                    <span class="detail-value">${UI.formatDateTime(order.created_at)}</span>
                </div>
                <div class="divider"></div>
                <h4 style="font-size:var(--text-sm);font-weight:var(--weight-semibold);margin-bottom:var(--space-3)">Items</h4>
                ${UI.buildTable([
                    { label: 'Medicine',   key: 'medicine_name' },
                    { label: 'Qty',        key: 'quantity_ordered', align: 'right' },
                    { label: 'Unit',       key: 'unit' },
                    { label: 'Unit Price', render: r => UI.formatPaisas(r.price_per_unit_paisas), align: 'right' },
                    { label: 'Discount',   render: r => UI.formatPaisas(r.discount_paisas), align: 'right' },
                    { label: 'Line Total', render: r => UI.formatPaisas(r.line_total_paisas), align: 'right' },
                ], items)}
                <div class="divider"></div>
                <div class="order-summary-row"><span>Subtotal</span><span>${UI.formatPaisas(order.subtotal_paisas)}</span></div>
                <div class="order-summary-row"><span>Discount</span><span>-${UI.formatPaisas(order.discount_paisas)}</span></div>
                <div class="order-summary-row"><span>Delivery</span><span>${UI.formatPaisas(order.delivery_charges_paisas)}</span></div>
                <div class="order-summary-row total"><span>Total</span><span>${UI.formatPaisas(order.total_paisas)}</span></div>
            `;
            UI.openModal(`Order ${order.order_number}`, body);
        } catch (err) {
            UI.error('Failed to load order: ' + err.message);
        }
    },

    showCreateForm() {
        const body = `
            <form id="create-dist-form">
                <div class="form-group">
                    <label class="form-label">Business Name *</label>
                    <input class="form-input" name="business_name" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Owner Name *</label>
                    <input class="form-input" name="owner_name" required>
                </div>
                <div class="form-group">
                    <label class="form-label">WhatsApp Number * (E.164)</label>
                    <input class="form-input" name="whatsapp_number" placeholder="+92300..." required>
                </div>
                <div class="form-group">
                    <label class="form-label">City *</label>
                    <input class="form-input" name="city" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Address</label>
                    <input class="form-input" name="address">
                </div>
                <div class="form-group">
                    <label class="form-label">CNIC</label>
                    <input class="form-input" name="cnic" placeholder="XXXXX-XXXXXXX-X">
                </div>
                <div class="form-group">
                    <label class="form-label">NTN</label>
                    <input class="form-input" name="ntn">
                </div>
                <div class="form-group">
                    <label class="form-label">Channel</label>
                    <select class="form-select" name="channel">
                        <option value="channel_a">Channel A (Order Management)</option>
                        <option value="channel_b">Channel B (Sales Funnel)</option>
                    </select>
                </div>
            </form>
        `;
        const footer = `
            <button class="btn btn-secondary" onclick="UI.closeModal()">Cancel</button>
            <button class="btn btn-primary" id="btn-submit-create">Create Distributor</button>
        `;
        UI.openModal('New Distributor', body, footer);

        document.getElementById('btn-submit-create').addEventListener('click', async () => {
            const form = document.getElementById('create-dist-form');
            const fd = new FormData(form);
            const data = Object.fromEntries(fd.entries());

            if (!data.business_name || !data.owner_name || !data.whatsapp_number || !data.city) {
                UI.error('Please fill all required fields.');
                return;
            }

            try {
                await API.createDistributor(data);
                UI.closeModal();
                UI.success('Distributor created.');
                this.render(document.getElementById('page-container'));
            } catch (err) {
                UI.error(err.message);
            }
        });
    },

    showExtendModal(id, name) {
        const body = `
            <p class="text-sm mb-4">Extend subscription for <strong>${name}</strong></p>
            <div class="form-group">
                <label class="form-label">Days to Add</label>
                <input class="form-input" type="number" id="extend-days" value="30" min="1" max="365">
            </div>
            <div class="form-group">
                <label class="form-label">Reason</label>
                <input class="form-input" id="extend-reason" value="Manual extension by admin">
            </div>
        `;
        const footer = `
            <button class="btn btn-secondary" onclick="UI.closeModal()">Cancel</button>
            <button class="btn btn-primary" id="btn-submit-extend">Extend</button>
        `;
        UI.openModal('Extend Subscription', body, footer);

        document.getElementById('btn-submit-extend').addEventListener('click', async () => {
            const days = parseInt(document.getElementById('extend-days').value) || 30;
            const reason = document.getElementById('extend-reason').value || '';
            try {
                await API.extendSubscription(id, { days, reason });
                UI.closeModal();
                UI.success(`Subscription extended by ${days} days.`);
                this.showDetail(id, document.getElementById('page-container'));
            } catch (err) {
                UI.error(err.message);
            }
        });
    },
};
