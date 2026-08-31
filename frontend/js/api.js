// ---------------------------------------------------------------------
// Central place for talking to the FastAPI backend + storing JWTs.
// ---------------------------------------------------------------------

const API_BASE_URL = "http://127.0.0.1:8000";

const Auth = {
  getAccessToken() { return localStorage.getItem("access_token"); },
  getRefreshToken() { return localStorage.getItem("refresh_token"); },
  setTokens(access, refresh) {
    localStorage.setItem("access_token", access);
    localStorage.setItem("refresh_token", refresh);
  },
  clear() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  },
  isLoggedIn() { return !!this.getAccessToken(); },
};

async function apiRequest(path, { method = "GET", body = null, auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const token = Auth.getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  });

  // Transparent refresh-on-401 (basic version)
  if (res.status === 401 && auth && Auth.getRefreshToken()) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      headers["Authorization"] = `Bearer ${Auth.getAccessToken()}`;
      res = await fetch(`${API_BASE_URL}${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : null,
      });
    }
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || "Something went wrong. Please try again.");
  }
  return data;
}

async function tryRefreshToken() {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: Auth.getRefreshToken() }),
    });
    if (!res.ok) { Auth.clear(); return false; }
    const data = await res.json();
    Auth.setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    Auth.clear();
    return false;
  }
}

// ---------------------------------------------------------------------
// Auth API calls
// ---------------------------------------------------------------------

const AuthAPI = {
  register(name, email, password) {
    return apiRequest("/auth/register", { method: "POST", body: { name, email, password } });
  },
  async login(email, password) {
    const data = await apiRequest("/auth/login", { method: "POST", body: { email, password } });
    Auth.setTokens(data.access_token, data.refresh_token);
    return data;
  },
  me() {
    return apiRequest("/auth/me", { auth: true });
  },
  async socialLogin(auth0AccessToken) {
    const data = await apiRequest("/auth/social-login", {
      method: "POST",
      body: { auth0_access_token: auth0AccessToken },
    });
    Auth.setTokens(data.access_token, data.refresh_token);
    return data;
  },
  logout() { Auth.clear(); },
};

const ProductsAPI = {
  list() { return apiRequest("/products/"); },
};

const CartAPI = {
  view() { return apiRequest("/cart/", { auth: true }); },
  add(productId, quantity = 1) {
    return apiRequest("/cart/add", { method: "POST", auth: true, body: { product_id: productId, quantity } });
  },
  update(cartItemId, quantity) {
    return apiRequest("/cart/update", { method: "PUT", auth: true, body: { cart_item_id: cartItemId, quantity } });
  },
  remove(cartItemId) {
    return apiRequest("/cart/remove", { method: "DELETE", auth: true, body: { cart_item_id: cartItemId } });
  },
};

const AdminAPI = {
  listUsers() { return apiRequest("/auth/users", { auth: true }); },
  listAllCarts() { return apiRequest("/cart/all", { auth: true }); },
};

const CheckoutAPI = {
  // Validates the cart, creates an Order + Payment, and returns a Stripe
  // Checkout URL to redirect the browser to.
  start() { return apiRequest("/checkout/", { method: "POST", auth: true }); },
};

const OrdersAPI = {
  mine() { return apiRequest("/orders/", { auth: true }); },
  get(orderId) { return apiRequest(`/orders/${orderId}`, { auth: true }); },
};

const NotificationsAPI = {
  list() { return apiRequest("/notifications/", { auth: true }); },
  markRead(notificationId = null) {
    return apiRequest("/notifications/read", {
      method: "POST",
      auth: true,
      body: { notification_id: notificationId },
    });
  },
};

// ---------------------------------------------------------------------
// Day 5: Customer Experience & Insights Module — Return/Refund requests
// ---------------------------------------------------------------------

const ReturnsAPI = {
  // Submits a return request for an order. `comment` may be null/empty.
  request(orderId, reason, comment) {
    return apiRequest(`/orders/${orderId}/return`, {
      method: "POST",
      auth: true,
      body: { reason, comment: comment || null },
    });
  },
  // Fetches the return request (if any) already submitted for an order.
  get(orderId) {
    return apiRequest(`/orders/${orderId}/return`, { auth: true });
  },
};

// ---------------------------------------------------------------------
// Real-time WebSocket connection (order_status_updated, cart_updated)
// ---------------------------------------------------------------------

const WS_BASE_URL = "ws://127.0.0.1:8000";

function connectNotificationSocket(onEvent) {
  if (!Auth.isLoggedIn()) return null;

  const token = Auth.getAccessToken();
  const ws = new WebSocket(`${WS_BASE_URL}/ws/notifications?token=${encodeURIComponent(token)}`);

  ws.onmessage = (msg) => {
    try {
      const parsed = JSON.parse(msg.data);
      onEvent(parsed.event, parsed.data);
    } catch {
      /* ignore malformed frames */
    }
  };

  return ws;
}

// ---------------------------------------------------------------------
// Shared navbar behaviour
// ---------------------------------------------------------------------

function renderNavAuthState() {
  const badge = document.getElementById("userBadge");
  if (!badge) return;
  if (Auth.isLoggedIn()) {
    AuthAPI.me()
      .then((user) => {
        badge.innerHTML = `${user.name} <span class="badge role-${user.role}">${user.role}</span> &nbsp;|&nbsp; <a href="#" id="logoutLink">Logout</a>`;
        document.getElementById("logoutLink").addEventListener("click", (e) => {
          e.preventDefault();
          AuthAPI.logout();
          window.location.href = "login.html";
        });
      })
      .catch(() => {
        Auth.clear();
        badge.innerHTML = `<a href="login.html">Login</a>`;
      });
  } else {
    badge.innerHTML = `<a href="login.html">Login</a>`;
  }
}

async function updateBellBadge() {
  const badge = document.getElementById("bellBadge");
  if (!badge || !Auth.isLoggedIn()) return;
  try {
    const notifications = await NotificationsAPI.list();
    const unread = notifications.filter(n => !n.read_status).length;
    if (unread > 0) {
      badge.textContent = unread > 9 ? "9+" : unread;
      badge.style.display = "flex";
    } else {
      badge.style.display = "none";
    }
  } catch {
    /* not logged in / request failed — leave badge hidden */
  }
}

document.addEventListener("DOMContentLoaded", () => {
  renderNavAuthState();
  updateBellBadge();
});
