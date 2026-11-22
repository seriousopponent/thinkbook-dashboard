import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests',timeout:20000,workers:1,use:{channel:'chrome',baseURL:'http://127.0.0.1:4178',viewport:{width:1180,height:850}},webServer:{command:'npm run dev -- --port 4178',url:'http://127.0.0.1:4178',reuseExistingServer:false},reporter:'list'});
