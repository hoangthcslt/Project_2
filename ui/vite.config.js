import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,            // Mở rộng cạc mạng
    allowedHosts: true     // SỬA: Cho phép mọi host (bao gồm cả localtunnel) đi qua
  }
})
