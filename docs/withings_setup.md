# Connecting your Withings scale (≈ 10 minutes)

Your scale syncs to the Withings cloud. Bloom reads it from there through the Withings Public API (OAuth2).
You need a free developer app once.

## 1. Create the developer app

1. Open **https://developer.withings.com/dashboard/** and log in with the same Withings account your scale uses
   (or create one).
2. Choose **Public Cloud** (not "Medical Cloud").
3. **Create a new organization** → any name (e.g. `Bloom personal`) + your contact email.
4. Service: select **Public API integration** → accept the terms → continue.
5. Fill in the application form:

   | Field | Value |
   |---|---|
   | Target environment | **Development** |
   | Application name | `Bloom` (anything) |
   | Application description | `Personal health dashboard` (anything) |
   | Registered URLs (callback) | `http://localhost:8000/withings/callback` |
   | Logo | optional |

6. **Start the backend first** (`make api` or `make dev`). When you save the app, Withings sends a request to the
   callback URL, and the save fails if nothing answers with HTTP 200. Bloom's `/withings/callback` answers these probes.
7. After saving, the dashboard shows **Client ID** and **Secret** (sometimes called *Consumer Secret*). Copy both.

## 2. Put the credentials in `.env`

```dotenv
WITHINGS_CLIENT_ID=<Client ID>
WITHINGS_CLIENT_SECRET=<Secret>
WITHINGS_REDIRECT_URI=http://localhost:8000/withings/callback
```

It must be *exactly* the same URL as the one registered (same scheme, host, port, path). Restart the backend.

## 3. Connect

Open **http://localhost:3000/data**, click **Connect Withings**, log in, and click **Allow**. You're redirected back to the Data page with
"Withings connected — imported N measurements". Use **Sync now** later to pull new weigh-ins (tokens refresh automatically).

## If Withings refuses the localhost URL

Some accounts get "Fail to connect to callback url". Withings wants a public HTTPS URL. Use a free tunnel:

```bash
brew install ngrok                  # sign up at ngrok.com, it gives you ONE free static domain
ngrok config add-authtoken <token>
ngrok http --url=<your-name>.ngrok-free.app 8000
```

Then register `https://<your-name>.ngrok-free.app/withings/callback` in the Withings dashboard and set the same
value as `WITHINGS_REDIRECT_URI` in `.env`. Keep ngrok running while you click **Connect Withings**; after that it's
only needed again to re-connect, because syncing happens server-side with the stored tokens.

(`cloudflared tunnel --url http://localhost:8000` also works without an account, but the URL changes on every run,
so you'd have to update the Withings app each time.)

## Troubleshooting

| Symptom | Fix |
|---|---|
| `invalid redirect_uri` on the Withings login page | `.env` value ≠ registered URL (check trailing slash, http vs https, port) |
| Page "Withings connection failed … status 503/601" | code already used or expired. Click **Connect Withings** again |
| Connected but 0 measurements | the scale hasn't synced yet: open the Withings app once, then **Sync now** |
| "WITHINGS_CLIENT_ID … not set" | backend wasn't restarted after editing `.env` |
