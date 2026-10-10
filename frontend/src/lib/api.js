import axios from 'axios';
import Cookies from 'js-cookie';
import { API_URL } from './env';

// Create axios instance
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = Cookies.get('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // If error is 401 and we haven't retried yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = Cookies.get('refresh_token');
        if (refreshToken) {
          const response = await axios.post(`${API_URL}/auth/token/refresh/`, {
            refresh: refreshToken,
          });

          const { access } = response.data;
          Cookies.set('access_token', access);

          originalRequest.headers.Authorization = `Bearer ${access}`;
          return api(originalRequest);
        }
      } catch (refreshError) {
        // Refresh failed, logout user
        Cookies.remove('access_token');
        Cookies.remove('refresh_token');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default api;

// API Service functions
export const authAPI = {
  register: (data) => api.post('/auth/register/', data),
  login: (data) => api.post('/auth/login/', data),
  logout: (refreshToken) => api.post('/auth/logout/', { refresh_token: refreshToken }),
  verifyEmail: (token) => api.get(`/auth/verify-email/${token}/`),
  getProfile: () => api.get('/auth/profile/'),
  updateProfile: (data) => api.put('/auth/profile/', data),
  changePassword: (data) => api.post('/auth/change-password/', data),
};

export const addressesAPI = {
  list: () => api.get('/auth/addresses/'),
  get: (id) => api.get(`/auth/addresses/${id}/`),
  create: (data) => api.post('/auth/addresses/', data),
  update: (id, data) => api.put(`/auth/addresses/${id}/`, data),
  delete: (id) => api.delete(`/auth/addresses/${id}/`),
};

export const storesAPI = {
  list: (params) => api.get('/stores/', { params }),
  get: (slug) => api.get(`/stores/${slug}/`),
  create: (data) => api.post('/stores/seller/create/', data),
  getMyStore: () => api.get('/stores/seller/my-store/'),
  updateMyStore: (data) => api.put('/stores/seller/my-store/', data),
  getStats: () => api.get('/stores/seller/stats/'),
};

export const productsAPI = {
  list: (params) => api.get('/products/', { params }),
  get: (id) => api.get(`/products/${id}/`),
  getById: (id) => api.get(`/products/seller/${id}/`), // For seller to get their own product
  create: (data) => api.post('/products/seller/create/', data),
  update: (id, data) => api.put(`/products/seller/${id}/`, data),
  delete: (id) => api.delete(`/products/seller/${id}/`),
  featured: () => api.get('/products/featured/'),
  sellerList: () => api.get('/products/seller/list/'),
  search: (params) => api.get('/products/search/', { params }),
};

export const ordersAPI = {
  list: () => api.get('/orders/'),
  get: (id) => api.get(`/orders/${id}/`),
  checkout: (data) => api.post('/orders/checkout/', data),
  sellerList: () => api.get('/orders/seller/list/'),
  updateStatus: (orderId, data) => api.put(`/orders/seller/${orderId}/update-status/`, data),
};

export const cartAPI = {
  get: () => api.get('/orders/cart/'),
  add: (data) => api.post('/orders/cart/add/', data),
  update: (itemId, data) => api.put(`/orders/cart/items/${itemId}/`, data),
  remove: (itemId) => api.delete(`/orders/cart/items/${itemId}/remove/`),
  clear: () => api.delete('/orders/cart/clear/'),
};

// ==================== REVIEWS API ====================
export const reviewsAPI = {
  // Get all reviews for a product
  listByProduct: (productId) => api.get(`/products/${productId}/reviews/`),
  
  // Create a review
  create: (data) => api.post('/products/reviews/create/', data),
  
  // Get user's own reviews
  myReviews: () => api.get('/products/reviews/my-reviews/'),
  
  // Get, update or delete a specific review
  get: (reviewId) => api.get(`/products/reviews/${reviewId}/`),
  update: (reviewId, data) => api.put(`/products/reviews/${reviewId}/`, data),
  delete: (reviewId) => api.delete(`/products/reviews/${reviewId}/`),
  
  // Check if user has reviewed a product
  checkUserReview: (productId) => api.get(`/products/${productId}/check-review/`),
};

// ==================== WISHLIST API ====================
export const wishlistAPI = {
  // Get all wishlist items
  list: () => api.get('/products/wishlist/'),
  
  // Add product to wishlist
  add: (productId) => api.post('/products/wishlist/add/', { product_id: productId }),
  
  // Remove product from wishlist
  remove: (productId) => api.delete(`/products/wishlist/remove/${productId}/`),
  
  // Check if product is in wishlist
  check: (productId) => api.get(`/products/wishlist/check/${productId}/`),
  
  // Clear entire wishlist
  clear: () => api.delete('/products/wishlist/clear/'),
};

// ==================== PAYMENTS API ====================
export const paymentsAPI = {
  // List user's transactions
  transactions: () => api.get('/payments/transactions/'),
  
  // Simulate payment for an order
  simulatePayment: (data) => api.post('/payments/simulate/', data),
  
  // Process refund
  refund: (orderId) => api.post(`/payments/refund/${orderId}/`),
  
  // Get payment status
  getStatus: (orderId) => api.get(`/payments/status/${orderId}/`),
  
  // Seller commissions
  sellerCommissions: () => api.get('/payments/seller/commissions/'),
};
