# Awesome Albert Plugins

<a href="https://travis-ci.com/bergercookie/awesome-albert-plugins" alt="Build Status">
<img src="https://travis-ci.com/bergercookie/awesome-albert-plugins.svg?branch=master"></a>
<a href="https://www.codacy.com/manual/bergercookie/awesome-albert-plugins">
<img src="https://api.codacy.com/project/badge/Grade/dbefc49bb5f446488da561c7497bb821"/></a>
<a href=https://github.com/bergercookie/awesome-albert-plugins/blob/master/LICENSE alt="LICENCE">
<img src="https://img.shields.io/github/license/bergercookie/awesome-albert-plugins.svg" /></a>
<a href="https://github.com/psf/black">
<img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>

## Description

**NOTE** This branch corresponds to the Albert Python API prior to the v0.5
changes - i.e., the plugins won't work with Albert >= 0.18. We're in the process
of moving each of the plugins to the new API. For this work and to see the
plugins that have currently been migrated, head to the [python_api_v0.5
branch](https://github.com/bergercookie/awesome-albert-plugins/tree/python_api_v0.5)

This is a collection of plugins and themes for the
[Albert](https://albertlauncher.github.io/) launcher.

## Demos

| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/emoji/misc/demo0.png) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/emoji/misc/demo1.png) |
| :----------------------------------------------------------------------------------------------------| :--------------------------------------------------------------------------------------------------: |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/contacts/misc/demo0.png) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/contacts/misc/demo1.png) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/bluetooth/misc/demo0.png) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/bluetooth/misc/demo1.png) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/anki/misc/anki.gif) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/anki/misc/anki0.png) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/albert-suggestions-demo.gif) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/albert-suggestions-demo2.gif) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/errno_lookup.png) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/ipshow.png) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/pulse_control/misc/pulse-demo1.png) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/pulse_control/misc/pulse-demo2.png) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/albert-suggestions-demo3.gif) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/colors/misc/colors1.png) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/timezones/misc/demo1.png) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/killproc/misc/demo0.png) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/words/misc/demo0.png) | ![](https://raw.githubusercontent.com/bergercookie/awesome-albert-plugins/master/misc/tldr.gif) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/harakiri/misc/demo0.png) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/image_search/misc/demo0.png) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/meme_generator/misc/demo.gif) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/clock/misc/clock.png) |

## Plugins

Currently the list of plugins includes:

- [Anki](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/anki) - 📇 Generate flashcards for [Anki](https://apps.ankiweb.net/)
- [Bluetooth](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/bluetooth) - 🦷 Manage bluetooth devices
- [Clock](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/clock) - ⏰ Create countdown and stopwatch timers
- [Contacts](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/contacts) - 📕 View your contacts and copy emails/telephones, etc.
- [Colors](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/colors) - 🎨 Color lookup using RGB, hex notation or color name
- [Emoji](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/emoji) - 🎉 Search for and copy emojis to clipboard
- [Errno](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/errno_lookup) - ❗Lookup and get information on Linux error codes
- [Google Translate](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/google_translate) - 🉑 Reimplementation of [this](https://github.com/dshoreman/albert-translate) plugin with persistent storage of previous searches, no need for API key and smart HTTP querying to avoid blocking from Google.
- [Harakiri](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/harakiri) - 📫 Create temporary email addresses at [harakirimail.com](https://harakirimail.com/)
- [IP show](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/ipshow) - 🌐 Display information about your network interfaces and public IPs
- [Image Search](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/image_search) - 📷 Search the web for images, download them and/or copy them to clipboard
- [Jira](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/jira) - 📝 View and edit your [Jira](https://www.atlassian.com/software/jira) tickets from Albert
- [Killproc](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/killproc) - ☠️ Kill processes based on fuzzy-search
- [Meme Generator](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/meme_generator) - 😸 Generate memes and copy them to clipboard
- [Pass TOTP](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/pass_totp_cli) - 🔢 Generate 2FA codes with [Pass](https://www.passwordstore.org/) and [totp](https://pypi.org/project/totp/)
- [Pass_rlded](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/pass_rlded) - 🔒 UNIX Password Manager interaction with fuzzy-search capabilities
- [Pulse Control](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/pulse_control) - 🎤 Enable/disable sources and sinks from Pulse Control
- [Remmina](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/remmina) - 🖥️ Start a [Remmina](https://remmina.org/) VNC/SFTP connection
- [Saxophone](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/saxophone) - 🎷 Play your favorite internet radio stations / streams
- [Scratchpad](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/scratchpad) - 📝 Take quick notes into a single textfile
- [Taskwarrior](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/taskwarrior) - 🪖 Interact with the [Taskwarrior](https://taskwarrior.org/) task manager
- [Template Albert Plugin](https://github.com/bergercookie/awesome-albert-plugins) - 🛠️ Template [cookiecutter](https://github.com/cookiecutter/cookiecutter) for creating new Albert plugins
- [Timezones](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/timezones) - 🌏 Lookup timezone information
- [Tldr Lookup](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/tldr_pages) - Lookup [tldr](https://github.com/tldr-pages/tldr) pages and commands
- [URL Error Lookup](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/url_lookup) - 🔗 Lookup URL error codes
- [Words](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/words) - 🔤 Lookup a word definition, synonyms and antonyms
- [Xkcd](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/xkcd) - 📓 List and fuzzy-search the latest [xkcd](https://fr.wikipedia.org/wiki/Xkcd) comics
- [`DuckDuckGo`-based autocompletion search](https://github.com/bergercookie/awesome-albert-plugins#ddgr-based-plugins) - 🦆 for searching on duckduckgo.com, github.com,
  stackoverflow, amazon, and a variety of other websites using [ddgr](https://github.com/jarun/ddgr)

  - Suggestions-enabled search using [ddgr](https://github.com/jarun/ddgr) on
    a variety of websites. For example:

    - DuckDuckGo
    - Amazon
    - Youtube
    - Github
    - Ebay
    - Imdb
    - Urban dictionary: Word/Slang definitions lookup
    - Python, OpenCV, Dlib, C++ documentation lookup
    - ...
    - :warning: To avoid getting blocked, a search request is only sent when the
        text ends with a dot `"."`.

    - Install `google-chrome` or `chromium-browser` to add an "Open in incognito
      mode" option
    - See the [`ddgr`-specific section](#ddgr-based-plugins) for more

- Improved implementations of the original 🍅 `Pomodoro` plugin

Plugins have been tested with the Albert python `v0.4` interface. If you're
looking for a version that works with earlier versions of the plugin, see the
`prior-to-v0.4` branch. I'm using Python `3.6.8`.

### Themes

- [Mozhi](https://github.com/Hsins/Albert-Mozhi) - A flat, transparent and dark
  theme for Albert.
  ([DEMO](https://github.com/Hsins/Albert-Mozhi/blob/master/demo/demo.gif))

## Motivation

It's really so easy writing plugins and automating parts of your workflow using
Albert and its python extensions. That's the very reason I started writing them.

## Installation

Requirements:

- Linux (tested on Ubuntu)
- Albert - [Installation instructions](https://albertlauncher.github.io/docs/installing/)
  - Albert Python Interface: `v0.4`

Clone this repository under your local Albert python plugins directory. By
default the that is: `~/.local/share/albert/org.albert.extension.python/modules`.

Then go to the Albert settings and enable the plugins that you are interested in
using. Beware that you may need to install some more dependencies depending on
the plugins you use. These dependencies will probably be pointed out either when
you enable, or when you run the plugin for the first time. Refer to the
directory of the corresponding plugin for more details.

### `ddgr`-based plugins

The search plugins that use `ddgr` have not been committed to this repo. You
can generate them offline using the `create_ddgr_plugins.py` script provided.
Make sure you have Python >= 3.6 installed:

```
pip3 install --user --upgrade secrets requests ddgr cookiecutter
./create_ddgr_plugins.py
```

This will generate an Albert plugin for each one of the search engines specified
in `create_ddgr_plugins.py`. Adjust the latter as required if you want to
add more or remove plugins.

```py
generate_plugins_only_for = [
    "alternativeto",
    "amazon",
    "askubuntu",
    "aur.archlinux",
    ...
    ]
```

### I don't want to setup all the plugins, just a few

Very well, then after cloning this repo, just symlink or copy the plugin of
choice under your local python plugins directory. For example for the `jira`
plugin:

```sh
cp -r plugins/jira ~/.local/share/albert/org.albert.extension.python/modules/jira
```

After that, enable the plugin from the Albert settings.

## Self Promotion

If you find this tool useful, please [star it on
Github](https://github.com/bergercookie/awesome-albert-plugins)

## TODO List

See [ISSUES list](https://github.com/bergercookie/awesome-albert-plugins/issues)
for the things that I'm currently either working on or interested in
implementing in the near future. In case there's something you are interesting
in working on, don't hesitate to either ask for clarifications or just do it and
directly make a PR.

### Ideas List (feel free to implement)

- :construction: Giphy - https://github.com/Giphy/giphy-python-client
- :construction: Devdocs.io/Zeal/Dash search
- :construction: Manage your VPN connections - Frontend to `WireGuard`?
- :construction: Spotify mini player - similar to [this](https://github.com/vdesabou/alfred-spotify-mini-player)
- :construction: Movie search and ratings - be able to sign in to various
  services and (e.g., imdb) and submit a rating for a movie
- :construction: An alternative to [Alfred's pkgman](https://github.com/willfarrell/alfred-pkgman-workflow)
- :construction: Vagrant start/stop boxes - see [this](https://github.com/m1keil/alfred-vagrant-workflow)
- :construction: Assembly instructions lookup - use [this](https://github.com/asmjit/asmdb)
  - Use ddgr asynchronously to get links to pages: `adcs site:developer.arm.com`
