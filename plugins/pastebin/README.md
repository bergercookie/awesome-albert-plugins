# Pastebin - Albert plugin

## Description

Share a snippet or a file as a link, via a paste service. Type `pb ` and Albert
gives you an item to paste what you just typed. The link is returned instantly
after you pick a service, and you can have it copied to the clipboard and/or
opened in the browser automatically.

Supported services:

| Service | Needs a key? | Notes |
| --- | --- | --- |
| [termbin.com](https://termbin.com/) | No | Pastes are deleted after a week. Only accepts text. |
| [dpaste.org](https://dpaste.org/) | No | Highlights syntax from the filename, a couple of expiry options behind its web UI, and answers with the link cleanly. |
| [0x0.st](https://0x0.st/) | No | Takes some of the largest pastes among the keyless ones, and works well for plain text. |
| [ix.io](https://ix.io/) | No | Tiny, reliable, no fuss. |
| [pastebin.com](https://pastebin.com/) | Yes | The only one that needs a paid Developer API key. |

## Usage

1. Paste some text: `pb echo hello world` (or anything at all after `pb `)
2. Paste a file: `pb file:~/notes.md` or just `pb ~/notes.md`
3. Paste what's piped in: `cat error.log | albert paste` (when launched from a shell)

Albert shows one item - press `ENTER` to paste to the **default** service, or use
the action list to pick a different one. The first action is always the default.

## Configuration

In the plugin settings:

| Setting | Meaning |
| --- | --- |
| `Default service` | Which one to run when you press ENTER. All five are still available as actions. |
| `pastebin.com Developer API key` | Only if you use pastebin.com. Leave empty for the keyless services. |
| `Copy the link to the clipboard` | If checked, the returned URL is copied once the paste succeeds. |
| `Open the link in the browser` | If checked, the returned URL is opened in your default browser. |

Both of the last two can be checked at the same time. When a paste succeeds you
get an Albert notification with the link and a short note about what was done.

## Notes

- No network calls while you're typing — uploads only happen when you trigger an action.
- The max size is 8 MB to avoid accidental uploads. If your snippet is larger than that, use a file-sharing service meant for binaries.
- The plugin only accepts UTF-8 text. For raw binary, use `0x0.st`.
- If a service returns an HTML error page (a common case when overloaded), the plugin refuses to treat it as a link and shows the actual HTTP error instead.

## Installation instructions

Refer to the parent project: [Awesome albert plugins](https://github.com/bergercookie/awesome-albert-plugins)

## Self Promotion

If you find this tool useful, please [star it on Github](https://github.com/bergercookie/awesome-albert-plugins)

## TODO List

See [ISSUES list](https://github.com/bergercookie/awesome-albert-plugins/issues)
for the things that I'm currently either working on or interested in
implementing in the near future. In case there's something you're interested
in working on, don't hesitate to either ask for clarifications or just do it and
directly make a PR.
