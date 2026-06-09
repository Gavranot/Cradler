<template>
  <v-container fluid>
    <v-row class="mb-4">
      <v-col>
        <div class="d-flex justify-space-between align-center">
          <h1 class="text-h4">My Scrapers</h1>
          <v-btn color="primary" :to="{ name: 'chat' }">
            <v-icon start>mdi-plus</v-icon>
            Create New Scraper
          </v-btn>
        </div>
      </v-col>
    </v-row>

    <v-row v-if="scraperStore.loading">
      <v-col cols="12" class="text-center py-12">
        <v-progress-circular indeterminate size="64" color="primary"></v-progress-circular>
        <p class="mt-4 text-grey">Loading scrapers...</p>
      </v-col>
    </v-row>

    <v-row v-else-if="scraperStore.scrapers.length === 0">
      <v-col cols="12" class="text-center py-12">
        <v-icon size="100" color="grey-lighten-2">mdi-spider-web</v-icon>
        <h2 class="text-h5 mt-4 text-grey">No scrapers yet</h2>
        <p class="text-body-1 mt-2 text-grey">Create your first scraper to get started</p>
        <v-btn color="primary" :to="{ name: 'chat' }" class="mt-4">
          <v-icon start>mdi-plus</v-icon>
          Create Scraper
        </v-btn>
      </v-col>
    </v-row>

    <v-row v-else>
      <v-col v-for="scraper in scraperStore.scrapers" :key="scraper.id" cols="12" md="6" lg="4">
        <v-card hover @click="$router.push({ name: 'scraper-detail', params: { id: scraper.id } })">
          <v-card-title class="d-flex align-center">
            <v-icon class="mr-2" :color="getStatusColor(scraper.status)">mdi-circle</v-icon>
            {{ scraper.name }}
          </v-card-title>
          <v-card-subtitle>{{ scraper.target_domain || scraper.target_url }}</v-card-subtitle>
          <v-card-text>
            <div class="d-flex justify-space-between">
              <div>
                <div class="text-caption text-grey">Status</div>
                <div class="text-body-2">{{ scraper.status }}</div>
              </div>
              <div>
                <div class="text-caption text-grey">Last Run</div>
                <div class="text-body-2">{{ scraper.last_run_at ? formatDate(scraper.last_run_at) : 'Never' }}</div>
              </div>
            </div>
          </v-card-text>
          <v-card-actions>
            <v-btn variant="text" size="small">View Details</v-btn>
            <v-spacer></v-spacer>
            <v-btn icon="mdi-play" size="small" variant="text" color="success" @click.stop="handleRunScraper(scraper.id)"></v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
import { onMounted } from 'vue'
import { useScraperStore } from '@/stores/scraper'

const scraperStore = useScraperStore()

onMounted(async () => {
  try {
    await scraperStore.fetchScrapers()
  } catch (error) {
    console.error('Failed to load scrapers:', error)
  }
})

function getStatusColor(status) {
  const colors = { active: 'success', paused: 'warning', error: 'error', inactive: 'grey' }
  return colors[status] || 'grey'
}

function formatDate(dateString) {
  return new Date(dateString).toLocaleString()
}

async function handleRunScraper(scraperId) {
  try {
    await scraperStore.runScraper(scraperId)
  } catch (error) {
    console.error('Failed to run scraper:', error)
  }
}
</script>
