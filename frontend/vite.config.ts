import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  // Set the third parameter to '' to load all env regardless of the `VITE_` prefix.
  const env = loadEnv(mode, process.cwd(), '')
  console.log('Loaded environment variables:', env)

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',  // Allow connections from any IP
      port: 5173,       // Explicitly set the port
      strictPort: true, // Fail if port is in use
      hmr: {
        host: 'localhost' // Use localhost for HMR
      }
    },
    preview: {
      host: false,
      allowedHosts: [
        'pipebot.example.com'
      ]
    }
  }
})
