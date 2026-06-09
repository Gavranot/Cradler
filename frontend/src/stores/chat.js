/**
 * Chat Store (Pinia)
 * Manages chat sessions and messages for scraper creation
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chatService } from '@/services/chat'

export const useChatStore = defineStore('chat', () => {
  // State
  const chatSessions = ref([])
  const currentSession = ref(null)
  const messages = ref([])
  const loading = ref(false)
  const sending = ref(false)
  const error = ref(null)

  /**
   * Fetch all chat sessions
   */
  async function fetchChatSessions() {
    loading.value = true
    error.value = null

    try {
      chatSessions.value = await chatService.getChatSessions()
      return chatSessions.value
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch a specific chat session
   * @param {string} sessionId - Chat session ID
   */
  async function fetchChatSession(sessionId) {
    loading.value = true
    error.value = null

    try {
      const session = await chatService.getChatSession(sessionId)
      currentSession.value = session
      messages.value = session.messages || []
      return session
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Create a new chat session
   */
  async function createChatSession() {
    loading.value = true
    error.value = null

    try {
      const session = await chatService.createChatSession()
      console.log('[CHAT_STORE] Created session:', session)
      console.log('[CHAT_STORE] Session messages:', session.messages)

      currentSession.value = session
      messages.value = session.messages || []
      chatSessions.value.unshift(session)

      console.log('[CHAT_STORE] Messages initialized, count:', messages.value.length)
      return session
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Send a message in the current session
   * @param {string} message - User message
   */
  async function sendMessage(message) {
    if (!currentSession.value) {
      throw new Error('No active chat session')
    }

    sending.value = true
    error.value = null

    // Optimistically add user message
    const userMessage = {
      role: 'user',
      content: message,
      timestamp: new Date().toISOString()
    }
    messages.value.push(userMessage)

    try {
      const response = await chatService.sendMessage(currentSession.value.id, message)

      console.log('[CHAT_STORE] Response received:', response)
      console.log('[CHAT_STORE] Session messages:', response.session?.messages)
      console.log('[CHAT_STORE] Current messages before update:', messages.value.length)

      // The backend returns the full session with updated messages
      // So we should update from the session instead of duplicating
      if (response.session && response.session.messages) {
        messages.value = response.session.messages
        currentSession.value = response.session
        console.log('[CHAT_STORE] Updated messages from session, count:', messages.value.length)
      } else {
        // Fallback: add just the AI message if session not returned
        const aiMessage = {
          role: 'assistant',
          content: response.message?.content || response.content,
          timestamp: response.message?.timestamp || new Date().toISOString()
        }
        messages.value.push(aiMessage)
        console.log('[CHAT_STORE] Added AI message via fallback')
      }

      return response
    } catch (err) {
      // Remove optimistic user message on error
      messages.value.pop()
      error.value = err
      throw err
    } finally {
      sending.value = false
    }
  }

  /**
   * Delete a chat session
   * @param {string} sessionId - Chat session ID
   */
  async function deleteChatSession(sessionId) {
    loading.value = true
    error.value = null

    try {
      await chatService.deleteChatSession(sessionId)

      // Remove from list
      chatSessions.value = chatSessions.value.filter(s => s.id !== sessionId)

      // Clear current if it's the deleted one
      if (currentSession.value?.id === sessionId) {
        currentSession.value = null
        messages.value = []
      }
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Clear current session
   */
  function clearCurrentSession() {
    currentSession.value = null
    messages.value = []
  }

  /**
   * Clear error
   */
  function clearError() {
    error.value = null
  }

  return {
    // State
    chatSessions,
    currentSession,
    messages,
    loading,
    sending,
    error,

    // Actions
    fetchChatSessions,
    fetchChatSession,
    createChatSession,
    sendMessage,
    deleteChatSession,
    clearCurrentSession,
    clearError
  }
})
