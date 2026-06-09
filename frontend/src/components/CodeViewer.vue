<template>
  <v-card>
    <v-card-title class="d-flex align-center">
      <v-icon start>mdi-code-braces</v-icon>
      Generated Scraper Code
      <v-spacer></v-spacer>
      <v-btn
        variant="text"
        icon="mdi-content-copy"
        @click="copyToClipboard"
        :disabled="!code"
      >
        <v-icon>mdi-content-copy</v-icon>
        <v-tooltip activator="parent" location="top">
          Copy code
        </v-tooltip>
      </v-btn>
    </v-card-title>

    <v-card-text v-if="code">
      <div class="code-container">
        <pre><code class="language-python">{{ code }}</code></pre>
      </div>
    </v-card-text>

    <v-card-text v-else class="text-center py-8">
      <v-icon size="64" color="grey-lighten-1">mdi-code-tags</v-icon>
      <p class="text-grey mt-4">No code generated yet</p>
      <p class="text-caption text-grey">Click "Generate Code" to create a scraper</p>
    </v-card-text>

    <v-snackbar v-model="snackbar" :timeout="2000" color="success">
      Code copied to clipboard!
    </v-snackbar>
  </v-card>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  code: {
    type: String,
    default: null
  }
})

const snackbar = ref(false)

const copyToClipboard = async () => {
  try {
    await navigator.clipboard.writeText(props.code)
    snackbar.value = true
  } catch (error) {
    console.error('Failed to copy:', error)
  }
}
</script>

<style scoped>
.code-container {
  background-color: #1e1e1e;
  border-radius: 4px;
  overflow-x: auto;
}

pre {
  margin: 0;
  padding: 16px;
  color: #d4d4d4;
  font-family: 'Courier New', Courier, monospace;
  font-size: 14px;
  line-height: 1.6;
}

code {
  color: #d4d4d4;
}

/* Simple Python syntax highlighting */
.language-python {
  white-space: pre-wrap;
  word-wrap: break-word;
}
</style>
