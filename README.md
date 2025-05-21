# slack-exporter-inline

Export Slack channels or direct messages (DMs) with threads inline and real names resolved — directly to `.txt` files.

Includes:
- Top-level messages and thread replies
- Resolution of Slack mentions:
  - `<@UXXXXXX>` → `@Real Name`
  - `<UXXXXXX>` → `<Real Name>` (e.g. old-style references or logs)
  - `<!subteam^SXXXXXX>` → `@Group Name`
- Optional unresolved/raw output for backup/debugging

---

## 🚀 Features

- 🧵 Threads appear *inline* below their parent messages
- 🧑 Real names instead of Slack user/group IDs
- 💬 Exports both channels and direct messages (DMs)
- 🗃 Optional raw output with unresolved Slack IDs (`--save-unresolved`)
- ⚙️ CLI-friendly and KISS-compliant
- 📅 Interactive prompts when run without arguments

---

## 🔐 Requirements

- Python 3.7+
- A Slack **OAuth User Token** (`xoxp-...`) with the following scopes:

### Required OAuth Scopes:
```
channels:history
groups:history
im:history
mpim:history
users:read
channels:read
groups:read
im:read
mpim:read
usergroups:read
```

---

## 🛠 Setup & Installation

```bash
# install system deps
sudo apt install python3-virtualenv -y

# create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# install python deps
pip install slack-sdk tqdm
```

---

## 🔑 Creating Your Slack API Token

1. Visit: [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click **"Create New App"** → "From scratch"
3. Under **OAuth & Permissions**, add the required scopes (see above)
4. Click **"Install to Workspace"**
5. Copy the `xoxp-...` token

Then:

```bash
export SLACK_TOKEN="xoxp-your-token-here"
```

---

## 📦 Usage

### Export DMs with threads inline:

```bash
./export.py --all-dms
```

### Export specific channels or DMs:

```bash
./export.py --channels "welcome,devops,DM with John Doe"
```

### Save raw (unresolved) version too:

```bash
./export.py --channels "DM with Jane Smith" --save-unresolved
```

### Export messages within a date range:

```bash
./export.py --start 2025-01-01 --end 2025-05-21
```

### Or just run interactively:

```bash
./export.py
```

You’ll be prompted to choose channels and dates.

---

## 📁 Output Example

```
output-2025-05-21-10-00/
├── devops.txt
├── dm-John_Doe.txt

output-2025-05-21-10-00-unresolved/     # only if --save-unresolved is set
├── devops.txt
├── dm-John_Doe.txt
```

---

## 🧑💻 Author

**Andrey Arapov**

GitHub: [@arno01](https://github.com/arno01)

---

## ⚡ Support the project with Bitcoin Lightning

You can scan this Lightning address QR code from your terminal or directly here on GitHub:

➡️  [lightning:andynostr@walletofsatoshi.com](lightning:andynostr@walletofsatoshi.com)

![Donate via Lightning](lightning.png)

---

## 📄 License

[MIT](LICENSE)
