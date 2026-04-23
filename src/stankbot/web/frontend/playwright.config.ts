import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
	testDir: './e2e',
	fullyParallel: false,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 2 : 0,
	workers: process.env.CI ? 1 : undefined,
	reporter: 'html',

	projects: [
		{
			name: 'e2e',
			use: { ...devices['Desktop Chrome'], baseURL: 'http://localhost:8000' }
		},
		{
			name: 'e2e:dev',
			use: { ...devices['Desktop Chrome'], baseURL: 'http://localhost:5173' }
		}
	],

	webServer: [
		{
			command: 'cd ../../../.. && python -m stankbot',
			url: 'http://localhost:8000/healthz',
			reuseExistingServer: !process.env.CI,
			timeout: 30000,
			env: { ENV: 'dev', PYTHONPATH: 'src' }
		},
		// For e2e:dev project, also start Vite dev server
		{
			command: 'npm run dev',
			url: 'http://localhost:5173',
			reuseExistingServer: !process.env.CI,
			timeout: 30000
		}
	]
});
