<template>
  <v-container fluid class="fill-height">
    <v-row align="center" justify="center">
      <v-col cols="12" md="8" lg="6">
        <v-card elevation="8" class="text-center pa-8">
          <v-icon size="100" color="primary" class="mb-4">
            mdi-robot
          </v-icon>

          <h1 class="text-h3 mb-4">Welcome to Cradler</h1>
          <p class="text-h6 text-grey mb-6">
            AI-powered web scraping platform
          </p>

          <v-card-text class="text-body-1 mb-6">
            Automatically generate, deploy, and maintain custom web scrapers
            using AI agents. Zero code required.
          </v-card-text>

          <v-row justify="center">
            <v-col cols="auto">
              <v-btn
                color="primary"
                size="large"
                prepend-icon="mdi-chat"
                to="/chat"
              >
                Create Scraper
              </v-btn>
            </v-col>
            <v-col cols="auto">
              <v-btn
                variant="outlined"
                size="large"
                prepend-icon="mdi-login"
                to="/login"
              >
                Sign In
              </v-btn>
            </v-col>
          </v-row>

          <v-divider class="my-8"></v-divider>

          <v-row>
            <v-col cols="12" md="4">
              <v-icon color="primary" size="40">mdi-auto-fix</v-icon>
              <h3 class="mt-2">Zero Code</h3>
              <p class="text-body-2">
                Describe what you need, AI does the rest
              </p>
            </v-col>
            <v-col cols="12" md="4">
              <v-icon color="primary" size="40">mdi-wrench-cog</v-icon>
              <h3 class="mt-2">Self-Healing</h3>
              <p class="text-body-2">
                Automatic repair when websites change
              </p>
            </v-col>
            <v-col cols="12" md="4">
              <v-icon color="primary" size="40">mdi-rocket-launch</v-icon>
              <h3 class="mt-2">Scalable</h3>
              <p class="text-body-2">
                Handle thousands of concurrent scrapers
              </p>
            </v-col>
          </v-row>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
// Home page component
</script>

<style scoped>
.fill-height {
  min-height: 80vh;
}
</style>
