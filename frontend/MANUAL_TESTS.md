# Manual Test Checklist

Run through these checks before the demo.

## Prerequisites

- `docker compose up` is running (api + worker + redis)
- Ollama is running locally with `llama3:8b` pulled
- `cd frontend && npm install && npm run dev`

## Checklist

- [ ] 1. App launches with macOS native window chrome (hidden inset title bar).
- [ ] 2. Greeting reads exactly `"Hello, there."`
- [ ] 3. Clicking "Upload Files" opens a native macOS file dialog.
- [ ] 4. The dialog only accepts `.pdf` files (TXT, PNG should be greyed out or rejected).
- [ ] 5. Selecting a PDF triggers a toast: `"Uploading <name>..."`.
- [ ] 6. On 201 response, toast updates to `"<name> is being indexed."`.
- [ ] 7. Submitting a query navigates to the results screen with the query echoed in the search bar.
- [ ] 8. Results render with all five fields visible (excerpt, file name, source type badge, date, score).
- [ ] 9. Empty result set shows the API's `response` message.
- [ ] 10. Backend down (`docker compose stop api`): submit a query → see `"Could not reach the backend. Is it running?"`.
- [ ] 11. DevTools Network tab (toggle via `Cmd+Option+I`): verify zero requests go anywhere except `localhost:8000` and `localhost:5173`.
