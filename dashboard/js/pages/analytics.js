/* ── Analytics Page ────────────────────────────────────────────── */

const AnalyticsPage = {
    selectedDist: null,
    eventTypeFilter: null,

    async render(container) {
        if (!this.selectedDist && AppState.distributors.length > 0) {
            this.selectedDist = AppState.distributors[0].id;
        }

        container.innerHTML = `
            <div class="section-header">
                <h2 class="section-title">Analytics Events</h2>
            </div>
            <div class="toolbar">
                ${UI.distributorSelect(this.selectedDist, (val) => {
                    this.selectedDist = val;
                    this.loadEvents();
                })}
                <input class="form-input" id="evt-type-filter" placeholder="Filter by event type..." style="min-width:220px">
                <button class="btn btn-secondary" id="btn-filter-events">Filter</button>
            </div>
            <div id="analytics-content"></div>
        `;

        document.getElementById('btn-filter-events').addEventListener('click', () => {
            this.eventTypeFilter = document.getElementById('evt-type-filter').value || null;
            this.loadEvents();
        });

        document.getElementById('evt-type-filter').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                this.eventTypeFilter = e.target.value || null;
                this.loadEvents();
            }
        });

        if (this.selectedDist) {
            this.loadEvents();
        } else {
            document.getElementById('analytics-content').innerHTML = '<div class="empty-state"><p>Select a distributor to view analytics.</p></div>';
        }
    },

    async loadEvents() {
        const content = document.getElementById('analytics-content');
        if (!content || !this.selectedDist) return;
        UI.showLoading(content);

        try {
            const res = await API.listAnalytics(this.selectedDist, this.eventTypeFilter);
            const events = res.data || [];

            // Aggregate event types for summary
            const typeCounts = {};
            for (const e of events) {
                typeCounts[e.event_type] = (typeCounts[e.event_type] || 0) + 1;
            }

            const typesSorted = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);

            content.innerHTML = `
                <div class="kpi-row">
                    <div class="kpi-item"><span class="kpi-label">Total Events</span><span class="kpi-value">${events.length}</span></div>
                    <div class="kpi-item"><span class="kpi-label">Unique Types</span><span class="kpi-value">${typesSorted.length}</span></div>
                </div>

                <!-- Event type breakdown -->
                ${typesSorted.length > 0 ? `
                <div class="card mb-6">
                    <div class="card-header">
                        <span class="card-title">Event Type Breakdown</span>
                    </div>
                    <div class="card-body">
                        <div style="display:flex;flex-wrap:wrap;gap:var(--space-2)">
                            ${typesSorted.map(([type, count]) => `
                                <span class="badge badge-neutral" style="cursor:pointer" onclick="document.getElementById('evt-type-filter').value='${type}';AnalyticsPage.eventTypeFilter='${type}';AnalyticsPage.loadEvents()">
                                    ${type}: ${count}
                                </span>
                            `).join('')}
                        </div>
                    </div>
                </div>
                ` : ''}

                <!-- Event log table -->
                ${UI.buildTable([
                    { label: 'Event Type',  key: 'event_type', mono: true },
                    { label: 'Data',        render: r => {
                        const data = r.event_data;
                        if (!data || typeof data !== 'object') return String(data || '—');
                        const keys = Object.keys(data).slice(0, 4);
                        return keys.map(k => `<span class="text-mono text-muted">${k}:</span> ${String(data[k]).substring(0, 30)}`).join(', ');
                    }, truncate: true },
                    { label: 'Created', render: r => UI.formatDateTime(r.created_at) },
                    { label: '',        render: r => `<button class="btn btn-sm btn-ghost" onclick='AnalyticsPage.showEventDetail(${JSON.stringify(r).replace(/'/g, "&#39;")})'>View</button>` },
                ], events, { emptyMsg: 'No analytics events found.' })}
            `;
        } catch (err) {
            content.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
        }
    },

    showEventDetail(event) {
        const dataStr = JSON.stringify(event.event_data, null, 2);
        const body = `
            <div class="detail-grid mb-4">
                <span class="detail-label">Event ID</span>
                <span class="detail-value text-mono">${event.id}</span>
                <span class="detail-label">Type</span>
                <span class="detail-value">${event.event_type}</span>
                <span class="detail-label">Created</span>
                <span class="detail-value">${UI.formatDateTime(event.created_at)}</span>
            </div>
            <div class="divider"></div>
            <h4 style="font-size:var(--text-sm);font-weight:var(--weight-semibold);margin-bottom:var(--space-3)">Event Data</h4>
            <pre style="background:var(--gray-50);border:1px solid var(--border-light);border-radius:var(--radius-md);padding:var(--space-4);font-family:var(--font-mono);font-size:var(--text-xs);overflow:auto;max-height:300px;white-space:pre-wrap">${this.escapeHtml(dataStr)}</pre>
        `;
        UI.openModal('Event Detail', body);
    },

    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    },
};
