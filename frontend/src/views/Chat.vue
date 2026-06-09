<template>
  <v-container fluid class="fill-height pa-0">
    <v-row no-gutters class="fill-height">
      <!-- Chat Messages Area -->
      <v-col cols="12" class="d-flex flex-column" style="height: calc(100vh - 64px)">
        <v-card flat class="flex-grow-1 d-flex flex-column" style="height: 100%">
          <!-- Chat Header -->
          <v-card-title class="d-flex align-center bg-grey-lighten-4 py-3">
            <v-icon color="primary" class="mr-2">mdi-robot</v-icon>
            <div class="flex-grow-1">
              <div class="text-h6">Create New Scraper</div>
              <div class="text-caption text-grey">
                Describe what you want to scrape, and I'll help you create it
              </div>
            </div>
            <v-btn
              v-if="chatStore.currentSession"
              icon
              variant="text"
              size="small"
              @click="startNewChat"
              :disabled="chatStore.loading"
            >
              <v-icon>mdi-plus</v-icon>
            </v-btn>
          </v-card-title>

          <!-- Messages -->
          <v-card-text
            ref="messagesContainer"
            class="flex-grow-1 overflow-y-auto pa-4"
            style="max-height: calc(100vh - 240px)"
          >
            <!-- Welcome Message -->
            <div v-if="chatStore.messages.length === 0" class="text-center pa-8">
              <v-icon size="80" color="grey-lighten-2">mdi-chat-outline</v-icon>
              <h2 class="text-h5 mt-4 text-grey-darken-1">Welcome to Cradler!</h2>
              <p class="text-body-1 mt-2 text-grey">
                Tell me what website you'd like to scrape and what data you need.
              </p>
              <v-chip-group class="mt-6">
                <v-chip
                  v-for="(example, i) in examplePrompts"
                  :key="i"
                  variant="outlined"
                  @click="messageInput = example"
                  class="ma-1"
                >
                  {{ example }}
                </v-chip>
              </v-chip-group>
            </div>

            <!-- Message List -->
            <div v-for="(msg, index) in chatStore.messages" :key="index" class="mb-4">
              <!-- User Message -->
              <div v-if="msg.role === 'user'" class="d-flex justify-end mb-3">
                <v-card
                  color="primary"
                  dark
                  max-width="70%"
                  class="pa-3"
                  elevation="1"
                >
                  <div class="text-body-1">{{ msg.content }}</div>
                </v-card>
              </div>

              <!-- Assistant Message -->
              <div v-else class="d-flex justify-start mb-3">
                <v-avatar class="mr-3" color="secondary" size="40">
                  <v-icon>mdi-robot</v-icon>
                </v-avatar>
                <v-card max-width="70%" class="pa-3" elevation="1">
                  <div class="text-body-1" v-html="formatMessage(msg.content)"></div>
                </v-card>
              </div>
            </div>

            <!-- Loading Indicator -->
            <div v-if="chatStore.sending" class="d-flex justify-start mb-3">
              <v-avatar class="mr-3" color="secondary" size="40">
                <v-icon>mdi-robot</v-icon>
              </v-avatar>
              <v-card max-width="70%" class="pa-3" elevation="1">
                <v-progress-circular
                  indeterminate
                  size="20"
                  width="2"
                  color="primary"
                ></v-progress-circular>
                <span class="ml-2 text-grey">Thinking...</span>
              </v-card>
            </div>
          </v-card-text>

          <!-- Input Area -->
          <v-divider></v-divider>
          <v-card-actions class="pa-4">
            <v-textarea
              v-model="messageInput"
              placeholder="Describe what you want to scrape..."
              variant="outlined"
              rows="2"
              auto-grow
              hide-details
              :disabled="chatStore.sending"
              @keydown.enter.exact.prevent="handleSendMessage"
              @keydown.enter.shift.exact="messageInput += '\n'"
            >
              <template v-slot:append-inner>
                <v-btn
                  icon
                  color="primary"
                  :disabled="!messageInput.trim() || chatStore.sending"
                  @click="handleSendMessage"
                >
                  <v-icon>mdi-send</v-icon>
                </v-btn>
              </template>
            </v-textarea>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>

    <!-- Error Snackbar -->
    <v-snackbar v-model="showError" color="error" timeout="5000">
      {{ errorMessage }}
      <template v-slot:actions>
        <v-btn variant="text" @click="showError = false">Close</v-btn>
      </template>
    </v-snackbar>
  </v-container>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()

const messageInput = ref('')
const messagesContainer = ref(null)
const showError = ref(false)
const errorMessage = ref('')

const examplePrompts = [
  'Scrape product prices from Amazon',
  'Extract articles from TechCrunch',
  'Get reviews from Yelp',
  'Monitor stock prices'
]

/**
 * Initialize chat session
 */
onMounted(async () => {
  try {
    await chatStore.createChatSession()
  } catch (error) {
    console.error('Failed to create chat session:', error)
    errorMessage.value = 'Failed to initialize chat'
    showError.value = true
  }
})

/**
 * Send message
 */
async function handleSendMessage() {
  if (!messageInput.value.trim() || chatStore.sending) return

  const message = messageInput.value.trim()
  messageInput.value = ''

  try {
    await chatStore.sendMessage(message)
    scrollToBottom()
  } catch (error) {
    console.error('Failed to send message:', error)
    errorMessage.value = typeof error === 'string' ? error : 'Failed to send message'
    showError.value = true
  }
}

/**
 * Start a new chat session
 */
async function startNewChat() {
  try {
    await chatStore.createChatSession()
    messageInput.value = ''
  } catch (error) {
    console.error('Failed to start new chat:', error)
    errorMessage.value = 'Failed to start new chat'
    showError.value = true
  }
}

/**
 * Scroll to bottom of messages
 */
function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

/**
 * Format message content (basic markdown-like formatting)
 */
function formatMessage(content) {
  if (!content) return ''

  // Simple formatting: convert \n to <br>, **text** to <strong>
  return content
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

// Watch for new messages and scroll
watch(() => chatStore.messages.length, () => {
  scrollToBottom()
})
</script>

<style scoped>
.fill-height {
  height: 100%;
}

.overflow-y-auto {
  overflow-y: auto;
}
</style>
