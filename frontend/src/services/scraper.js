/**
 * Scraper API Service
 * Handles all scraper-related API calls
 */
import api from './api'

export const scraperService = {
  /**
   * Get all scrapers for current user
   * @returns {Promise<Array>} List of scrapers
   */
  async getScrapers() {
    try {
      const response = await api.get('/scrapers')
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to fetch scrapers'
    }
  },

  /**
   * Get a specific scraper by ID
   * @param {string} scraperId - Scraper ID
   * @returns {Promise<Object>} Scraper object
   */
  async getScraper(scraperId) {
    try {
      const response = await api.get(`/scrapers/${scraperId}`)
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to fetch scraper'
    }
  },

  /**
   * Create a new scraper
   * @param {Object} scraperData - Scraper configuration
   * @returns {Promise<Object>} Created scraper
   */
  async createScraper(scraperData) {
    try {
      const response = await api.post('/scrapers', scraperData)
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to create scraper'
    }
  },

  /**
   * Update a scraper
   * @param {string} scraperId - Scraper ID
   * @param {Object} scraperData - Updated scraper data
   * @returns {Promise<Object>} Updated scraper
   */
  async updateScraper(scraperId, scraperData) {
    try {
      const response = await api.put(`/scrapers/${scraperId}`, scraperData)
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to update scraper'
    }
  },

  /**
   * Delete a scraper
   * @param {string} scraperId - Scraper ID
   * @returns {Promise<void>}
   */
  async deleteScraper(scraperId) {
    try {
      await api.delete(`/scrapers/${scraperId}`)
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to delete scraper'
    }
  },

  /**
   * Run a scraper
   * @param {string} scraperId - Scraper ID
   * @returns {Promise<Object>} Scraping run object
   */
  async runScraper(scraperId) {
    try {
      const response = await api.post(`/scrapers/${scraperId}/run`)
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to run scraper'
    }
  },

  /**
   * Get scraping runs for a scraper
   * @param {string} scraperId - Scraper ID
   * @returns {Promise<Array>} List of scraping runs
   */
  async getScraperRuns(scraperId) {
    try {
      const response = await api.get(`/scrapers/${scraperId}/runs`)
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to fetch scraper runs'
    }
  },

  /**
   * Generate scraper code via Secondary Agent
   * @param {string} scraperId - Scraper ID
   * @returns {Promise<Object>} Generation result
   */
  async generateScraperCode(scraperId) {
    try {
      const response = await api.post(`/scrapers/${scraperId}/generate`)
      return response
    } catch (error) {
      throw error.response?.data?.detail || 'Failed to generate scraper code'
    }
  }
}
