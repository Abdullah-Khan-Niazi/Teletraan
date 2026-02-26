/* ── TELETRAAN Dashboard — Application Controller ─────────────── */

const App = {
    pages: {
        overview:     OverviewPage,
        distributors: DistributorsPage,
        orders:       OrdersPage,
        customers:    CustomersPage,
        payments:     PaymentsPage,
        sessions:     SessionsPage,
        analytics:    AnalyticsPage,
        system:       SystemPage,
    },

    titles: {
        overview:     'Overview',
        distributors: 'Distributors',
        orders:       'Orders',
        customers:    'Customers',
        payments:     'Payments',
        sessions:     'Sessions',
        analytics:    'Analytics',
        system:       'System',
    },

    init() {
        this.bindAuth();
        this.bindNavigation();
        this.bindModal();
        this.bindSidebar();

        // Auto-login if key stored
        if (AppState.isAuthenticated()) {
            this.authenticate(AppState.apiKey);
        }
    },

    /* ── Authentication ───────────────────────────────────────── */
    bindAuth() {
        const form = document.getElementById('auth-form');
        const input = document.getElementById('api-key-input');
        const toggleBtn = document.getElementById('toggle-key-vis');
        const errorEl = document.getElementById('auth-error');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            errorEl.hidden = true;
            const key = input.value.trim();
            if (!key) return;

            try {
                await this.authenticate(key);
            } catch (err) {
                errorEl.textContent = err.message || 'Authentication failed.';
                errorEl.hidden = false;
            }
        });

        toggleBtn.addEventListener('click', () => {
            input.type = input.type === 'password' ? 'text' : 'password';
        });
    },

    async authenticate(key) {
        AppState.setApiKey(key);

        // Probe the API
        try {
            await API.probe();
        } catch (err) {
            AppState.logout();
            throw new Error('Invalid API key or server unreachable.');
        }

        // Show app
        document.getElementById('auth-gate').hidden = true;
        document.getElementById('app-shell').hidden = false;

        // Set env badge
        const overview = AppState.overviewData;
        if (overview && overview.environment) {
            document.getElementById('env-badge').textContent = overview.environment.toUpperCase();
        }

        // Navigate to overview
        this.navigate('overview');
    },

    /* ── Navigation ───────────────────────────────────────────── */
    bindNavigation() {
        document.querySelectorAll('.nav-item[data-page]').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                this.navigate(item.dataset.page);
            });
        });

        document.getElementById('btn-logout').addEventListener('click', () => {
            AppState.logout();
        });
    },

    navigate(pageName) {
        if (!this.pages[pageName]) return;
        AppState.currentPage = pageName;

        // Update nav active state
        document.querySelectorAll('.nav-item[data-page]').forEach(item => {
            item.classList.toggle('active', item.dataset.page === pageName);
        });

        // Update topbar title
        document.getElementById('page-title').textContent = this.titles[pageName] || pageName;

        // Render page
        const container = document.getElementById('page-container');
        this.pages[pageName].render(container);

        // Close sidebar on mobile
        document.getElementById('app-shell').classList.remove('sidebar-open');
    },

    /* ── Modal ─────────────────────────────────────────────────── */
    bindModal() {
        document.getElementById('modal-close').addEventListener('click', () => UI.closeModal());
        document.getElementById('modal-overlay').addEventListener('click', (e) => {
            if (e.target === document.getElementById('modal-overlay')) UI.closeModal();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') UI.closeModal();
        });
    },

    /* ── Sidebar ──────────────────────────────────────────────── */
    bindSidebar() {
        document.getElementById('btn-sidebar-toggle').addEventListener('click', () => {
            const shell = document.getElementById('app-shell');
            // On mobile: toggle open class; on desktop: toggle collapsed
            if (window.innerWidth <= 768) {
                shell.classList.toggle('sidebar-open');
            } else {
                shell.classList.toggle('sidebar-collapsed');
            }
        });
    },

    /* ── Connection Monitor ───────────────────────────────────── */
    startConnectionMonitor() {
        const dot = document.getElementById('connection-dot');
        setInterval(async () => {
            try {
                await API.probe();
                dot.classList.remove('offline');
                dot.title = 'Connected';
            } catch {
                dot.classList.add('offline');
                dot.title = 'Disconnected';
            }
        }, 30000);
    },
};

// ── Boot ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    App.init();
    App.startConnectionMonitor();
});
