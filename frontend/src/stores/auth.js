/**
 * Authentication Store (Pinia)
 * Manages authentication state and user data
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authService } from '@/services/auth'

export const useAuthStore = defineStore('auth', () => {
  // State
  const user = ref(null)
  const token = ref(localStorage.getItem('token') || null)
  const loading = ref(false)
  const error = ref(null)

  // Getters
  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  /**
   * Register a new user
   * @param {string} email - User email
   * @param {string} password - User password
   */
  async function register(email, password) {
    loading.value = true
    error.value = null

    try {
      const response = await authService.register(email, password)

      // Save token and user
      token.value = response.access_token
      user.value = response.user
      localStorage.setItem('token', response.access_token)
      localStorage.setItem('user', JSON.stringify(response.user))

      return response
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Login user
   * @param {string} email - User email
   * @param {string} password - User password
   */
  async function login(email, password) {
    loading.value = true
    error.value = null

    try {
      const response = await authService.login(email, password)

      // Save token and user
      token.value = response.access_token
      user.value = response.user
      localStorage.setItem('token', response.access_token)
      localStorage.setItem('user', JSON.stringify(response.user))

      return response
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Logout user
   */
  async function logout() {
    loading.value = true

    try {
      await authService.logout()
    } catch (err) {
      console.error('Logout error:', err)
    } finally {
      // Clear state regardless of API call result
      token.value = null
      user.value = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      loading.value = false
    }
  }

  /**
   * Initialize auth state from localStorage
   */
  async function initAuth() {
    const storedToken = localStorage.getItem('token')
    const storedUser = localStorage.getItem('user')

    if (storedToken && storedUser) {
      token.value = storedToken
      user.value = JSON.parse(storedUser)

      // Verify token is still valid by fetching current user
      try {
        const currentUser = await authService.getCurrentUser()
        user.value = currentUser
        localStorage.setItem('user', JSON.stringify(currentUser))
      } catch (err) {
        // Token is invalid, clear auth state
        console.error('Token validation failed:', err)
        await logout()
      }
    }
  }

  /**
   * Fetch current user data
   */
  async function fetchCurrentUser() {
    if (!token.value) return

    loading.value = true
    error.value = null

    try {
      const currentUser = await authService.getCurrentUser()
      user.value = currentUser
      localStorage.setItem('user', JSON.stringify(currentUser))
      return currentUser
    } catch (err) {
      error.value = err
      // If fetching user fails, logout
      await logout()
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Clear error
   */
  function clearError() {
    error.value = null
  }

  return {
    // State
    user,
    token,
    loading,
    error,

    // Getters
    isAuthenticated,
    isAdmin,

    // Actions
    register,
    login,
    logout,
    initAuth,
    fetchCurrentUser,
    clearError
  }
})
