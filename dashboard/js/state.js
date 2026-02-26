/* ── Application State ─────────────────────────────────────────── */

const AppState = {
    apiKey: localStorage.getItem('teletraan_admin_key') || '',
    currentPage: 'overview',
    overviewData: null,
    distributors: [],
    selectedDistributor: null,

    setApiKey(key) {
        this.apiKey = key;
        localStorage.setItem('teletraan_admin_key', key);
    },

    logout() {
        this.apiKey = '';
        localStorage.removeItem('teletraan_admin_key');
        document.getElementById('auth-gate').hidden = false;
        document.getElementById('app-shell').hidden = true;
        document.getElementById('api-key-input').value = '';
    },

    isAuthenticated() {
        return !!this.apiKey;
    },
};
