/* ── Payments Page ─────────────────────────────────────────────── */

const PaymentsPage = {
    selectedDist: null,
    statusFilter: null,

    async render(container) {
        if (!this.selectedDist && AppState.distributors.length > 0) {
            this.selectedDist = AppState.distributors[0].id;
        }

        container.innerHTML = `
            <div class="section-header">
                <h2 class="section-title">Payments</h2>
            </div>
            <div class="toolbar">
                ${UI.distributorSelect(this.selectedDist, (val) => {
                    this.selectedDist = val;
                    this.loadPayments();
                })}
                <select class="form-select" id="pay-status-filter">
                    <option value="">All Statuses</option>
                    <option value="initiated">Initiated</option>
                    <option value="pending">Pending</option>
                    <option value="paid">Paid</option>
                    <option value="failed">Failed</option>
                    <option value="refunded">Refunded</option>
                    <option value="expired">Expired</option>
                </select>
            </div>
            <div id="payments-content"></div>
        `;

        document.getElementById('pay-status-filter').addEventListener('change', (e) => {
            this.statusFilter = e.target.value || null;
            this.loadPayments();
        });

        if (this.selectedDist) {
            this.loadPayments();
        } else {
            document.getElementById('payments-content').innerHTML = '<div class="empty-state"><p>Select a distributor to view payments.</p></div>';
        }
    },

    async loadPayments() {
        const content = document.getElementById('payments-content');
        if (!content || !this.selectedDist) return;
        UI.showLoading(content);

        try {
            const res = await API.listPayments(this.selectedDist, this.statusFilter);
            const payments = res.data || [];

            const total = payments.length;
            const paidTotal = payments.filter(p => p.status === 'paid').reduce((s, p) => s + (p.amount_paisas || 0), 0);
            const pendingCount = payments.filter(p => ['initiated', 'pending'].includes(p.status)).length;
            const failedCount = payments.filter(p => p.status === 'failed').length;

            content.innerHTML = `
                <div class="kpi-row">
                    <div class="kpi-item"><span class="kpi-label">Total</span><span class="kpi-value">${total}</span></div>
                    <div class="kpi-item"><span class="kpi-label">Paid Volume</span><span class="kpi-value">${UI.formatPaisas(paidTotal)}</span></div>
                    <div class="kpi-item"><span class="kpi-label">Pending</span><span class="kpi-value">${pendingCount}</span></div>
                    <div class="kpi-item"><span class="kpi-label">Failed</span><span class="kpi-value">${failedCount}</span></div>
                </div>
                ${UI.buildTable([
                    { label: 'Reference',   key: 'transaction_reference', mono: true, truncate: true },
                    { label: 'Gateway',     key: 'gateway' },
                    { label: 'Amount',      render: r => UI.formatPaisas(r.amount_paisas), align: 'right' },
                    { label: 'Status',      render: r => UI.statusBadge(r.status) },
                    { label: 'Link',        render: r => r.payment_link ? `<a href="${r.payment_link}" target="_blank" class="text-sm" style="color:var(--status-info)">Open</a>` : '—' },
                    { label: 'Failure',     key: 'failure_reason', truncate: true },
                    { label: 'Paid At',     render: r => UI.formatDateTime(r.paid_at) },
                    { label: 'Created',     render: r => UI.formatDateTime(r.created_at) },
                ], payments, { emptyMsg: 'No payments match your filters.' })}
            `;
        } catch (err) {
            content.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
        }
    },
};
