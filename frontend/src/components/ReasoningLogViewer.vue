<template>
  <v-card>
    <v-card-title class="d-flex align-center">
      <v-icon start>mdi-brain</v-icon>
      AI Reasoning Log
      <v-spacer></v-spacer>
      <v-chip v-if="reasoningLog && reasoningLog.length > 0" size="small">
        {{ reasoningLog.length }} steps
      </v-chip>
    </v-card-title>

    <v-card-text v-if="reasoningLog && reasoningLog.length > 0">
      <v-expansion-panels variant="accordion">
        <v-expansion-panel
          v-for="(entry, index) in reasoningLog"
          :key="index"
        >
          <v-expansion-panel-title>
            <div class="d-flex align-center">
              <v-chip size="small" color="primary" class="mr-3">
                Step {{ entry.iteration }}
              </v-chip>
              <span class="text-body-2">{{ entry.type || 'reasoning.text' }}</span>
            </div>
          </v-expansion-panel-title>

          <v-expansion-panel-text>
            <div class="reasoning-content">
              <p class="text-body-2">{{ entry.text }}</p>

              <v-divider class="my-3" v-if="entry.format"></v-divider>

              <div v-if="entry.format" class="text-caption text-grey">
                <v-icon size="small" start>mdi-information-outline</v-icon>
                Format: {{ entry.format }}
              </div>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </v-card-text>

    <v-card-text v-else class="text-center py-8">
      <v-icon size="64" color="grey-lighten-1">mdi-brain-outline</v-icon>
      <p class="text-grey mt-4">No reasoning log available</p>
      <p class="text-caption text-grey">
        The AI's thinking process will appear here after code generation
      </p>
    </v-card-text>
  </v-card>
</template>

<script setup>
const props = defineProps({
  reasoningLog: {
    type: Array,
    default: () => []
  }
})
</script>

<style scoped>
.reasoning-content {
  line-height: 1.8;
}

.reasoning-content p {
  white-space: pre-wrap;
  word-wrap: break-word;
}
</style>
