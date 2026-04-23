/** @type {import('tailwindcss').Config} */
export default {
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			colors: {
				bg: '#0f1115',
				panel: '#181b22',
				border: '#262a33',
				text: '#e5e7eb',
				muted: '#9aa4b2',
				accent: '#a47cff',
				gold: '#ffd166',
				danger: '#ff6b6b',
				ok: '#4ade80'
			},
			fontFamily: {
				sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif']
			}
		}
	},
	plugins: []
};