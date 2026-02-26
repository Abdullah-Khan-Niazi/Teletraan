/* ── Shared UI Components ──────────────────────────────────────── */

const UI = {
    /* ── Toast Notifications ──────────────────────────────────── */
    toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.textContent = message;
        container.appendChild(el);
        setTimeout(() => {
            el.classList.add('removing');
            setTimeout(() => el.remove(), 200);
        }, 3500);
    },

    success(msg) { this.toast(msg, 'success'); },
    error(msg)   { this.toast(msg, 'error'); },

    /* ── Modal ────────────────────────────────────────────────── */
    openModal(title, bodyHtml, footerHtml) {
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-body').innerHTML = bodyHtml;
        document.getElementById('modal-footer').innerHTML = footerHtml || '';
        document.getElementById('modal-overlay').hidden = false;
    },

    closeModal() {
        document.getElementById('modal-overlay').hidden = true;
    },

    /* ── Confirm Dialog ───────────────────────────────────────── */
    confirm(title, message) {
        return new Promise(resolve => {
            const body = `<p class="text-sm">${message}</p>`;
            const footer = `
                <button class="btn btn-secondary" id="modal-cancel">Cancel</button>
                <button class="btn btn-primary" id="modal-confirm">Confirm</button>
            `;
            this.openModal(title, body, footer);
            document.getElementById('modal-cancel').onclick = () => {
                this.closeModal();
                resolve(false);
            };
            document.getElementById('modal-confirm').onclick = () => {
                this.closeModal();
                resolve(true);
            };
        });
    },

    /* ── Loading State ────────────────────────────────────────── */
    showLoading(container) {
        container.innerHTML = `
            <div class="page-loading">
                <div class="spinner spinner-lg"></div>
            </div>
        `;
    },

    /* ── Empty State ──────────────────────────────────────────── */
    showEmpty(container, message) {
        container.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="15" y1="9" x2="9" y2="15"/>
                    <line x1="9" y1="9" x2="15" y2="15"/>
                </svg>
                <p>${message}</p>
            </div>
        `;
    },

    /* ── Format Helpers ───────────────────────────────────────── */
    formatPaisas(paisas) {
        if (paisas == null) return 'PKR 0.00';
        const rupees = paisas / 100;
        return 'PKR ' + rupees.toLocaleString('en-PK', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    },

    formatDate(isoStr) {
        if (!isoStr) return '—';
        const d = new Date(isoStr);
        return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    },

    formatDateTime(isoStr) {
        if (!isoStr) return '—';
        const d = new Date(isoStr);
        return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
            + ' ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    },

    relativeTime(isoStr) {
        if (!isoStr) return '—';
        const diff = Date.now() - new Date(isoStr).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return `${mins}m ago`;
        const hrs = Math.floor(mins / 60);
        if (hrs < 24) return `${hrs}h ago`;
        const days = Math.floor(hrs / 24);
        return `${days}d ago`;
    },

    maskPhone(phone) {
        if (!phone) return '—';
        return '****' + phone.slice(-4);
    },

    /* ── Status Badge ─────────────────────────────────────────── */
    statusBadge(status) {
        const map = {
            'active':       'success',
            'completed':    'success',
            'confirmed':    'success',
            'paid':         'success',
            'delivered':    'success',
            'fulfilled':    'success',
            'verified':     'success',

            'pending':      'pending',
            'processing':   'pending',
            'awaiting_payment': 'pending',
            'initiated':    'pending',

            'suspended':    'warning',
            'expired':      'warning',
            'expiring':     'warning',
            'partial':      'warning',
            'on_hold':      'warning',

            'cancelled':    'error',
            'failed':       'error',
            'blocked':      'error',
            'rejected':     'error',
            'refunded':     'error',
            'inactive':     'error',

            'trial':        'info',
            'new':          'info',
            'idle':         'info',
            'draft':        'info',

            'true':         'success',
            'false':        'error',
        };
        const s = String(status || '').toLowerCase().replace(/ /g, '_');
        const variant = map[s] || 'neutral';
        return `<span class="badge badge-${variant}">${status}</span>`;
    },

    /* ── Build Table ──────────────────────────────────────────── */
    buildTable(columns, rows, options = {}) {
        if (!rows || rows.length === 0) {
            return `<div class="empty-state"><p>${options.emptyMsg || 'No data available.'}</p></div>`;
        }

        let html = '<div class="table-wrap"><table class="data-table"><thead><tr>';
        for (const col of columns) {
            html += `<th${col.align === 'right' ? ' class="cell-number"' : ''}>${col.label}</th>`;
        }
        html += '</tr></thead><tbody>';

        for (const row of rows) {
            const cls = options.onRowClick ? ' class="clickable"' : '';
            const dataAttr = options.rowDataAttr ? ` data-id="${row[options.rowDataAttr]}"` : '';
            html += `<tr${cls}${dataAttr}>`;
            for (const col of columns) {
                const val = col.render ? col.render(row) : (row[col.key] ?? '—');
                const cellCls = [];
                if (col.mono) cellCls.push('cell-mono');
                if (col.align === 'right') cellCls.push('cell-number');
                if (col.truncate) cellCls.push('cell-truncate');
                html += `<td${cellCls.length ? ` class="${cellCls.join(' ')}"` : ''}>${val}</td>`;
            }
            html += '</tr>';
        }

        html += '</tbody></table></div>';
        return html;
    },

    /* ── Distributor Selector ─────────────────────────────────── */
    distributorSelect(selectedId, onChange) {
        const id = 'dist-select-' + Math.random().toString(36).slice(2, 8);
        const dists = AppState.distributors || [];
        let html = `<select class="form-select" id="${id}">`;
        if (!selectedId) html += '<option value="">Select distributor...</option>';
        for (const d of dists) {
            const sel = String(d.id) === String(selectedId) ? ' selected' : '';
            html += `<option value="${d.id}"${sel}>${d.business_name} — ${d.city || ''}</option>`;
        }
        html += '</select>';

        // Defer event binding
        setTimeout(() => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', (e) => onChange(e.target.value));
        }, 0);

        return html;
    },
};
