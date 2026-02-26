/* ── Sessions Page ─────────────────────────────────────────────── */

const SessionsPage = {
    selectedDist: null,

    async render(container) {
        if (!this.selectedDist && AppState.distributors.length > 0) {
            this.selectedDist = AppState.distributors[0].id;
        }

        container.innerHTML = `
            <div class="section-header">
                <h2 class="section-title">Active Sessions</h2>
            </div>
            <div class="toolbar">
                ${UI.distributorSelect(this.selectedDist, (val) => {
                    this.selectedDist = val;
                    this.loadSessions();
                })}
                <button class="btn btn-secondary" id="btn-refresh-sessions">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
                    Refresh
                </button>
            </div>
            <div id="sessions-content"></div>
        `;

        document.getElementById('btn-refresh-sessions').addEventListener('click', () => {
            this.loadSessions();
        });

        if (this.selectedDist) {
            this.loadSessions();
        } else {
            document.getElementById('sessions-content').innerHTML = '<div class="empty-state"><p>Select a distributor to view sessions.</p></div>';
        }
    },

    async loadSessions() {
        const content = document.getElementById('sessions-content');
        if (!content || !this.selectedDist) return;
        UI.showLoading(content);

        try {
            const res = await API.listSessions(this.selectedDist);
            const sessions = res.data || [];

            const total = sessions.length;
            const handoff = sessions.filter(s => s.handoff_mode).length;
            const channelA = sessions.filter(s => s.channel === 'channel_a').length;
            const channelB = sessions.filter(s => s.channel === 'channel_b').length;

            content.innerHTML = `
                <div class="kpi-row">
                    <div class="kpi-item"><span class="kpi-label">Active</span><span class="kpi-value">${total}</span></div>
                    <div class="kpi-item"><span class="kpi-label">Handoff</span><span class="kpi-value">${handoff}</span></div>
                    <div class="kpi-item"><span class="kpi-label">Ch. A</span><span class="kpi-value">${channelA}</span></div>
                    <div class="kpi-item"><span class="kpi-label">Ch. B</span><span class="kpi-value">${channelB}</span></div>
                </div>
                ${UI.buildTable([
                    { label: 'Phone',        render: r => UI.maskPhone(r.whatsapp_number) },
                    { label: 'Customer',     key: 'customer_id', mono: true, truncate: true },
                    { label: 'Channel',      render: r => UI.statusBadge(r.channel || 'unknown') },
                    { label: 'State',        render: r => UI.statusBadge(r.current_state || 'idle') },
                    { label: 'Language',     key: 'language' },
                    { label: 'Handoff',      render: r => r.handoff_mode ? UI.statusBadge('handoff') : '—' },
                    { label: 'Last Message', render: r => UI.relativeTime(r.last_message_at) },
                    { label: 'Expires',      render: r => UI.formatDateTime(r.expires_at) },
                ], sessions, { emptyMsg: 'No active sessions.' })}
            `;
        } catch (err) {
            content.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
        }
    },
};
