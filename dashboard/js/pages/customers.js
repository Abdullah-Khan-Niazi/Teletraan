/* ── Customers Page ────────────────────────────────────────────── */

const CustomersPage = {
    selectedDist: null,

    async render(container) {
        if (!this.selectedDist && AppState.distributors.length > 0) {
            this.selectedDist = AppState.distributors[0].id;
        }

        container.innerHTML = `
            <div class="section-header">
                <h2 class="section-title">Customers</h2>
            </div>
            <div class="toolbar">
                ${UI.distributorSelect(this.selectedDist, (val) => {
                    this.selectedDist = val;
                    this.loadCustomers();
                })}
            </div>
            <div id="customers-content"></div>
        `;

        if (this.selectedDist) {
            this.loadCustomers();
        } else {
            document.getElementById('customers-content').innerHTML = '<div class="empty-state"><p>Select a distributor to view customers.</p></div>';
        }
    },

    async loadCustomers() {
        const content = document.getElementById('customers-content');
        if (!content || !this.selectedDist) return;
        UI.showLoading(content);

        try {
            const res = await API.listCustomers(this.selectedDist);
            const customers = res.data || [];

            const total = customers.length;
            const blocked = customers.filter(c => c.is_blocked).length;
            const totalSpend = customers.reduce((s, c) => s + (c.total_spend_paisas || 0), 0);

            content.innerHTML = `
                <div class="kpi-row">
                    <div class="kpi-item"><span class="kpi-label">Total</span><span class="kpi-value">${total}</span></div>
                    <div class="kpi-item"><span class="kpi-label">Blocked</span><span class="kpi-value">${blocked}</span></div>
                    <div class="kpi-item"><span class="kpi-label">Lifetime Spend</span><span class="kpi-value">${UI.formatPaisas(totalSpend)}</span></div>
                </div>
                ${UI.buildTable([
                    { label: 'Name',        key: 'name' },
                    { label: 'Shop',        key: 'shop_name', truncate: true },
                    { label: 'Phone',       render: r => UI.maskPhone(r.whatsapp_number) },
                    { label: 'City',        key: 'city' },
                    { label: 'Verified',    render: r => UI.statusBadge(String(r.is_verified)) },
                    { label: 'Status',      render: r => r.is_blocked ? UI.statusBadge('blocked') : UI.statusBadge('active') },
                    { label: 'Orders',      key: 'total_orders', align: 'right' },
                    { label: 'Spent',       render: r => UI.formatPaisas(r.total_spend_paisas), align: 'right' },
                    { label: 'Last Order',  render: r => UI.relativeTime(r.last_order_at) },
                    { label: 'Registered',  render: r => UI.formatDate(r.registered_at) },
                    { label: 'Actions',     render: r => r.is_blocked
                        ? `<button class="btn btn-sm btn-success" onclick="CustomersPage.unblock('${r.id}')">Unblock</button>`
                        : `<button class="btn btn-sm btn-danger" onclick="CustomersPage.block('${r.id}','${this.escapeHtml(r.name)}')">Block</button>`
                    },
                ], customers, { emptyMsg: 'No customers found for this distributor.' })}
            `;
        } catch (err) {
            content.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
        }
    },

    escapeHtml(str) {
        return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
    },

    async block(custId, name) {
        const ok = await UI.confirm('Block Customer', `Block ${name}? They will not be able to place orders.`);
        if (!ok) return;
        try {
            await API.blockCustomer(custId, this.selectedDist, 'Blocked by admin');
            UI.success('Customer blocked.');
            this.loadCustomers();
        } catch (err) { UI.error(err.message); }
    },

    async unblock(custId) {
        try {
            await API.unblockCustomer(custId, this.selectedDist);
            UI.success('Customer unblocked.');
            this.loadCustomers();
        } catch (err) { UI.error(err.message); }
    },
};
