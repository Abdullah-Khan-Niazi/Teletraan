/* ── Overview Page ─────────────────────────────────────────────── */

const OverviewPage = {
    async render(container) {
        UI.showLoading(container);

        try {
            const res = await API.dashboardOverview();
            const d = res.data;
            AppState.overviewData = d;

            // Cache distributors for use in selectors
            AppState.distributors = (d.distributors || []).map(dist => ({
                id: dist.id,
                business_name: dist.business_name,
                owner_name: dist.owner_name,
                city: dist.city,
                whatsapp_number: dist.whatsapp_number,
                subscription_status: dist.subscription_status,
                is_active: dist.is_active,
                onboarding_completed: dist.onboarding_completed,
                created_at: dist.created_at,
            }));

            const flags = d.feature_flags || {};

            container.innerHTML = `
                <div class="overview-header">
                    <h2>Command Center</h2>
                    <p>System overview and real-time metrics</p>
                </div>

                <!-- KPI Stats -->
                <div class="grid-stats mb-6">
                    <div class="stat-card">
                        <div class="stat-label">Distributors</div>
                        <div class="stat-value">${d.total_distributors}</div>
                        <div class="stat-sub">Active accounts</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Customers</div>
                        <div class="stat-value">${d.total_customers.toLocaleString()}</div>
                        <div class="stat-sub">Across all distributors</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Orders (24h)</div>
                        <div class="stat-value">${d.orders_today}</div>
                        <div class="stat-sub">${d.pending_orders} pending</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Revenue (24h)</div>
                        <div class="stat-value">${UI.formatPaisas(d.revenue_today_paisas)}</div>
                        <div class="stat-sub">Total collected</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Database</div>
                        <div class="stat-value">${UI.statusBadge(d.database === 'ok' ? 'active' : 'error')}</div>
                        <div class="stat-sub">${d.database}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Environment</div>
                        <div class="stat-value" style="font-size:var(--text-lg);letter-spacing:var(--tracking-wide)">${(d.environment || 'unknown').toUpperCase()}</div>
                        <div class="stat-sub">AI: ${d.ai_provider} / Pay: ${d.payment_gateway}</div>
                    </div>
                </div>

                <!-- Feature Flags -->
                <div class="card mb-6">
                    <div class="card-header">
                        <span class="card-title">Feature Flags</span>
                    </div>
                    <div class="card-body">
                        <div class="feature-flags">
                            ${Object.entries(flags).map(([k, v]) => `
                                <span class="flag-chip">
                                    <span class="flag-dot ${v ? 'on' : 'off'}"></span>
                                    ${k.replace(/_/g, ' ')}
                                </span>
                            `).join('')}
                        </div>
                    </div>
                </div>

                <!-- Recent Orders -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Recent Orders (24h)</span>
                        <button class="btn btn-sm btn-secondary" onclick="App.navigate('orders')">View All</button>
                    </div>
                    <div class="card-body" style="padding:0">
                        ${UI.buildTable([
                            { label: 'Order #',      key: 'order_number', mono: true },
                            { label: 'Distributor',   key: 'distributor_name', truncate: true },
                            { label: 'Status',        render: r => UI.statusBadge(r.status) },
                            { label: 'Payment',       render: r => UI.statusBadge(r.payment_status) },
                            { label: 'Total',         render: r => UI.formatPaisas(r.total_paisas), align: 'right' },
                            { label: 'Created',       render: r => UI.relativeTime(r.created_at) },
                        ], d.recent_orders || [], { emptyMsg: 'No orders in the last 24 hours.' })}
                    </div>
                </div>
            `;

        } catch (err) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>Failed to load overview: ${err.message}</p>
                    <button class="btn btn-secondary mt-4" onclick="OverviewPage.render(document.getElementById('page-container'))">Retry</button>
                </div>
            `;
        }
    },
};
