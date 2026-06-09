/**
 * Authentication API Service
 * Handles all authentication-related API calls
 */
import api from './api'

export const authService = {
  /**
   * Register a new user
   * @param {string} email - User email
   * @param {string} password - User password
   * @returns {Promise<{user: Object, access_token: string}>}
   */
  async register(email, password) {
    try {
      const response = await api.post('/auth/register', {
        email,
        password
      })
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Registration failed'
    }
  },

  /**
   * Login user
   * @param {string} email - User email
   * @param {string} password - User password
   * @returns {Promise<{user: Object, access_token: string}>}
   */
  async login(email, password) {
    try {
      const response = await api.post('/auth/login', {
        email,
        password
      })
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Login failed'
    }
  },

  /**
   * Get current user information
   * @returns {Promise<Object>} User object
   */
  async getCurrentUser() {
    try {
      const response = await api.get('/auth/me')
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to fetch user'
    }
  },

  /**
   * Logout user (client-side only with JWT)
   * @returns {Promise<void>}
   */
  async logout() {
    try {
      await api.post('/auth/logout')
    } catch (error) {
      // Even if API call fails, we still logout client-side
      console.error('Logout API error:', error)
    }
  }
}
