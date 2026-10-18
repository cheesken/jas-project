# Zero network traffic capture (US-NF-01)

**Requirement.** US-NF-01: none of the user's data is transmitted to any external server, verified with Wireshark.

**Pass criterion.** During a full session (backend startup, ingesting a document and an image, answering queries, using the desktop app), no packet sent or received by the app's processes leaves the Mac. The app's processes are Electron, Ollama, Docker Desktop (which carries all container traffic) and the Vite dev server (node).

**Owner.** Shamathmika runs the capture. Ananya and Jahnavi review the capture file and sign off below.

## Before you start

1. Quit every app you don't need (browsers, Mail, Slack, Music). They don't affect the result, because traffic is attributed per process, but they make the capture noisy to review.
2. In Docker Desktop, open **Settings → General** and turn off **Send usage statistics**. Then open **Software updates** and turn off **Automatically check for updates**. Docker Desktop's own update checks come from the same process that carries container traffic, so leaving them on gives a false FAIL.
3. Start Ollama from Terminal with `ollama serve`, not from the menu-bar app. The menu-bar app checks for updates.
4. Start the backend with `docker compose up -d`, then start the desktop app with `cd frontend && npm run dev`.

## Run

From the repository root:

```
sudo tests/acceptance/zero_network_capture.sh
```

The script captures on the interface that carries your internet traffic (usually `en0`), with the name of the process behind each packet. While capturing it:

1. restarts the api and worker containers, so model loading is inside the capture
2. ingests a note and a screenshot, and waits until both are indexed
3. asks three questions through `/query`, so retrieval and Ollama both run
4. calls the knowledge graph and status endpoints
5. pauses so you can use the desktop app: run a few searches, open Knowledge Graph and Settings, and upload a file. Press Enter when you're done.
6. removes its test files from the index

To rehearse the workload without capturing (no `sudo` needed), run `NO_CAPTURE=1 tests/acceptance/zero_network_capture.sh`.

## Output

The script writes `~/jas-network-capture-<date>-<time>/`:

| File | Contents |
|---|---|
| `report.txt` | Packet counts, packets by process, DNS lookups, and PASS or FAIL |
| `capture.pcapng` | The raw capture, for review in Wireshark |
| `packets.txt` | Every packet as text, with process name and PID |
| `app-packets.txt` | Only packets from the app's processes. Empty on a PASS. |
| `dns-lookups.txt` | Every hostname looked up during the session |
| `session.log` | What the workload did, with timestamps |

## Review in Wireshark

1. Open `capture.pcapng` in Wireshark.
2. **Who sent traffic.** Select any packet and expand the **PKTAP** section of the packet details. It shows the process name and PID. Right-click the process name field and choose **Apply as Column** to see it for every packet.
3. **Where traffic went.** Open **Statistics → Conversations → IPv4** to see every remote address the Mac talked to during the session.
4. **What was looked up.** Apply the display filter `dns` to see every hostname looked up. A lookup of a third-party host during the session (for example `huggingface.co` or `fonts.googleapis.com`) points to a leak, even before any data is sent.
5. Confirm that no packet attributed to Electron, ollama, com.docker.* or node reaches a non-local address.

## Leaks found and fixed before the first capture

These were found by running each component in a container with networking disabled:

| Component | What it contacted | Fix |
|---|---|---|
| Desktop app | `fonts.googleapis.com` and `fonts.gstatic.com`, to load the DM Sans font on every launch | Font files bundled in `frontend/src/assets/fonts`, and Google Fonts removed from the app's content security policy |
| Embedding model (sentence-transformers) | `huggingface.co`, on every load, to check for model updates | `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` set in the image after the model is downloaded |
| Chunking (tiktoken) | `openaipublic.blob.core.windows.net`, to download the tokenizer file on first use. Offline, indexing failed outright. | Tokenizer file downloaded into the image at build time (`TIKTOKEN_CACHE_DIR=/opt/tiktoken`) |
| ChromaDB | Its telemetry service | Already fixed: `ANONYMIZED_TELEMETRY=False` |

## Sign-off

| Reviewer | Date | Result | Notes |
|---|---|---|---|
| Shamathmika (ran capture) | | | |
| Ananya | | | |
| Jahnavi | | | |
