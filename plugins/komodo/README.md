# Komodo - Albert plugin

## Description

Control the containers, stacks and resource syncs of a running
[Komodo](https://github.com/moghtech/komodo) server without leaving the keyboard.

Type `komodo ` with nothing after it and you get everything Komodo knows about -
containers, stacks and resource syncs - grouped by kind. Anything you type instead
narrows that list by name, across all three kinds at once.

## Usage

`komodo ` lists every container, stack and resource sync, stacks first, then
containers, then resource syncs, each alphabetical. Type to filter - `komodo medi`
narrows the list down to anything named `media`. The match is fuzzy, so `komodo
mdia` still finds it, and a typo still finds the entry you meant. A container or
stack is also found by the name of the server it runs on, so `komodo raspberrypi`
lists everything on that server.

Every row shows its kind, state and a couple of useful details in its subtext, e.g.
`Stack | homelab | RUNNING | web, db` or `Resource Sync | Changes pending | 3
changes`. The icon reflects the state too: green for running/healthy, orange for
in-progress or needs-attention, gray for stopped, red for an error state.

The actions on each kind, reached with the usual Albert
<kbd>ALT</kbd>/<kbd>CTRL</kbd>/<kbd>SHIFT</kbd> + <kbd>ENTER</kbd> combinations:

| Kind | Actions |
| ---- | ------- |
| Container | `Open in browser`, `Start`, `Stop`, `Restart`, `Pause`, `Unpause` |
| Stack | `Open in browser`, `Deploy`, `Start`, `Stop`, `Restart`, `Pause`, `Unpause` |
| Resource Sync | `Open in browser`, `Refresh`, `Execute` |

`Open in browser` is always the first action, so `komodo home` plus
<kbd>ENTER</kbd> takes you straight to that entry's page in the Komodo web UI.

For a resource sync, `Refresh` recomputes the pending diff against its source
(the same as Komodo's own "Refresh" button) without changing anything, and
`Execute` applies it - deploys whatever the sync says should change.

Destructive actions (destroying a container or a stack) are deliberately left out
of this plugin; use the Komodo web UI for those.

Every action you trigger pops up an Albert notification when it is done, with the
detail from Komodo's own update log if it failed. If the server cannot be reached,
the row becomes the error itself, with actions to retry or copy it.

## Configuration

Open the plugin's configuration window from the Albert settings and fill in:

| Setting              | Meaning                                                              |
| -------------------- | ---------------------------------------------------------------------|
| `Komodo URL`         | The URL of your Komodo instance, e.g. `http://localhost:9120`         |
| `API key`            | An API key from Komodo                                                |
| `API secret`         | The secret that was handed out together with the API key             |
| `API key command`    | A command that prints the API key on stdout - see below               |
| `API secret command` | A command that prints the API secret on stdout - see below            |

The plugin only ever talks to that one server.

### Getting an API key and secret

Create one for your own user, or for a dedicated Service User with limited
permissions, from the Komodo UI's settings page. Komodo hands out the key and the
secret together, once, at creation time - if you lose the secret the only way to
get a new one is to create a fresh key.

### Keeping the key and secret off the disk

A value typed into `API key` or `API secret` is stored by Albert in plaintext. To
avoid that, leave the field empty and put a command in `API key command` / `API
secret command` instead:

```
pass show komodo/key
# or
rbw get komodo-key
```

The command is run through the shell when the value is first needed, and whatever
it prints on stdout is used. It **wins over** the plaintext field next to it, so
both can be set and the plaintext one is simply ignored. The value it prints is
held in memory only and is never written back to the config; it is fetched once
per session (a failure is not remembered, so unlocking your password manager and
trying again just works).

A command that fails, hangs for more than 30 seconds, or prints nothing leaves the
row as an error you can retry.

## Notes

- The container, stack and resource sync list is cached in memory for 5 seconds,
  so backspacing or retyping a search does not re-query Komodo on every keystroke.
  Triggering an action clears the cache, so the list reflects the change on the
  very next query.
- A container's or stack's server is read straight from Komodo's own list
  response; the plugin never has to ask about servers separately.
- Authentication is the `X-Api-Key` / `X-Api-Secret` header pair. Whatever the URL
  is, it is contacted as given; put Komodo behind TLS (or a reverse proxy) if it is
  not on localhost.

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
