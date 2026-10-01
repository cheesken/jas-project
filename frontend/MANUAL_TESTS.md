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
- [ ] 4. The dialog accepts `.pdf`, `.txt`, `.png`, `.jpg` and `.jpeg` files; other types are greyed out.
- [ ] 5. Selecting a PDF triggers a toast: `"Uploading <name>..."`.
- [ ] 6. On 201 response, toast updates to `"<name> is being indexed."`.
- [ ] 7. Submitting a query navigates to the results screen with the query echoed in the search bar.
- [ ] 8. Results render with all five fields visible (excerpt, file name, source type badge, date, score).
- [ ] 9. Empty result set shows the API's `response` message.
- [ ] 10. Backend down (`docker compose stop api`): submit a query → see `"Could not reach the backend. Is it running?"`.
- [ ] 11. DevTools Network tab (toggle via `Cmd+Option+I`): verify zero requests go anywhere except `localhost:8000` and `localhost:5173`.
- [ ] 12. Upload a `.txt` file → it is indexed, and a query about its contents returns it with a beige **Document** badge and "Modified:" date.
- [ ] 13. Click "Import Chrome History" → toast `"Chrome history is being indexed."`. A query about a recently visited site returns it with a blue **Browser History** badge, the page title as the heading, and a "Visited:" date.
- [ ] 14. Click "Import Chrome History" again after browsing → results are refreshed, not duplicated.
- [ ] 15. Image results show an orange **Image** badge with a "Captured:" date.
