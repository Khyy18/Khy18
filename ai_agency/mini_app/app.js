/**
 * AI Agency Telegram Mini App
 * Uses Telegram WebApp JS SDK for integration
 */

// Initialize Telegram WebApp
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
}

const API_BASE = '/api/miniapp';

// Get telegram user data
function getTelegramId() {
    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
        return tg.initDataUnsafe.user.id;
    }
    return null;
}

function getInitData() {
    if (tg && tg.initData) {
        return tg.initData;
    }
    return '';
}

// Navigation
function showPage(pageName) {
    document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

    document.getElementById('page-' + pageName).classList.remove('hidden');
    document.getElementById('nav-' + pageName).classList.add('active');

    // Load data for the page
    switch (pageName) {
        case 'catalog':
            loadServices();
            break;
        case 'history':
            loadOrders();
            break;
        case 'balance':
            loadBalance();
            break;
    }
}

// API calls
async function apiCall(endpoint, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        'X-Init-Data': getInitData(),
    };

    const response = await fetch(API_BASE + endpoint, {
        ...options,
        headers: { ...headers, ...options.headers },
    });

    if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
    }

    return response.json();
}

// Load services catalog
async function loadServices() {
    try {
        const services = await apiCall('/services');
        const container = document.getElementById('services-list');
        const select = document.getElementById('order-service');

        container.innerHTML = '';
        select.innerHTML = '';

        services.forEach(service => {
            // Catalog card
            const card = document.createElement('div');
            card.className = 'bg-white rounded-lg p-4 shadow-sm border';
            card.innerHTML = `
                <div class="flex justify-between items-center">
                    <div>
                        <h3 class="font-medium">${service.name}</h3>
                        <p class="text-sm text-gray-500">${service.description || ''}</p>
                    </div>
                    <span class="text-blue-600 font-bold">${service.price} &#8381;</span>
                </div>
            `;
            container.appendChild(card);

            // Select option
            const option = document.createElement('option');
            option.value = service.type;
            option.textContent = `${service.name} - ${service.price} \u20BD`;
            select.appendChild(option);
        });
    } catch (e) {
        console.error('Failed to load services:', e);
    }
}

// Load order history
async function loadOrders() {
    const telegramId = getTelegramId();
    if (!telegramId) {
        document.getElementById('orders-list').innerHTML = '<p class="text-gray-500">ID not available</p>';
        return;
    }

    try {
        const orders = await apiCall(`/orders/${telegramId}`);
        const container = document.getElementById('orders-list');

        if (orders.length === 0) {
            container.innerHTML = '<p class="text-gray-500">No orders yet</p>';
            return;
        }

        container.innerHTML = '';
        orders.forEach(order => {
            const statusColors = {
                'completed': 'text-green-600',
                'pending': 'text-yellow-600',
                'processing': 'text-blue-600',
                'failed': 'text-red-600',
            };
            const color = statusColors[order.status] || 'text-gray-600';

            const card = document.createElement('div');
            card.className = 'bg-white rounded-lg p-4 shadow-sm border';
            card.innerHTML = `
                <div class="flex justify-between items-center">
                    <div>
                        <span class="font-medium">#${order.id}</span>
                        <span class="text-sm text-gray-500 ml-2">${order.service_type}</span>
                    </div>
                    <span class="${color} text-sm font-medium">${order.status}</span>
                </div>
                <div class="flex justify-between mt-2 text-sm text-gray-500">
                    <span>${order.created_at ? order.created_at.slice(0, 10) : ''}</span>
                    <span>${order.price} &#8381;</span>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (e) {
        console.error('Failed to load orders:', e);
    }
}

// Load balance
async function loadBalance() {
    const telegramId = getTelegramId();
    if (!telegramId) {
        document.getElementById('balance-info').innerHTML = '<p class="text-gray-500">ID not available</p>';
        return;
    }

    try {
        const data = await apiCall(`/balance/${telegramId}`);
        const container = document.getElementById('balance-info');
        container.innerHTML = `
            <div class="text-center">
                <p class="text-3xl font-bold text-blue-600">${data.balance} &#8381;</p>
                <p class="text-sm text-gray-500 mt-2">Current balance</p>
            </div>
            <div class="mt-4 pt-4 border-t">
                <div class="flex justify-between text-sm">
                    <span class="text-gray-500">Total spent:</span>
                    <span class="font-medium">${data.total_spent} &#8381;</span>
                </div>
                <div class="flex justify-between text-sm mt-2">
                    <span class="text-gray-500">Orders:</span>
                    <span class="font-medium">${data.order_count}</span>
                </div>
            </div>
        `;
    } catch (e) {
        console.error('Failed to load balance:', e);
    }
}

// Create order
async function createOrder(serviceType, text) {
    const telegramId = getTelegramId();
    const data = {
        telegram_id: telegramId,
        service_type: serviceType,
        input_text: text,
    };

    return apiCall('/orders', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

// Form submission
document.getElementById('order-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const serviceType = document.getElementById('order-service').value;
    const text = document.getElementById('order-text').value;

    if (!serviceType || !text.trim()) {
        alert('Please fill all fields');
        return;
    }

    try {
        const result = await createOrder(serviceType, text);
        const resultDiv = document.getElementById('order-result');
        resultDiv.classList.remove('hidden');
        resultDiv.innerHTML = `
            <p class="text-green-700 font-medium">Order created!</p>
            <p class="text-sm text-gray-600 mt-1">Order #${result.order_id} - ${result.price} \u20BD</p>
        `;
        document.getElementById('order-text').value = '';
    } catch (e) {
        alert('Error creating order: ' + e.message);
    }
});

// Validate initData with backend
async function validateInitData() {
    const initData = getInitData();
    if (!initData) return false;

    try {
        const result = await apiCall('/validate-init-data', {
            method: 'POST',
            body: JSON.stringify({ init_data: initData }),
        });
        return result.valid;
    } catch (e) {
        return false;
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadServices();
    validateInitData();
});
