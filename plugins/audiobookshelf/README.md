# Audiobookshelf - Albert plugin

## Description

Search an [Audiobookshelf](https://www.audiobookshelf.org/) library and play an
audiobook with a local player, without leaving the keyboard.

Type `abs ` followed by an audiobook title, a series or an author and you get the
books that match; <kbd>ENTER</kbd> on one plays it through `cvlc`. The audio is
streamed straight from your Audiobookshelf server to the player, so nothing is
downloaded and the server keeps track of nothing.

## Usage

### Playing an audiobook

`abs ` with nothing after it only shows a hint. Type at least two characters and
every audiobook library on the server is searched at once. Each row is one
audiobook, showing its author, narrator, series, year and length.

An author or a series match is followed up with whatever books it is about, so a
series name gives you its books to play rather than the series itself.

The first action is the one <kbd>ENTER</kbd> runs:

| Action             | What it does                                              |
| ------------------ | -------------------------------------------------------- |
| `Play <title>`     | Streams every audio file of the book to the local player  |
| `Open in browser`  | Opens the audiobook's page in the Audiobookshelf web UI   |
| `Open Audiobookshelf` | Opens the Audiobookshelf web UI                        |

To keep typing cheap, a term that is still being typed never reaches the server,
and a term that was searched in the last minute is remembered, so backspacing
over a word costs nothing.

A single character only shows a hint - it is not searched, because one letter
matches most of the library.

### The player

The books are played by a local command, `cvlc` by default. Change it in the
plugin settings if you would rather use something else; extra flags are allowed,
e.g. `cvlc --play-and-exit`. The player is started detached, so it keeps playing
after Albert's window closes.

Because the player is a separate process, it cannot send the API key as a header;
the key goes into the streaming URL's query string instead, which Audiobookshelf
accepts, and nowhere else. If a book has several audio files they are handed to
the player in order, as one playlist.

Every action pops up an Albert notification when it is done. If the server cannot
be reached, the row becomes the error itself, with actions to retry or copy it.

## Configuration

| Setting           | Default  | What it is                                              |
| ----------------- | -------- | ------------------------------------------------------- |
| `Audiobookshelf URL` | -      | e.g. `http://localhost:13378`                           |
| `API key`         | -        | An API key or personal token, see below                 |
| `API key command` | -        | A command that prints the key, keeps it off the disk    |
| `Player command`  | `cvlc`   | The player to start, flags allowed                      |

The plugin only ever talks to that one server, reads your libraries and hands
their audio files to the player.

### The API key

Audiobookshelf calls it an API token. An administrator creates keys in its web
UI under **Settings > API Keys**; a personal token from your own account works
too. Either way the plugin acts as the user the key belongs to.

A key typed into the `API key` field is kept by Albert in plaintext. To keep it
off the disk entirely, leave that field empty and put a command here instead:

```
pass show audiobookshelf
```

The command is run through the shell when the key is first needed, and whatever it
prints on stdout is used as the key. It **wins over** the `API key` field, so the
two can both be set and the plaintext one is simply ignored. The key it prints is
held in memory only and is never written back to the config; it is fetched once
per session (a failure is not remembered, so unlocking your password manager and
trying again just works).

A command that fails, hangs for more than 30 seconds, or prints nothing leaves the
row as an error you can retry.

## Notes

- Only `book` libraries are searched; a podcast library on the same server is
  left alone.
- The library list is cached for a few minutes and a search for a minute, so
  typing does not turn into a request per keystroke. Changing the settings drops
  both caches.
- A reverse-proxy prefix is kept on the API and web UI routes alike, e.g.
  `https://audio.example.com/abs`.
- `requests` is the only library dependency; the player command is a binary
  dependency (`cvlc` by default).

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
