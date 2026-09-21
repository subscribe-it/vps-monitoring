// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import icon from 'astro-icon';

// Panel monitoringu — wyłącznie statyczne wyjście (HTML + assety).
// Zero zależności runtime: brak CDN, brak Google Fonts, brak frameworków JS.
export default defineConfig({
  output: 'static',
  site: 'https://monitoring.subscribeit.pl',
  integrations: [icon()],
  vite: {
    plugins: [tailwindcss()],
  },
  build: {
    assets: 'assets',
  },
  compressHTML: true,
  devToolbar: {
    enabled: false,
  },
});
