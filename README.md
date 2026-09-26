# discord-backup-tool

A command line tool to back up Discord channel history, reactions, and attachment metadata to a local SQLite database. I wrote this to keep offline archives of direct messages and private server channels before they get deleted.

It runs entirely over Discord's standard HTTP API using a user token (self-token). It handles rate limits gracefully and resumes previous backups by checking the last saved message ID.

## Installation

Clone this repository and install the dependencies:

```cmd
pip install -r requirements.txt
```

## Usage

You need your Discord authorization token. You can find this in your browser's Developer Tools (Network tab) by looking at any API request headers.

To back up a specific channel:

```cmd
python discord_backup.py --token "YOUR_TOKEN_HERE" --channel "123456789012345678" --output "my_archive.db"
```

If you want to pull multiple channels, you can run it in a loop or call it multiple times with the same database file. The tool will merge them and skip messages that are already saved.

To see all options:

```cmd
python discord_backup.py --help
```

<!-- verified: 2026-09-26 -->
