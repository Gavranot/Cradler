<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="6" lg="4">
        <v-card elevation="8" class="pa-4">
          <v-card-title class="text-h4 text-center mb-4">
            <v-icon size="large" color="primary" class="mr-2">mdi-web-box</v-icon>
            Cradler
          </v-card-title>

          <v-card-subtitle class="text-center mb-4">
            Sign in to your account
          </v-card-subtitle>

          <v-card-text>
            <v-form ref="formRef" @submit.prevent="handleLogin">
              <!-- Email Field -->
              <v-text-field
                v-model="email"
                label="Email"
                type="email"
                prepend-inner-icon="mdi-email"
                variant="outlined"
                :rules="emailRules"
                :disabled="loading"
                required
                class="mb-2"
              />

              <!-- Password Field -->
              <v-text-field
                v-model="password"
                label="Password"
                :type="showPassword ? 'text' : 'password'"
                prepend-inner-icon="mdi-lock"
                :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
                @click:append-inner="showPassword = !showPassword"
                variant="outlined"
                :rules="passwordRules"
                :disabled="loading"
                required
                class="mb-2"
              />

              <!-- Error Alert -->
              <v-alert
                v-if="errorMessage"
                type="error"
                density="compact"
                closable
                @click:close="errorMessage = ''"
                class="mb-4"
              >
                {{ errorMessage }}
              </v-alert>

              <!-- Login Button -->
              <v-btn
                type="submit"
                color="primary"
                size="large"
                block
                :loading="loading"
                :disabled="loading"
                class="mb-4"
              >
                Sign In
              </v-btn>

              <!-- Register Link -->
              <div class="text-center">
                <span class="text-body-2">Don't have an account?</span>
                <v-btn
                  variant="text"
                  color="primary"
                  size="small"
                  :to="{ name: 'register' }"
                  :disabled="loading"
                >
                  Create Account
                </v-btn>
              </div>
            </v-form>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

// Form state
const formRef = ref(null)
const email = ref('')
const password = ref('')
const showPassword = ref(false)
const loading = ref(false)
const errorMessage = ref('')

// Validation rules
const emailRules = [
  v => !!v || 'Email is required',
  v => /.+@.+\..+/.test(v) || 'Email must be valid'
]

const passwordRules = [
  v => !!v || 'Password is required',
  v => v.length >= 8 || 'Password must be at least 8 characters'
]

/**
 * Handle login form submission
 */
async function handleLogin() {
  // Validate form
  const { valid } = await formRef.value.validate()
  if (!valid) return

  loading.value = true
  errorMessage.value = ''

  try {
    await authStore.login(email.value, password.value)

    // Redirect to dashboard on success
    router.push({ name: 'dashboard' })
  } catch (error) {
    errorMessage.value = typeof error === 'string' ? error : 'Login failed. Please check your credentials.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.fill-height {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
</style>
