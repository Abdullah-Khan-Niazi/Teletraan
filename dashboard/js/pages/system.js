/* ── System Page ───────────────────────────────────────────────── */

const SystemPage = {
    async render(container) {
        UI.showLoading(container);

        try {
            // Fetch all health data in parallel
            const [statusRes, gwRes, aiRes] = await Promise.allSettled([
                API.systemStatus(),
                API.gatewayHealth(),
                API.aiHealth(),
            ]);

            const status = statusRes.status === 'fulfilled' ? statusRes.value.data : null;
            const gateway = gwRes.status === 'fulfilled' ? gwRes.value.data : null;
            const ai = aiRes.status === 'fulfilled' ? aiRes.value.data : null;

            container.innerHTML = `
                <div class="section-header">
                    <h2 class="section-title">System Status</h2>
                    <div class="flex gap-3">
                        <button class="btn btn-secondary" id="btn-force-sync">
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
                            Force Inventory Sync
                        </button>
                        <button class="btn btn-primary" id="btn-announce">
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                            Send Announcement
                        </button>
                    </div>
                </div>

                <!-- System Status -->
                ${status ? `
                <div class="card mb-6">
                    <div class="card-header">
                        <span class="card-title">System Overview</span>
                        ${UI.statusBadge(status.database === 'ok' ? 'active' : 'error')}
                    </div>
                    <div class="card-body">
                        <div class="detail-grid">
                            <span class="detail-label">Database</span>
                            <span class="detail-value">${status.database || '—'}</span>
                            <span class="detail-label">Environment</span>
                            <span class="detail-value">${status.environment || '—'}</span>
                            <span class="detail-label">AI Provider</span>
                            <span class="detail-value">${status.ai_provider || '—'}</span>
                            <span class="detail-label">Pay Gateway</span>
                            <span class="detail-value">${status.payment_gateway || '—'}</span>
                            <span class="detail-label">Distributors</span>
                            <span class="detail-value">${status.total_distributors ?? '—'}</span>
                            <span class="detail-label">Scheduler Jobs</span>
                            <span class="detail-value">${status.scheduler_jobs ?? '—'}</span>
                        </div>
                        ${status.feature_flags ? `
                        <div class="divider"></div>
                        <div class="feature-flags">
                            ${Object.entries(status.feature_flags).map(([k, v]) => `
                                <span class="flag-chip">
                                    <span class="flag-dot ${v ? 'on' : 'off'}"></span>
                                    ${k.replace(/_/g, ' ')}
                                </span>
                            `).join('')}
                        </div>
                        ` : ''}
                    </div>
                </div>
                ` : `
                <div class="card mb-6">
                    <div class="card-body"><p class="text-muted">System status unavailable.</p></div>
                </div>
                `}

                <!-- Health Cards -->
                <h3 style="font-size:var(--text-md);font-weight:var(--weight-semibold);margin-bottom:var(--space-4)">Health Checks</h3>
                <div class="health-grid mb-6">
                    <!-- Gateway -->
                    <div class="health-card">
                        <div class="health-card-header">
                            <span class="health-card-title">Payment Gateway</span>
                            <div class="health-indicator ${gateway ? 'ok' : 'error'}"></div>
                        </div>
                        ${gateway ? `
                        <div class="detail-grid">
                            <span class="detail-label">Active</span>
                            <span class="detail-value">${gateway.active_gateway || '—'}</span>
                            <span class="detail-label">Status</span>
                            <span class="detail-value">${UI.statusBadge(gateway.status || 'unknown')}</span>
                            ${gateway.supported_gateways ? `
                            <span class="detail-label">Supported</span>
                            <span class="detail-value">${Array.isArray(gateway.supported_gateways) ? gateway.supported_gateways.join(', ') : gateway.supported_gateways}</span>
                            ` : ''}
                        </div>
                        ` : `<p class="health-detail">Unable to check gateway health.</p>`}
                    </div>

                    <!-- AI -->
                    <div class="health-card">
                        <div class="health-card-header">
                            <span class="health-card-title">AI Provider</span>
                            <div class="health-indicator ${ai ? 'ok' : 'error'}"></div>
                        </div>
                        ${ai ? `
                        <div class="detail-grid">
                            <span class="detail-label">Active</span>
                            <span class="detail-value">${ai.active_provider || '—'}</span>
                            <span class="detail-label">Status</span>
                            <span class="detail-value">${UI.statusBadge(ai.status || 'unknown')}</span>
                            ${ai.supported_providers ? `
                            <span class="detail-label">Supported</span>
                            <span class="detail-value">${Array.isArray(ai.supported_providers) ? ai.supported_providers.join(', ') : ai.supported_providers}</span>
                            ` : ''}
                        </div>
                        ` : `<p class="health-detail">Unable to check AI health.</p>`}
                    </div>

                    <!-- Database -->
                    <div class="health-card">
                        <div class="health-card-header">
                            <span class="health-card-title">Database</span>
                            <div class="health-indicator ${status && status.database === 'ok' ? 'ok' : 'error'}"></div>
                        </div>
                        <div class="detail-grid">
                            <span class="detail-label">Provider</span>
                            <span class="detail-value">Supabase (PostgreSQL)</span>
                            <span class="detail-label">Status</span>
                            <span class="detail-value">${UI.statusBadge(status && status.database === 'ok' ? 'active' : 'error')}</span>
                        </div>
                    </div>
                </div>

                <!-- Announcement Form -->
                <div class="card" id="announce-card" hidden>
                    <div class="card-header">
                        <span class="card-title">Send Announcement</span>
                        <button class="btn-icon" onclick="document.getElementById('announce-card').hidden=true">
                            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                    </div>
                    <div class="card-body">
                        <div class="announce-form">
                            <div class="form-group">
                                <label class="form-label">Message *</label>
                                <textarea class="form-textarea" id="announce-msg" rows="4" placeholder="Type your announcement..."></textarea>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Priority</label>
                                <select class="form-select" id="announce-priority">
                                    <option value="normal">Normal</option>
                                    <option value="high">High</option>
                                    <option value="critical">Critical</option>
                                </select>
                            </div>
                            <button class="btn btn-primary" id="btn-send-announce">Send to All Distributors</button>
                        </div>
                    </div>
                </div>
            `;

            // Force Sync
            document.getElementById('btn-force-sync').addEventListener('click', async () => {
                const ok = await UI.confirm('Force Inventory Sync', 'This will trigger an immediate inventory sync for all distributors. Continue?');
                if (!ok) return;
                try {
                    const res = await API.forceSync();
                    UI.success(res.message || 'Inventory sync triggered.');
                } catch (err) { UI.error(err.message); }
            });

            // Announce toggle
            document.getElementById('btn-announce').addEventListener('click', () => {
                const card = document.getElementById('announce-card');
                card.hidden = !card.hidden;
                if (!card.hidden) card.scrollIntoView({ behavior: 'smooth' });
            });

            // Send announcement
            document.getElementById('btn-send-announce').addEventListener('click', async () => {
                const msg = document.getElementById('announce-msg').value.trim();
                const priority = document.getElementById('announce-priority').value;

                if (!msg) {
                    UI.error('Message cannot be empty.');
                    return;
                }

                try {
                    const res = await API.sendAnnouncement({ message: msg, priority });
                    UI.success(res.message || 'Announcement sent.');
                    document.getElementById('announce-msg').value = '';
                    document.getElementById('announce-card').hidden = true;
                } catch (err) {
                    UI.error(err.message);
                }
            });

        } catch (err) {
            container.innerHTML = `<div class="empty-state"><p>Failed to load system status: ${err.message}</p></div>`;
        }
    },
};
