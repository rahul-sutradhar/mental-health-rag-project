// Serenity Mindspace - Shared Utility Functions v2.0

// Dynamic API Base URL detection for decoupled hosting
const API_BASE = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost'
    ? window.location.origin
    : 'BACKEND_API_URL';

/* ==========================================
   TOKEN MANAGEMENT
   ========================================== */
function getTokens() { return parseInt(localStorage.getItem('tokens') || '0'); }
function setTokens(amount) {
    localStorage.setItem('tokens', Math.max(0, Math.round(amount)).toString());
    updateAllTokenDisplays();
}
function addTokens(amount) { setTokens(getTokens() + amount); }
function deductTokens(amount) {
    const c = getTokens();
    if (c < amount) return false;
    setTokens(c - amount);
    return true;
}
function updateAllTokenDisplays() {
    const tokens = getTokens();
    document.querySelectorAll('[data-token-display]').forEach(el => el.textContent = tokens);
    ['tokenCount', 'chatTokenCount', 'currentBalance'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = tokens;
    });
}

/* ==========================================
   MESSAGE COUNT (persisted across reloads)
   ========================================== */
function getMessageCount() { return parseInt(localStorage.getItem('aiMessageCount') || '0'); }
function incrementMessageCount() {
    const c = getMessageCount() + 1;
    localStorage.setItem('aiMessageCount', c.toString());
    return c;
}
function getFreeMessagesLeft() { return Math.max(0, 10 - getMessageCount()); }
function resetMessageCount() { localStorage.removeItem('aiMessageCount'); }

/* ==========================================
   AUTHENTICATION
   ========================================== */
function isLoggedIn() { return localStorage.getItem('isLoggedIn') === 'true' && !!localStorage.getItem('user_id'); }
function getUserType() { return localStorage.getItem('userType') || 'user'; }
function getUserName() { return localStorage.getItem('userName') || 'Friend'; }
function login(userType, userName) {
    localStorage.setItem('isLoggedIn', 'true');
    localStorage.setItem('userType', userType);
    if (userName) localStorage.setItem('userName', userName);
    if (!localStorage.getItem('tokens')) setTokens(100);
}
function logout() {
    fetch(API_BASE + '/api/logout').catch(err => console.error(err));
    localStorage.removeItem('isLoggedIn');
    localStorage.removeItem('userType');
    localStorage.removeItem('userName');
    localStorage.removeItem('user_id');
    localStorage.removeItem('tokens');
    showToast('Logged out successfully', 'success');
    setTimeout(() => { window.location.href = 'index.html'; }, 900);
}
function requireAuth() {
    if (!isLoggedIn()) {
        window.location.href = 'login.html?redirect=' + encodeURIComponent(window.location.pathname.split('/').pop());
        return false;
    }
    return true;
}
function requireSpecialist() {
    if (!isLoggedIn() || getUserType() !== 'specialist') {
        window.location.href = 'login.html';
        return false;
    }
    return true;
}
function requireAdmin() {
    if (!isLoggedIn() || (getUserType() !== 'admin' && getUserType() !== 'master_admin')) {
        window.location.href = 'login.html';
        return false;
    }
    return true;
}
async function syncSessionWithBackend() {
    try {
        const res = await fetch(API_BASE + '/api/session');
        const data = await res.json();
        if (data.logged_in) {
            localStorage.setItem('isLoggedIn', 'true');
            localStorage.setItem('userType', data.user_type);
            localStorage.setItem('userName', data.full_name || data.email.split('@')[0]);
            localStorage.setItem('user_id', data.user_id);
            localStorage.setItem('tokens', data.tokens.toString());
            updateAllTokenDisplays();
            updateNavAuthState();
        } else {
            if (localStorage.getItem('isLoggedIn') === 'true') {
                localStorage.removeItem('isLoggedIn');
                localStorage.removeItem('userType');
                localStorage.removeItem('userName');
                localStorage.removeItem('user_id');
                localStorage.removeItem('tokens');
                updateNavAuthState();
            }
        }
    } catch (e) {
        console.error('Session sync error:', e);
    }
}

/* ==========================================
   DATA STORAGE
   ========================================== */
function saveAssessment(data) { localStorage.setItem('assessmentData', JSON.stringify(data)); }
function getAssessment() {
    try { const d = localStorage.getItem('assessmentData'); return d ? JSON.parse(d) : null; }
    catch { return null; }
}
function saveBooking(booking) {
    const bookings = getBookings();
    booking.id = Date.now();
    booking.createdAt = new Date().toISOString();
    bookings.unshift(booking);
    localStorage.setItem('bookings', JSON.stringify(bookings));
    return booking;
}
function getBookings() {
    try { const d = localStorage.getItem('bookings'); return d ? JSON.parse(d) : []; }
    catch { return []; }
}
function getUpcomingBookings() {
    const now = new Date();
    return getBookings().filter(b => {
        const dt = b.dateTime || b.date;
        return dt && new Date(dt) > now;
    });
}
function saveChatHistory(sessionId, messages) { localStorage.setItem('chat_' + sessionId, JSON.stringify(messages)); }
function getChatHistory(sessionId) {
    try { const d = localStorage.getItem('chat_' + sessionId); return d ? JSON.parse(d) : []; }
    catch { return []; }
}

/* ==========================================
   VALIDATION
   ========================================== */
function validateEmail(email) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()); }
function validatePassword(password) { return password.length >= 8; }
function sanitizeInput(input) { const d = document.createElement('div'); d.textContent = input; return d.innerHTML; }
function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML.replace(/\n/g, '<br>');
}

/* ==========================================
   TOAST NOTIFICATIONS (replaces all alert())
   ========================================== */
function showToast(message, type, duration) {
    type = type || 'info';
    duration = duration || 3500;
    const colors = { success: '#7A9B76', error: '#D47C7C', info: '#7C9FD4', warning: '#E8A44A' };
    const icons = { success: '✓', error: '✕', info: 'ℹ', warning: '⚠' };
    const toast = document.createElement('div');
    toast.className = 'sm-toast sm-toast-' + type;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = '<span style="font-weight:700;margin-right:6px;">' + (icons[type] || 'ℹ') + '</span><span>' + message + '</span><button onclick="this.parentElement.remove()" style="background:none;border:none;color:white;cursor:pointer;margin-left:12px;font-size:1.1em;opacity:0.8;" aria-label="Close">✕</button>';
    const top = (20 + document.querySelectorAll('.sm-toast').length * 60) + 'px';
    toast.style.cssText = 'position:fixed;top:' + top + ';right:20px;padding:14px 20px;background:' + (colors[type] || colors.info) + ';color:white;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,0.18);z-index:100000;display:flex;align-items:center;max-width:380px;font-family:var(--font-display,sans-serif);font-size:0.95rem;animation:smToastIn 0.3s ease;';
    document.body.appendChild(toast);
    const t = setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateX(60px)'; toast.style.transition = 'all 0.3s ease'; setTimeout(() => toast.remove(), 300); }, duration);
    toast.addEventListener('mouseenter', () => clearTimeout(t));
    return toast;
}

/* ==========================================
   CONFIRM MODAL (replaces confirm())
   ========================================== */
function showConfirmModal(message, title, onConfirm, onCancel) {
    title = title || 'Confirm Action';
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.style.display = 'flex';
    overlay.innerHTML = '<div class="modal" style="max-width:420px;"><div class="modal-header"><div class="modal-icon">⚠️</div><h3 class="modal-title">' + title + '</h3></div><div class="modal-body"><p style="text-align:center;color:var(--text-secondary);">' + message + '</p></div><div class="modal-actions"><button class="btn btn-outline" id="smCancelBtn">Cancel</button><button class="btn btn-primary" id="smConfirmBtn">Confirm</button></div></div>';
    document.body.appendChild(overlay);
    overlay.querySelector('#smConfirmBtn').onclick = () => { overlay.remove(); if (onConfirm) onConfirm(); };
    overlay.querySelector('#smCancelBtn').onclick = () => { overlay.remove(); if (onCancel) onCancel(); };
    overlay.onclick = e => { if (e.target === overlay) { overlay.remove(); if (onCancel) onCancel(); } };
}

/* ==========================================
   LOADER
   ========================================== */
function showLoader(msg) {
    if (document.getElementById('globalLoader')) return;
    const l = document.createElement('div');
    l.id = 'globalLoader';
    l.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.45);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:99999;';
    l.innerHTML = '<div style="width:52px;height:52px;border:4px solid rgba(255,255,255,0.2);border-top-color:#7A9B76;border-radius:50%;animation:smSpin 0.9s linear infinite;"></div>' + (msg ? '<p style="color:white;margin-top:16px;font-family:var(--font-display,sans-serif);">' + msg + '</p>' : '');
    document.body.appendChild(l);
}
function hideLoader() { const l = document.getElementById('globalLoader'); if (l) l.remove(); }

/* ==========================================
   DARK MODE
   ========================================== */
function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    document.querySelectorAll('[data-dark-icon]').forEach(el => el.textContent = theme === 'dark' ? '☀️' : '🌙');
}
function toggleDarkMode() { applyTheme(localStorage.getItem('theme') === 'dark' ? 'light' : 'dark'); }
function initTheme() {
    const saved = localStorage.getItem('theme');
    const preferred = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    applyTheme(saved || preferred);
}

/* ==========================================
   MOBILE NAVIGATION
   ========================================== */
function initMobileMenu() {
    const toggle = document.getElementById('menuToggle');
    const menu = document.getElementById('navMenu');
    if (!toggle || !menu) return;
    toggle.addEventListener('click', () => {
        const open = menu.classList.toggle('active');
        toggle.classList.toggle('active', open);
        toggle.setAttribute('aria-expanded', open.toString());
    });
    document.addEventListener('click', e => {
        if (!toggle.contains(e.target) && !menu.contains(e.target)) {
            menu.classList.remove('active');
            toggle.classList.remove('active');
        }
    });
    menu.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
        menu.classList.remove('active');
        toggle.classList.remove('active');
    }));
}

/* ==========================================
   HEADER SMART SCROLL (hide down / show up)
   ========================================== */
function initHeaderScroll() {
    const h = document.getElementById('header') || document.querySelector('.site-header');
    if (!h) return;
    let lastY = 0;
    let ticking = false;

    window.addEventListener('scroll', () => {
        if (!ticking) {
            window.requestAnimationFrame(() => {
                const currentY = window.scrollY;
                const delta = currentY - lastY;

                // Add shadow when scrolled
                h.classList.toggle('scrolled', currentY > 50);

                // Hide on scroll down (> 80px from top), show on scroll up
                if (currentY > 80) {
                    if (delta > 4) {
                        h.classList.add('nav-hidden');
                    } else if (delta < -4) {
                        h.classList.remove('nav-hidden');
                    }
                } else {
                    h.classList.remove('nav-hidden');
                }

                lastY = currentY;
                ticking = false;
            });
            ticking = true;
        }
    }, { passive: true });
}

/* ==========================================
   REAL DEVICE DATE & TIME
   ========================================== */
function getRealNow() { return new Date(); }

function getRealDate() {
    return new Date().toLocaleDateString(undefined, {
        weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
    });
}
function getRealTime() {
    return new Date().toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function getRealDateTime() {
    return new Date().toLocaleString(undefined, {
        weekday: 'short', year: 'numeric', month: 'short',
        day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
}
function getRealShortDate() {
    return new Date().toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

// Live clock — updates every second on any element with [data-live-time]
function startLiveClock() {
    function tick() {
        const now = new Date();
        document.querySelectorAll('[data-live-time]').forEach(el => {
            const fmt = el.getAttribute('data-live-time') || 'time';
            if (fmt === 'time') el.textContent = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            else if (fmt === 'date') el.textContent = now.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
            else if (fmt === 'datetime') el.textContent = now.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
            else if (fmt === 'short') el.textContent = now.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        });
        // Also update any element with [data-session-start] for live session timers
    }
    tick();
    setInterval(tick, 1000);
}

/* ==========================================
   NAV AUTH STATE
   ========================================== */
function updateNavAuthState() {
    const show = (id, v) => { const el = document.getElementById(id); if (el) el.style.display = v ? '' : 'none'; };
    const logged = isLoggedIn();
    show('navLoginBtn', !logged);
    show('navSignupBtn', !logged);
    show('navDashBtn', logged);
    show('navLogoutBtn', logged);

    if (logged) {
        const dashBtn = document.getElementById('navDashBtn');
        if (dashBtn) {
            const role = getUserType();
            if (role === 'specialist') {
                dashBtn.href = 'specialist-console.html';
                dashBtn.textContent = 'Specialist Console';
            } else if (role === 'admin' || role === 'master_admin') {
                dashBtn.href = 'admin-dashboard.html';
                dashBtn.textContent = 'Admin Panel';
            } else {
                dashBtn.href = 'dashboard.html';
                dashBtn.textContent = 'Dashboard';
            }
        }
    }
}

/* ==========================================
   DATE & TIME
   ========================================== */
function formatDate(date) { return new Date(date).toLocaleDateString('en-IN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }); }
function formatTime(date) { return new Date(date).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }); }
function formatDateTime(date) { return formatDate(date) + ' at ' + formatTime(date); }
function getTimeAgo(date) {
    const s = Math.floor((new Date() - new Date(date)) / 1000);
    if (s < 60) return 'just now';
    if (s < 3600) return Math.floor(s / 60) + 'm ago';
    if (s < 86400) return Math.floor(s / 3600) + 'h ago';
    return Math.floor(s / 86400) + 'd ago';
}

/* ==========================================
   CRISIS DETECTION
   ========================================== */
const CRISIS_KEYWORDS = ['suicide', 'kill myself', 'end my life', 'want to die', "don't want to live", 'self harm', 'hurt myself', 'no reason to live', 'not worth living', 'better off dead'];
function detectCrisisKeywords(text) {
    const l = text.toLowerCase();
    return CRISIS_KEYWORDS.some(kw => l.includes(kw));
}
function showCrisisResources() {
    if (document.getElementById('crisisModal')) return;
    var m = document.createElement('div');
    m.className = 'modal-overlay';
    m.id = 'crisisModal';
    m.style.display = 'flex';

    var modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = [
        '<div class="modal-header">',
        '<div class="modal-icon" style="font-size:2.5rem;">🆘</div>',
        '<h3 class="modal-title" style="color:var(--color-error);">You Are Not Alone</h3>',
        '<p class="modal-subtitle">Immediate help is available right now — in India.</p>',
        '</div>',
        '<div class="modal-body">',
        '<div style="background:rgba(212,124,124,0.1);padding:var(--space-xl);border-radius:var(--radius-md);text-align:center;margin-bottom:var(--space-lg);border:2px solid rgba(212,124,124,0.3);">',
        '<h2 style="color:var(--color-error);margin-bottom:var(--space-sm);">',
        '<a href="tel:9152987821" style="color:inherit;text-decoration:none;">📞 9152987821</a>',
        '</h2>',
        '<p style="margin:0;font-weight:600;">iCall — TISS Suicide Prevention Helpline</p>',
        '<p style="font-size:var(--text-sm);color:var(--text-secondary);margin-top:var(--space-xs);">Mon–Sat 8am–10pm &bull; Free &amp; Confidential</p>',
        '</div>',
        '<div style="text-align:center;margin-bottom:var(--space-md);">',
        '<p style="font-size:var(--text-sm);color:var(--text-secondary);">',
        'Also: <a href="tel:18602662345" style="color:var(--color-primary)">Vandrevala: 1860-2662-345</a> (24&times;7)',
        ' | <a href="tel:9820466567" style="color:var(--color-primary)">AASRA: 9820466567</a> (24&times;7)',
        ' | Emergency: <strong>112</strong>',
        '</p>',
        '</div>',
        '<p style="text-align:center;color:var(--text-secondary);">',
        '&#x906;&#x92A; &#x905;&#x915;&#x947;&#x932;&#x947; &#x928;&#x939;&#x940;&#x902; &#x939;&#x948;&#x902;&#x964; &#x92E;&#x926;&#x926; &#x92E;&#x93E;&#x901;&#x917;&#x928;&#x93E; &#x938;&#x93E;&#x939;&#x938; &#x915;&#x940; &#x928;&#x93F;&#x936;&#x93E;&#x928;&#x940; &#x939;&#x948;&#x964;',
        '</p>',
        '</div>',
        '<div class="modal-actions">',
        '<a href="tel:9152987821" class="btn btn-primary btn-lg">📞 Call iCall Now</a>',
        '<button class="btn btn-outline" id="crisisSafeBtn">I\'m Safe, Continue</button>',
        '</div>'
    ].join('');

    m.appendChild(modal);
    document.body.appendChild(m);

    var safeBtn = document.getElementById('crisisSafeBtn');
    if (safeBtn) safeBtn.addEventListener('click', function () {
        var el = document.getElementById('crisisModal');
        if (el) el.remove();
    });
    m.addEventListener('click', function (e) {
        if (e.target === m) m.remove();
    });
}

/* ==========================================
   LUCKY VAULT
   ========================================== */
function canSpinVault() { return localStorage.getItem('lastVaultSpin') !== new Date().toDateString(); }
function spinLuckyVault() {
    if (!canSpinVault()) { showToast('Already spun today! Come back tomorrow.', 'info'); return null; }
    const won = Math.random() < 0.01;
    localStorage.setItem('lastVaultSpin', new Date().toDateString());
    if (won) { addTokens(50); showToast('🎉 You won 50 bonus tokens!', 'success', 5000); }
    else showToast('Better luck tomorrow!', 'info');
    return won;
}

/* ==========================================
   NOTIFICATIONS
   ========================================== */
function getNotifications() { try { return JSON.parse(localStorage.getItem('notifications') || '[]'); } catch { return []; } }
function addNotification(n) {
    const list = getNotifications();
    list.unshift({ ...n, id: Date.now(), read: false, timestamp: new Date().toISOString() });
    localStorage.setItem('notifications', JSON.stringify(list.slice(0, 50)));
}
function markNotificationRead(id) {
    const list = getNotifications();
    const n = list.find(x => x.id === id);
    if (n) { n.read = true; localStorage.setItem('notifications', JSON.stringify(list)); }
}

/* ==========================================
   EXPORT
   ========================================== */
function exportChatTranscript(messages, filename) {
    let text = '=== Serenity Mindspace - Chat Transcript ===\nDate: ' + new Date().toLocaleDateString() + '\n' + '─'.repeat(50) + '\n\n';
    messages.forEach(m => { text += '[' + formatTime(m.timestamp || new Date()) + '] ' + (m.sender || 'User') + ': ' + m.text + '\n\n'; });
    const blob = new Blob([text], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename || ('transcript-' + Date.now() + '.txt');
    a.click();
    URL.revokeObjectURL(a.href);
}

/* ==========================================
   INJECT CSS ANIMATIONS
   ========================================== */
(function () {
    if (document.getElementById('sm-utils-styles')) return;
    const s = document.createElement('style');
    s.id = 'sm-utils-styles';
    s.textContent = `
        @keyframes smToastIn { from{opacity:0;transform:translateX(60px)} to{opacity:1;transform:translateX(0)} }
        @keyframes smSpin    { to{transform:rotate(360deg)} }
        @media (max-width:768px) {
            .nav-menu { display:none !important; position:absolute; top:100%; left:0; right:0; background:var(--bg-elevated); padding:var(--space-md); flex-direction:column; box-shadow:var(--shadow-lg); border-top:1px solid var(--color-sand); z-index:1000; }
            .nav-menu.active { display:flex !important; }
            .menu-toggle { display:flex !important; }
        }
        .dark-mode-toggle { background:none; border:1.5px solid var(--color-stone); border-radius:var(--radius-full); padding:4px 10px; cursor:pointer; font-size:0.9rem; color:var(--text-secondary); transition:var(--transition-fast); }
        .dark-mode-toggle:hover { border-color:var(--color-primary); color:var(--color-primary); }
    `;
    document.head.appendChild(s);
})();

/* ==========================================
   ANALYTICS
   ========================================== */
function trackEvent(c, a, l) { console.debug('[Analytics]', { category: c, action: a, label: l }); }
function trackPageView(n) { trackEvent('Page View', n, window.location.pathname); }

/* ==========================================
   AUTO-INIT
   ========================================== */
document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initMobileMenu();
    initHeaderScroll();
    updateAllTokenDisplays();
    updateNavAuthState();
    syncSessionWithBackend();

    document.querySelectorAll('[data-action="toggle-dark"]').forEach(btn => btn.addEventListener('click', toggleDarkMode));
    document.querySelectorAll('[data-action="logout"]').forEach(btn => btn.addEventListener('click', function (e) { e.preventDefault(); logout(); }));

    // Auth guards
    const page = window.location.pathname.split('/').pop().replace('.html', '');
    const guarded = ['dashboard', 'booking', 'chat-room', 'video-call', 'ai-chat', 'choose-support'];
    const specialist = ['specialist-dashboard', 'specialist-console'];
    const admin = ['admin-dashboard'];
    if (guarded.includes(page)) requireAuth();
    if (specialist.includes(page)) requireSpecialist();
    if (admin.includes(page)) requireAdmin();

    if (page === 'login' && isLoggedIn()) {
        const role = getUserType();
        let rUrl = 'choose-support.html';
        if (role === 'specialist') rUrl = 'specialist-console.html';
        else if (role === 'admin' || role === 'master_admin') rUrl = 'admin-dashboard.html';
        window.location.href = rUrl;
    }

    startLiveClock();
    trackPageView(document.title);
});
