<template>
  <v-container fluid>
    <v-row v-if="scraperStore.loading" class="py-12">
      <v-col cols="12" class="text-center">
        <v-progress-circular indeterminate size="64" color="primary"></v-progress-circular>
      </v-col>
    </v-row>

    <template v-else-if="scraperStore.currentScraper">
      <v-row>
        <v-col>
          <div class="d-flex align-center mb-4">
            <v-btn icon :to="{ name: 'scrapers' }" class="mr-4">
              <v-icon>mdi-arrow-left</v-icon>
            </v-btn>
            <div>
              <h1 class="text-h4">{{ scraperStore.currentScraper.name }}</h1>
              <p class="text-grey">{{ scraperStore.currentScraper.target_url }}</p>
            </div>
            <v-spacer></v-spacer>

            <!-- Generate Code Button -->
            <v-btn
              v-if="scraperStore.currentScraper.status !== 'active'"
              color="primary"
              class="mr-2"
              @click="handleGenerateCode"
              :loading="generating"
              :disabled="generating"
            >
              <v-icon start>mdi-robot</v-icon>
              {{ generating ? 'Generating...' : 'Generate Code' }}
            </v-btn>

            <!-- Run Now Button -->
            <v-btn
              color="success"
              @click="handleRunScraper"
              :disabled="scraperStore.currentScraper.status !== 'active'"
            >
              <v-icon start>mdi-play</v-icon>
              Run Now
            </v-btn>
          </div>

          <!-- Status Badge -->
          <v-chip
            v-if="generating"
            color="info"
            class="mb-4"
            prepend-icon="mdi-loading mdi-spin"
          >
            {{ generationStatus }}
          </v-chip>
        </v-col>
      </v-row>

      <v-row>
        <!-- Main Content -->
        <v-col cols="12" md="8">
          <v-card>
            <v-tabs v-model="activeTab" bg-color="primary">
              <v-tab value="config">
                <v-icon start>mdi-cog</v-icon>
                Configuration
              </v-tab>
              <v-tab value="code">
                <v-icon start>mdi-code-braces</v-icon>
                Generated Code
              </v-tab>
              <v-tab value="reasoning">
                <v-icon start>mdi-brain</v-icon>
                Reasoning Log
              </v-tab>
            </v-tabs>

            <v-window v-model="activeTab">
              <!-- Configuration Tab -->
              <v-window-item value="config">
                <v-card-text>
                  <v-list>
                    <v-list-item>
                      <v-list-item-title>Status</v-list-item-title>
                      <v-list-item-subtitle>
                        <v-chip :color="getStatusColor(scraperStore.currentScraper.status)" size="small">
                          {{ scraperStore.currentScraper.status }}
                        </v-chip>
                      </v-list-item-subtitle>
                    </v-list-item>
                    <v-list-item>
                      <v-list-item-title>Target URL</v-list-item-title>
                      <v-list-item-subtitle>{{ scraperStore.currentScraper.target_url }}</v-list-item-subtitle>
                    </v-list-item>
                    <v-list-item v-if="scraperStore.currentScraper.scraping_config?.data_fields">
                      <v-list-item-title>Data Fields</v-list-item-title>
                      <v-list-item-subtitle>
                        {{ scraperStore.currentScraper.scraping_config.data_fields.join(', ') }}
                      </v-list-item-subtitle>
                    </v-list-item>
                    <v-list-item v-if="scraperStore.currentScraper.scraping_config?.iterations">
                      <v-list-item-title>Generation Iterations</v-list-item-title>
                      <v-list-item-subtitle>{{ scraperStore.currentScraper.scraping_config.iterations }}</v-list-item-subtitle>
                    </v-list-item>
                  </v-list>
                </v-card-text>
              </v-window-item>

              <!-- Generated Code Tab -->
              <v-window-item value="code">
                <v-card-text>
                  <CodeViewer :code="generatedCode" />
                </v-card-text>
              </v-window-item>

              <!-- Reasoning Log Tab -->
              <v-window-item value="reasoning">
                <v-card-text>
                  <ReasoningLogViewer :reasoning-log="reasoningLog" />
                </v-card-text>
              </v-window-item>
            </v-window>
          </v-card>

          <!-- Recent Runs -->
          <v-card class="mt-4">
            <v-card-title>Recent Runs</v-card-title>
            <v-card-text>
              <v-list v-if="scraperStore.scraperRuns.length > 0">
                <v-list-item v-for="run in scraperStore.scraperRuns" :key="run.id">
                  <template v-slot:prepend>
                    <v-icon :color="getRunStatusColor(run.status)">mdi-circle</v-icon>
                  </template>
                  <v-list-item-title>{{ run.status }}</v-list-item-title>
                  <v-list-item-subtitle>{{ formatDate(run.started_at) }} - {{ run.records_scraped }} records</v-list-item-subtitle>
                </v-list-item>
              </v-list>
              <p v-else class="text-grey text-center py-4">No runs yet</p>
            </v-card-text>
          </v-card>
        </v-col>

        <!-- Sidebar -->
        <v-col cols="12" md="4">
          <v-card>
            <v-card-title>Actions</v-card-title>
            <v-card-text>
              <v-btn
                block
                class="mb-2"
                color="primary"
                @click="handleGenerateCode"
                :loading="generating"
                :disabled="generating"
                v-if="scraperStore.currentScraper.status !== 'active'"
              >
                <v-icon start>mdi-robot</v-icon>
                Generate Code
              </v-btn>
              <v-btn
                block
                class="mb-2"
                @click="handleRunScraper"
                :disabled="scraperStore.currentScraper.status !== 'active'"
              >
                <v-icon start>mdi-play</v-icon>
                Run Scraper
              </v-btn>
              <v-btn block color="error" variant="outlined" @click="handleDeleteScraper">
                <v-icon start>mdi-delete</v-icon>
                Delete
              </v-btn>
            </v-card-text>
          </v-card>

          <!-- Generation Info Card -->
          <v-card v-if="scraperStore.currentScraper.status === 'active'" class="mt-4">
            <v-card-title>Generation Info</v-card-title>
            <v-card-text>
              <div class="text-body-2 mb-2">
                <v-icon size="small" start color="success">mdi-check-circle</v-icon>
                Code generated successfully
              </div>
              <div v-if="scraperStore.currentScraper.scraping_config?.iterations" class="text-caption text-grey">
                Completed in {{ scraperStore.currentScraper.scraping_config.iterations }} iterations
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </template>

    <!-- Error Snackbar -->
    <v-snackbar v-model="errorSnackbar" color="error" :timeout="5000">
      {{ errorMessage }}
    </v-snackbar>

    <!-- Success Snackbar -->
    <v-snackbar v-model="successSnackbar" color="success" :timeout="3000">
      {{ successMessage }}
    </v-snackbar>
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useScraperStore } from '@/stores/scraper'
import { scraperService } from '@/services/scraper'
import CodeViewer from '@/components/CodeViewer.vue'
import ReasoningLogViewer from '@/components/ReasoningLogViewer.vue'

const route = useRoute()
const router = useRouter()
const scraperStore = useScraperStore()

const activeTab = ref('config')
const generating = ref(false)
const generationStatus = ref('Initializing...')
const errorSnackbar = ref(false)
const errorMessage = ref('')
const successSnackbar = ref(false)
const successMessage = ref('')

let pollingInterval = null

const generatedCode = computed(() => {
  return scraperStore.currentScraper?.scraping_config?.generated_code || null
})

const reasoningLog = computed(() => {
  return scraperStore.currentScraper?.scraping_config?.reasoning_log || []
})

onMounted(async () => {
  try {
    await scraperStore.fetchScraper(route.params.id)
    await scraperStore.fetchScraperRuns(route.params.id)

    // If scraper is currently generating, start polling
    if (scraperStore.currentScraper?.status === 'generating') {
      startPolling()
    }
  } catch (error) {
    console.error('Failed to load scraper:', error)
    showError('Failed to load scraper details')
  }
})

onUnmounted(() => {
  stopPolling()
})

function getStatusColor(status) {
  const colors = {
    inactive: 'grey',
    generating: 'info',
    active: 'success',
    failed: 'error'
  }
  return colors[status] || 'grey'
}

function getRunStatusColor(status) {
  const colors = { running: 'primary', completed: 'success', failed: 'error' }
  return colors[status] || 'grey'
}

function formatDate(dateString) {
  return new Date(dateString).toLocaleString()
}

async function handleGenerateCode() {
  try {
    generating.value = true
    generationStatus.value = 'Starting code generation...'

    await scraperService.generateScraperCode(route.params.id)

    generationStatus.value = 'Analyzing website...'
    startPolling()
  } catch (error) {
    console.error('Failed to generate code:', error)
    showError('Failed to start code generation: ' + error)
    generating.value = false
  }
}

function startPolling() {
  generating.value = true
  generationStatus.value = 'Generating code...'

  // Poll every 5 seconds
  pollingInterval = setInterval(async () => {
    try {
      await scraperStore.fetchScraper(route.params.id)

      const status = scraperStore.currentScraper?.status

      if (status === 'active') {
        stopPolling()
        generating.value = false
        showSuccess('Code generated successfully!')
        activeTab.value = 'code' // Switch to code tab
      } else if (status === 'failed') {
        stopPolling()
        generating.value = false
        showError('Code generation failed. Please try again.')
      } else if (status === 'generating') {
        // Still generating, update status message
        const iterations = scraperStore.currentScraper?.scraping_config?.iterations
        if (iterations) {
          generationStatus.value = `Generating code... (${iterations} iterations)`
        } else {
          generationStatus.value = 'Generating code... Please wait'
        }
      }
    } catch (error) {
      console.error('Polling error:', error)
      stopPolling()
      generating.value = false
      showError('Failed to check generation status')
    }
  }, 5000) // Poll every 5 seconds
}

function stopPolling() {
  if (pollingInterval) {
    clearInterval(pollingInterval)
    pollingInterval = null
  }
}

async function handleRunScraper() {
  try {
    await scraperStore.runScraper(route.params.id)
    showSuccess('Scraper run started')
    await scraperStore.fetchScraperRuns(route.params.id)
  } catch (error) {
    console.error('Failed to run scraper:', error)
    showError('Failed to start scraper run')
  }
}

async function handleDeleteScraper() {
  if (confirm('Are you sure you want to delete this scraper?')) {
    try {
      await scraperStore.deleteScraper(route.params.id)
      showSuccess('Scraper deleted successfully')
      router.push({ name: 'scrapers' })
    } catch (error) {
      console.error('Failed to delete scraper:', error)
      showError('Failed to delete scraper')
    }
  }
}

function showError(message) {
  errorMessage.value = message
  errorSnackbar.value = true
}

function showSuccess(message) {
  successMessage.value = message
  successSnackbar.value = true
}
</script>
