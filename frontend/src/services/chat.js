/**
 * Chat API Service
 * Handles all chat/conversation API calls for scraper creation
 */
import api from './api'

export const chatService = {
  /**
   * Get all chat sessions for current user
   * @returns {Promise<Array>} List of chat sessions
   */
  async getChatSessions() {
    try {
      const response = await api.get('/chat/sessions')
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to fetch chat sessions'
    }
  },

  /**
   * Get a specific chat session
   * @param {string} sessionId - Chat session ID
   * @returns {Promise<Object>} Chat session with messages
   */
  async getChatSession(sessionId) {
    try {
      const response = await api.get(`/chat/sessions/${sessionId}`)
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to fetch chat session'
    }
  },

  /**
   * Create a new chat session
   * @returns {Promise<Object>} New chat session
   */
  async createChatSession() {
    try {
      const response = await api.post('/chat/sessions', {})
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to create chat session'
    }
  },

  /**
   * Send a message in a chat session
   * @param {string} sessionId - Chat session ID
   * @param {string} message - User message
   * @returns {Promise<Object>} AI response
   */
  async sendMessage(sessionId, message) {
    try {
      const response = await api.post(`/chat/sessions/${sessionId}/messages`, {
        content: message
      })
      return response
    } catch (error) {
      console.log("sendMessage: ", error)
      throw error.response?.data?.detail || 'Failed to send message'
    }
  },

  /**
   * Delete a chat session
   * @param {string} sessionId - Chat session ID
   * @returns {Promise<void>}
   */
  async deleteChatSession(sessionId) {
    try {
      await api.delete(`/chat/sessions/${sessionId}`)
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to delete chat session'
    }
  }
}
