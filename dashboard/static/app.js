/**
 * AI Outbound Agency - Frontend JavaScript Utilities
 */

/**
 * Retrieve JWT token from localStorage.
 */
function getToken() {
    return localStorage.getItem('access_token');
}

/**
 * Wrapper around fetch that adds Authorization: Bearer header.
 */
async function authFetch(url, options = {}) {
    const token = getToken();
    if (!options.headers) {
        options.headers = {};
    }
    if (token) {
        options.headers['Authorization'] = `Bearer ${token}`;
    }
    return fetch(url, options);
}

/**
 * Logout: clear localStorage and redirect to login page.
 */
function logout() {
    localStorage.removeItem('access_token');
    window.location.href = '/login';
}

/**
 * On DOMContentLoaded: check if token exists.
 * If not on login/register page and no token, redirect to /login.
 */
document.addEventListener('DOMContentLoaded', function () {
    const path = window.location.pathname;
    const publicPaths = ['/login', '/register'];

    if (!publicPaths.includes(path) && !getToken()) {
        window.location.href = '/login';
        return;
    }
});

/**
 * Configure HTMX to add auth header to all requests.
 */
document.addEventListener('htmx:configRequest', function (event) {
    const token = getToken();
    if (token) {
        event.detail.headers['Authorization'] = `Bearer ${token}`;
    }
});
