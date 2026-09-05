import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
const backend=process.env.CIL_API_PROXY_TARGET||'http://127.0.0.1:8000';
export default defineConfig({ plugins:[react()], envDir:'..', server:{port:5173,strictPort:true,proxy:{'/api':{target:backend},'/cmpdi/workbench':{target:backend}}}, test:{globals:true,environment:'jsdom',setupFiles:['./src/test-setup.ts']} });
