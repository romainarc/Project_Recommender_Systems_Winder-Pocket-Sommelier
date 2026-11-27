# Pocket Sommelier web app

React (Vite) front end of Pocket Sommelier. FastAPI serves the built version (`dist/`) on
http://localhost:8000, so running the project needs no Node.js.

- `src/App.jsx`: screens (welcome, six-question questionnaire, selection with dish families, cellar)
- `src/i18n.js`: every text in French (default) and English, plus translations of X-Wines values
- `src/Bottle.jsx`: vector bottle illustrations, tinted by wine type (offline, no image download)
- `src/api.js`: calls to `/options`, `/onboard`, `/recommend`, `/log_interaction`

Develop: `npm install && npm run dev` (the API must run on port 8000). Ship: `npm run build`.
