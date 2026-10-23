# Jellyseerr - Albert plugin

## Description

Review the media requests on a [Jellyseerr](https://github.com/Fallenbagel/jellyseerr)
server and add new ones, without leaving the keyboard.

Type `seerr ` with nothing after it and you get the recent requests, the ones
waiting for a decision first, so <kbd>ENTER</kbd> on a pending request approves it.
Anything you type instead is searched on Jellyseerr's own catalogue, and
<kbd>ENTER</kbd> on a hit requests it.

## Usage

### The request list

`seerr ` lists the recent requests. Pending ones come first - they are the
ones there is something to decide about - and everything else follows in the order
Jellyseerr returns it, newest first. Each row shows the title, the kind of media,
the seasons for a series, the status, who asked for it and how long ago.

The first action is the one <kbd>ENTER</kbd> runs:

| Row          | <kbd>ENTER</kbd> does |
| ------------ | --------------------- |
| Pending      | Approve it            |
| Anything else | Open it in the browser |

The remaining actions, reached with the usual Albert <kbd>ALT</kbd>/<kbd>CTRL</kbd>/<kbd>SHIFT</kbd>
+ <kbd>ENTER</kbd> combinations, are:

| Action                | What it does                                            |
| --------------------- | ------------------------------------------------------- |
| `Approve <title>`     | Approves the pending request                             |
| `Decline <title>`     | Declines the pending request                             |
| `Open in browser`     | Opens the title's page in the Jellyseerr web UI          |
| `Open Jellyseerr`     | Opens the request queue in the Jellyseerr web UI         |
| `Reload the request list` | Asks Jellyseerr for a fresh list                     |

### Requesting something new

Type at least two characters to search Jellyseerr's catalogue. Every hit is a movie
or a series; people and collections are left out, because the API cannot request
them. A hit that already exists in the library is only worth opening, so:

| Hit                       | First action    |
| ------------------------- | --------------- |
| A movie not requested yet | `Request <title>` |
| A series that is not fully available | `Request <title>` |
| Anything already available | `Open in browser` |

Series are always worth asking for: some seasons may be missing, and Jellyseerr
drops the ones it already has rather than refusing. A movie that was already
requested (or is being downloaded) is not offered again.

A single character only shows a hint - it is not searched, because one letter
matches most of the catalogue and each search is a TMDB lookup on Jellyseerr's
side.

Every action you trigger pops up an Albert notification when it is done. If the
server cannot be reached, the row becomes the error itself, with actions to retry
or copy it.

## Configuration

Open the plugin's configuration window from the Albert settings and fill in:

| Setting           | Meaning                                                                    |
| ----------------- | -------------------------------------------------------------------------- |
| `Jellyseerr URL`  | The URL of your Jellyseerr instance, e.g. `http://localhost:5055`           |
| `API key`         | An API key from Jellyseerr, under Settings > General > API Key              |
| `API key command` | A command that prints the API key on stdout - see below                     |

The plugin only ever talks to that one server, and reads and writes nothing but
media requests.

### Keeping the API key off the disk

A key typed into `API key` is stored by Albert in plaintext. To avoid that, leave
`API key` empty and put a command in `API key command` instead:

```
pass show jellyseerr
# or
rbw get jellyseerr
# or
secret-tool lookup service jellyseerr
```

The command is run through the shell when the key is first needed, and whatever it
prints on stdout is used as the key. The command **wins over** the `API key` field,
so the two can both be set and the plaintext one is simply ignored. The key it
prints is held in memory only and is never written back to the config; it is
fetched once per session (a failure is not remembered, so unlocking your password
manager and trying again just works).

A command that fails, hangs for more than 30 seconds, or prints nothing leaves the
row as an error you can retry.

### Which user the requests are made as

Jellyseerr authenticates the key and acts as the user it belongs to. A key that
belongs to an administrator - the one under Settings > General does - means
requests made here are approved on the spot instead of landing in the queue. Use a
key that belongs to a regular user if you would rather they were queued.

## Notes

- The URL may include a path if Jellyseerr sits behind a reverse proxy, e.g.
  `https://media.example.com/jellyseerr`. The plugin keeps that prefix on the API
  routes as well as on the web UI links.
- A request payload carries no title, so each row costs a lookup of its own;
  titles are fetched a handful at a time and cached for the session.
- The request list and each search term are cached in memory for a short while -
  30 seconds for the list, 60 seconds per search term - so backspacing over a word
  does not re-query Jellyseerr. Changing the settings, or choosing an action,
  clears the caches.
- Whatever the URL is, it is contacted over plain HTTP. Put Jellyseerr behind TLS
  (or a reverse proxy) if it is not on localhost.
- The API key is sent as an `X-API-Key` header. A key typed into the settings sits
  in Albert's config in plaintext; use the `API key command` field to keep it off
  the disk.
- Tested against Jellyseerr v1.9.2.

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
