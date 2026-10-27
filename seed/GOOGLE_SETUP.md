# Set up the Google demo account (Part 2, CLAUDE.md 10.5)

Part 2 reads one Calendar event and its RSVP emails from a Google account. Use a **new demo account**, not a personal or a work account. All its data is synthetic (D13). Only Jaco can do these steps, because they need a new account and a sign-in.

It takes about 20 minutes.

## 1. Create the demo account

1. Open <https://accounts.google.com/signup> in a private browser window.
2. Create a new Gmail account, for example `eventai.demo.<something>@gmail.com`.
3. Keep this window signed in as the demo account for steps 2–4.

## 2. Create the Cloud project and turn on the two APIs

1. Open <https://console.cloud.google.com/>, signed in as the demo account. Accept the terms.
2. Open the project selector (top left), then click **New project**:
   - Name: `event-ai-demo`
   - Click **Create**, then select the project.
3. Open **APIs & Services → Library**. Turn on these two APIs:
   - **Google Calendar API**: search for it, open it, then click **Enable**.
   - **Gmail API**: the same.

## 3. Set up the consent screen (it stays in Testing)

1. Open **APIs & Services → OAuth consent screen**. On newer consoles this is **Google Auth Platform → Get started**.
2. Fill in the app details:
   - App name: `Event AI demo`
   - User support email: the demo account
   - Audience: **External**
   - Contact email: the demo account
   - Then accept and **Create**.
3. Under **Audience** (or **Test users**), click **Add users** and add the demo account's own address. The publishing status stays **Testing**. Do not publish the app.
4. Optional: under **Data access**, add the four scopes, so the screen shows what the app asks for:
   - `.../auth/calendar.readonly`
   - `.../auth/gmail.readonly`
   - `.../auth/calendar.events`
   - `.../auth/gmail.insert`

## 4. Create the OAuth client and save `credentials.json`

1. Open **Clients** (or **APIs & Services → Credentials**), then **Create client** (or **Create credentials → OAuth client ID**).
2. Application type: **Desktop app**. Name: `event-ai`. Click **Create**.
3. Click **Download JSON**.
4. Save the file in the repository root as **`credentials.json`**. It is gitignored: never commit it.

## 5. Tell Claude Code

Claude Code then runs `python seed/seed_google.py`. A browser window opens to ask for permission:
- Sign in as the **demo account**.
- On "Google hasn't verified this app", click **Continue**. The app is yours and is in Testing.
- Allow access.

The script then does three things:
- It creates the event `partnersummit2026` in the demo account's calendar. It sends no invitations (`sendUpdates="none"`).
- It inserts the 13 RSVP emails into the inbox. They are inserted, not sent.
- It saves `token_seed.json` (gitignored).

The first Part 2 run with **Source = google** asks once more, for the read-only scopes, and saves `token.json`.

## Limits

- **In Testing status, the sign-in expires after 7 days.** Sign in again one day before the interview: delete `token.json`, then run once.
- **The agent only reads**, with `calendar.readonly` and `gmail.readonly`. Only the seed script writes, with its own token.
