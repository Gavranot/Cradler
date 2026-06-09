<template>
  <v-app>
    <!-- Navigation Bar (only show when authenticated) -->
    <v-app-bar v-if="authStore.isAuthenticated" app color="primary" dark elevation="2">
      <v-app-bar-nav-icon @click="drawer = !drawer" class="d-lg-none"></v-app-bar-nav-icon>

      <v-toolbar-title class="d-flex align-center">
        <v-icon size="large" class="mr-2">mdi-web-box</v-icon>
        <span class="text-h5 font-weight-bold">Cradler</span>
      </v-toolbar-title>

      <!-- Desktop Navigation Links -->
      <v-tabs class="d-none d-lg-flex ml-8" align-with-title>
        <v-tab :to="{ name: 'dashboard' }" exact>
          <v-icon start>mdi-view-dashboard</v-icon>
          Dashboard
        </v-tab>
        <v-tab :to="{ name: 'chat' }">
          <v-icon start>mdi-message-text</v-icon>
          Create Scraper
        </v-tab>
        <v-tab :to="{ name: 'scrapers' }">
          <v-icon start>mdi-spider-web</v-icon>
          My Scrapers
        </v-tab>
      </v-tabs>

      <v-spacer></v-spacer>

      <!-- User Menu -->
      <v-menu offset-y>
        <template v-slot:activator="{ props }">
          <v-btn v-bind="props" icon>
            <v-avatar color="secondary" size="40">
              <v-icon>mdi-account-circle</v-icon>
            </v-avatar>
          </v-btn>
        </template>
        <v-list>
          <v-list-item>
            <v-list-item-title class="text-body-2 font-weight-bold">
              {{ authStore.user?.email }}
            </v-list-item-title>
            <v-list-item-subtitle class="text-caption">
              {{ authStore.user?.role }}
            </v-list-item-subtitle>
          </v-list-item>
          <v-divider></v-divider>
          <v-list-item @click="handleLogout" :disabled="loggingOut">
            <template v-slot:prepend>
              <v-icon>mdi-logout</v-icon>
            </template>
            <v-list-item-title>Logout</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </v-app-bar>

    <!-- Mobile Navigation Drawer -->
    <v-navigation-drawer v-if="authStore.isAuthenticated" v-model="drawer" app temporary>
      <v-list>
        <v-list-item :to="{ name: 'dashboard' }" exact>
          <template v-slot:prepend>
            <v-icon>mdi-view-dashboard</v-icon>
          </template>
          <v-list-item-title>Dashboard</v-list-item-title>
        </v-list-item>
        <v-list-item :to="{ name: 'chat' }">
          <template v-slot:prepend>
            <v-icon>mdi-message-text</v-icon>
          </template>
          <v-list-item-title>Create Scraper</v-list-item-title>
        </v-list-item>
        <v-list-item :to="{ name: 'scrapers' }">
          <template v-slot:prepend>
            <v-icon>mdi-spider-web</v-icon>
          </template>
          <v-list-item-title>My Scrapers</v-list-item-title>
        </v-list-item>
      </v-list>
    </v-navigation-drawer>

    <!-- Main Content -->
    <v-main>
      <router-view />
    </v-main>

    <!-- Loading Overlay -->
    <v-overlay v-model="loggingOut" persistent class="align-center justify-center">
      <v-progress-circular indeterminate size="64" color="primary"></v-progress-circular>
      <p class="mt-4 text-h6">Logging out...</p>
    </v-overlay>
  </v-app>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const drawer = ref(false)
const loggingOut = ref(false)

/**
 * Handle user logout
 */
async function handleLogout() {
  loggingOut.value = true

  try {
    await authStore.logout()
    router.push({ name: 'login' })
  } catch (error) {
    console.error('Logout error:', error)
  } finally {
    loggingOut.value = false
  }
}
</script>

<style>
/* Global styles */
html {
  overflow-y: auto !important;
}

.v-app-bar .v-tab {
  text-transform: none;
  letter-spacing: normal;
}
</style>
