# HyZone Instagram Bot

Every Sunday at 9 PM it drafts next week's content and sends it to you on Telegram:
**4 designed posters** (Tue, Thu, Sat, Sun) and **3 Reel scripts** (Mon, Wed, Fri).
Formats rotate: each series is a Reel one week and a poster the next, so all 7 poster designs stay in use.
You approve the posters, record the Reels on your phone and send the raw clips back.
The bot edits the videos, you approve, and everything goes live on Instagram at its scheduled time.
You never open Instagram, never edit, never upload, never schedule anything.

**Cost: ₹0.** GitHub Actions (public repo), Gemini free tier, Telegram and the Instagram API are all free. No card needed anywhere.

> **This is a separate repository.** It has no link to your HyZone app repo and cannot read or change it.
> The only GitHub key it uses (step 5) is locked to this one repo.

---

## One-time setup (about an hour)

### 1. Create a NEW GitHub repo
1. github.com → **New repository** → name it `hyzone-social-bot` → **Public** → Create.
   (Public = free unlimited Actions minutes. Your keys stay hidden in encrypted Secrets.
   Don't reuse or touch your app repo.)
2. Upload the files. Easiest from Google Cloud Shell:
   ```bash
   unzip hyzone-social-bot.zip && cd hyzone-social-bot
   git init -b main && git add . && git commit -m "HyZone bot"
   git remote add origin https://github.com/<your-username>/hyzone-social-bot.git
   git push -u origin main
   ```
   (Or drag the files into GitHub's "uploading an existing file" page. The `.github` folder is hidden
   on most computers, so create `.github/workflows/bot.yml` with **Add file → Create new file** and paste it in.)

### 2. Telegram bot (2 minutes)
1. In Telegram, open **@BotFather** → send `/newbot` → pick a name → copy the **token**.
2. Open your new bot and send it `hi`.
3. In a browser open `https://api.telegram.org/bot<TOKEN>/getUpdates` and find `"chat":{"id": 123456789`.
   That number is your **chat ID**. Only messages from this chat are obeyed.

### 3. Gemini key
aistudio.google.com → **Get API key** → **Create API key** → copy it.

### 4. Instagram
1. In the Instagram app, logged in as HyZone: **Settings → Account type and tools → Switch to professional account → Business**.
2. developers.facebook.com → **My Apps → Create app**, and choose the Instagram use case
   (manage messaging & content on Instagram).
3. In the app: **Instagram → API setup with Instagram login → Generate access tokens → Add account** → log in as HyZone.
   If it asks, add the account under **App roles → Instagram testers** and accept the invite in Instagram
   (Settings → Website permissions / Apps and websites → Tester invites).
4. Copy the **access token** and the **Instagram user ID** shown next to the account.
   The bot needs the `instagram_business_basic` and `instagram_business_content_publish` permissions.

Meta renames its menus often. If a label differs, look for "API setup with Instagram login".

### 5. GitHub key that renews the Instagram token (locked to this repo)
Instagram tokens expire after 60 days; the bot renews it monthly by itself using this key.
1. GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. **Repository access: Only select repositories → `hyzone-social-bot` only.** Do NOT select your app repo.
3. **Permissions → Repository → Secrets: Read and write.** Nothing else.
4. Expiration: 1 year (set a calendar reminder to make a new one).

### 6. Add the secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**, one by one:

| Name | Value |
|---|---|
| `GEMINI_API_KEY` | from step 3 |
| `TELEGRAM_BOT_TOKEN` | from step 2 |
| `TELEGRAM_CHAT_ID` | from step 2 |
| `IG_ACCESS_TOKEN` | from step 4 |
| `IG_USER_ID` | from step 4 |
| `GH_PAT` | from step 5 |

### 7. Your details
Edit `config.yaml` on GitHub (pencil icon): set `phone` and `instagram_handle`. Commit.

### 8. Test, then go live
1. Repo → **Actions** → enable workflows if asked → **HyZone bot → Run workflow → action: test**.
   Within ~3 minutes, 7 sample posters arrive on Telegram. (Test posters are never posted.)
2. **Run workflow → action: this_week** to fill the remaining days of the current week (any day, e.g. a Tuesday start).
   Or **action: generate** to draft next week right now.
3. From here it runs by itself every 15 minutes, and drafts every Sunday at 9 PM.

---

## Before Instagram is connected
Leave `IG_ACCESS_TOKEN` and `IG_USER_ID` unset. Everything else works. At each post's time the bot sends the finished
poster or Reel to Telegram with "📲 Time to post" and the caption as a separate message to copy. Post it by hand.
Once you add the two Instagram secrets, it switches to posting by itself.

## Daily use (Telegram)

- **Reply to a poster** with `approved`, or with what to change: *"make it about bed bugs"*, *"funnier"*, *"shorter headline"*.
  The bot redraws it and sends the new version.
- Or type: `approve all` · `approve 1 3` · `change 4: use the bathroom` · `skip 6` · `retry 2`
- `q: Is pest control safe with pets?` queues a follower question for the next **Ask HyZone** Sunday.
- `status`: what's approved and when it goes live.

If a post is still unapproved at its time, you get one reminder and nothing is posted until you say so.
Replies are picked up within about 15 minutes, and posts can go live a few minutes after the set time (GitHub's timer).

## Reels (Mon, Wed, Fri)

**How the editing works.** Telegram is only the courier. When you send a clip, a free GitHub computer downloads it,
**Gemini watches it and writes an edit plan**, and **ffmpeg** (professional video software) carries the plan out:
- cuts pauses, false starts and repeated takes (keeps your last clean take)
- crops to vertical 9:16 and adds punch-in zooms on key lines
- pops up HyZone graphics exactly when you say them: a **stat card** ("30–40"), a **MYTH** stamp, a **FACT** panel, a pest sticker, a **DO THIS** tip
- adds Telugu-English captions with the key word in gold, a hook title at the top, and an end card with your number
- evens out your audio loudness

**Your part:**
1. Sunday night you get each Reel's script. Read it in your own words; mistakes and retakes are fine.
2. Record vertically, ideally with the phone at eye level and your face in the top half of the frame.
3. **Reply to the script message** with the video. Send it as a normal video (not "as file") so Telegram keeps it under the
   bots' 20 MB limit. Record 30–60 seconds.
4. About 5 minutes later the edited Reel comes back. Reply `approved`, or say what to fix:
   *"cut the first line"*, *"zoom on the eggs part"*, *"caption says kemikal, should be chemical"*, *"no sticker"*.
5. Busy that day? Reply `poster` to the script and it makes that day's designed poster instead.

You get a nudge 6 hours before a Reel's time if the video hasn't arrived.
Captions default to Telugu in English letters; set `caption_script: telugu` in `config.yaml` for Telugu script.
Finished videos are kept on a separate `media` branch of this repo (overwritten each time, so it never grows) and
cleaned up 3 days after posting.

## Changing things
- **Topics, voice, facts rules:** `brief.md`
- **Days, series, formats, posting times, Reel days, Sunday drafting time:** `config.yaml`
  (`rotation` holds the weekly lineups; weeks take turns A → B → A. Add a week C to rotate further.)
- **Poster designs:** `templates/` (the 5 locked formats); **Reel graphics:** `templates/reel_*.html`

## If something breaks
The bot messages you on Telegram with the error. Common ones:
- *Gemini model not found*: change `gemini.model` in `config.yaml` to the current Flash model name in AI Studio.
- *Instagram error / token*: redo step 4 and update the `IG_ACCESS_TOKEN` secret.
- *Graph API version*: bump `instagram.graph_version` in `config.yaml`.
- *Nothing happens*: Actions tab → check that the workflow is enabled. GitHub pauses scheduled workflows in repos with
  no activity for 60 days; the bot commits weekly, so this shouldn't happen while it's in use.
