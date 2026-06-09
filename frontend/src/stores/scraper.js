/**
 * Scraper Store (Pinia)
 * Manages scraper state and operations
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { scraperService } from '@/services/scraper'

export const useScraperStore = defineStore('scraper', () => {
  // State
  const scrapers = ref([])
  const currentScraper = ref(null)
  const scraperRuns = ref([])
  const loading = ref(false)
  const error = ref(null)

  // Getters
  const activeScrapers = computed(() =>
    scrapers.value.filter(s => s.status === 'active')
  )

  const pausedScrapers = computed(() =>
    scrapers.value.filter(s => s.status === 'paused')
  )

  /**
   * Fetch all scrapers
   */
  async function fetchScrapers() {
    loading.value = true
    error.value = null

    try {
      scrapers.value = await scraperService.getScrapers()
      return scrapers.value
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch a specific scraper
   * @param {string} scraperId - Scraper ID
   */
  async function fetchScraper(scraperId) {
    loading.value = true
    error.value = null

    try {
      currentScraper.value = await scraperService.getScraper(scraperId)
      return currentScraper.value
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Create a new scraper
   * @param {Object} scraperData - Scraper configuration
   */
  async function createScraper(scraperData) {
    loading.value = true
    error.value = null

    try {
      const newScraper = await scraperService.createScraper(scraperData)
      scrapers.value.push(newScraper)
      return newScraper
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Update a scraper
   * @param {string} scraperId - Scraper ID
   * @param {Object} scraperData - Updated data
   */
  async function updateScraper(scraperId, scraperData) {
    loading.value = true
    error.value = null

    try {
      const updatedScraper = await scraperService.updateScraper(scraperId, scraperData)

      // Update in list
      const index = scrapers.value.findIndex(s => s.id === scraperId)
      if (index !== -1) {
        scrapers.value[index] = updatedScraper
      }

      // Update current if it's the same
      if (currentScraper.value?.id === scraperId) {
        currentScraper.value = updatedScraper
      }

      return updatedScraper
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Delete a scraper
   * @param {string} scraperId - Scraper ID
   */
  async function deleteScraper(scraperId) {
    loading.value = true
    error.value = null

    try {
      await scraperService.deleteScraper(scraperId)

      // Remove from list
      scrapers.value = scrapers.value.filter(s => s.id !== scraperId)

      // Clear current if it's the deleted one
      if (currentScraper.value?.id === scraperId) {
        currentScraper.value = null
      }
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Run a scraper
   * @param {string} scraperId - Scraper ID
   */
  async function runScraper(scraperId) {
    loading.value = true
    error.value = null

    try {
      const run = await scraperService.runScraper(scraperId)
      return run
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch scraping runs for a scraper
   * @param {string} scraperId - Scraper ID
   */
  async function fetchScraperRuns(scraperId) {
    loading.value = true
    error.value = null

    try {
      scraperRuns.value = await scraperService.getScraperRuns(scraperId)
      return scraperRuns.value
    } catch (err) {
      error.value = err
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

  /**
   * Clear current scraper
   */
  function clearCurrentScraper() {
    currentScraper.value = null
  }

  return {
    // State
    scrapers,
    currentScraper,
    scraperRuns,
    loading,
    error,

    // Getters
    activeScrapers,
    pausedScrapers,

    // Actions
    fetchScrapers,
    fetchScraper,
    createScraper,
    updateScraper,
    deleteScraper,
    runScraper,
    fetchScraperRuns,
    clearError,
    clearCurrentScraper
  }
})
