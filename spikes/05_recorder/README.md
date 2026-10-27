# Spike 5: recorder on a real phone

Camera and microphone only work in a secure context: `https://`, or `http://localhost`. Pick one of the
two setups below, open the page on the phone, record once for the full 60 s while saying a few prices, then
tap **Copy results** and paste the JSON into `spikes/RESULTS.md` (or send it to the developer).

What we want to learn: which `mimeType` the phone actually records, the real resolution and frame rate,
whether the torch works, and the file size of 60 s at ~2.5 Mbps.

## Option A (simplest): USB cable + Chrome port forwarding

The phone opens `http://localhost:8080`, which Chrome treats as secure, so no certificate is needed.

1. On the phone: Settings → About phone → tap **Build number** 7 times, then Developer options →
   **USB debugging** on. Connect the cable and allow the computer.
2. On the computer:
   ```sh
   uv run python -m http.server 8080 --bind 127.0.0.1 --directory spikes/05_recorder
   ```
3. On the computer, open `chrome://inspect/#devices` in Chrome → **Port forwarding…** → add
   `8080` → `localhost:8080`, tick **Enable port forwarding**.
4. On the phone, open Chrome at `http://localhost:8080`.

## Option B: Wi-Fi with a locally trusted HTTPS certificate (mkcert)

Use this when the phone can't be cabled, and later for testing the PWA service worker (which needs a
certificate the phone trusts).

1. Install mkcert (`choco install mkcert` on Windows, `brew install mkcert` on macOS), then:
   ```sh
   mkcert -install
   mkcert 192.168.1.20          # your computer's LAN IP (ipconfig / ip addr)
   ```
   This writes `192.168.1.20.pem` and `192.168.1.20-key.pem` (both gitignored: never commit them).
2. Copy the mkcert root CA to the phone: run `mkcert -CAROOT`, take `rootCA.pem` from that folder, and
   on Android go to Settings → Security → Encryption & credentials → **Install a certificate** →
   **CA certificate**. Remove it after testing.
3. Serve over HTTPS:
   ```sh
   uv run python spikes/05_recorder/serve_https.py --cert 192.168.1.20.pem --key 192.168.1.20-key.pem
   ```
4. On the phone (same Wi-Fi), open `https://192.168.1.20:8443`. Allow port 8443 in the Windows firewall
   if the page doesn't load.

Accepting a self-signed certificate warning instead of installing a CA lets the camera work, but service
workers stay disabled, so prefer Option B's trusted certificate.
