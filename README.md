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

This is a collection of plugins and themes for the
[Albert](https://albertlauncher.github.io/) launcher.

### Plugins

Currently the list of plugins includes:

* Jira - Issue Tracking
* Listen to internet Radio Streams - Saxophone Plugin
* Zoopla - Search Property to Buy, Rent, House Prices
* Xkcd - Fetch xkcd comics like a boss
* Taskwarrior - Interact with Taskwarrior
* Remmina - Search and start remmina connections easily
* Google Maps - Fetch instructions from/to a specific place
* Google Translate - Improved version of original albert plugin - avoids
  occasional IP blocking by Google
* [TL;DR](https://github.com/tldr-pages/tldr) pages lookup - [demo](https://raw.githubusercontent.com/bergercookie/awesome-albert-plugins/master/misc/tldr.gif)
* Get 2FA codes using [totp-cli](https://github.com/bergercookie/totp-cli)
* Lookup HTTP URL status codes
* Lookup errno status codes
* Show Internal, External IPs, Default Gateways
* Suggestions-enabled search using [googler](https://github.com/jarun/googler) on a variety of websites. For example: Google
  * Amazon
  * Youtube
  * Github
  * Ebay
  * Imdb
  * Urban dictionary: Word/Slang definitions lookup
  * Python, OpenCV, Dlib, C++ documentation lookup
  * ...
  * :warning: To avoid getting blocked by Google, a search request is only sent
      when there is a 0.3 seconds difference between keystrokes. Thus, it's
      common when you actually want to send a request to wait a bit and then
      append a space character at the end of the query.


Here's a view of the albert prompt after having enabled several of the
search-suggestion plugins:

![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/search_plugins.png)

Plugins have been tested with the Albert python `v0.3` interface but there's no
reason they shouldn't work with the `v0.2` as well (if they don't raise an
issue). I'm using Python `3.6.8` (again, raise an issue if it doesn't work in
your case).

### Themes

* [Mozhi](https://github.com/Hsins/Albert-Mozhi) - A flat, transparent and dark theme for Albert (A fast and flexible keyboard launcher for Linux). ([DEMO](https://github.com/Hsins/Albert-Mozhi/blob/master/demo/demo.gif))

## Demos

| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/jira/misc/demo-basic.png) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/taskwarrior/misc/demo.gif) |
|:---:|:---:|
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/zoopla/misc/demo.gif) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/xkcd/misc/demo.gif) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/albert-suggestions-demo.gif) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/albert-suggestions-demo2.gif) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/errno_lookup.png) | ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/ipshow.png) |
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/albert-suggestions-demo3.gif) | |

## Motivation

It's really so easy writing plugins and automating parts of your workflow using
Albert and its python extensions. That's the very reason I started writing them.

## Installation

Requirements:

- Linux (tested on Ubuntu)
- Albert - [Installation instructions](https://albertlauncher.github.io/docs/installing/)
    - Albert Python Interface: ``v0.2``

Clone this repository under your local Albert python plugins directory. By
default the that is: `~/.local/share/albert/org.albert.extension.python/modules`.

Then go to the Albert settings and enable the plugins that you are interested in
using. Beware that you may need to install some more dependencies depending on
the plugins you use. These dependencies will probably be pointed out either when
you enable, or when you run the plugin for the first time. Refer to the
directory of the corresponding plugin for more details.

### `Googler`-based plugins

The search plugins that use googler have not been committed to this repo. You
can generate them offline using the `create_googler_plugins.py` script provided.
Make sure you have Python >= 3.6 installed:

```
pip3 install --user --upgrade secrets requests googler cookiecutter
./create_googler_plugins.py
```

This will generate an Albert plugin for each one of the search engines specified
in `create_googler_plugins.py`. Adjust the latter as required if you want to
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
```
cp -r plugins/jira ~/.local/share/albert/org.albert.extension.python/modules/jira
```
After that, enable the plugin from the Albert settings.

## Self Promotion

If you find this tool useful, please [star it on
Github](https://github.com/bergercookie/awesome-albert-plugins)

## TODO List

See [ISSUES list](https://github.com/bergercookie/awesome-albert-plugins/issues) for the things
that I'm currently either working on or interested in implementing in the near
future. In case there's something you are interesting in working on, don't
hesitate to either ask for clarifications or just do it and directly make a PR.

### Plugin ideas

* :construction: Online radio player - use https://github.com/coderholic/pyradio
* :construction: [Radio Paradise player](https://radioparadise.com/player)
* :construction: Giphy - https://github.com/Giphy/giphy-python-client
* :construction: Filesystem directory listing
* :construction: devdocs.io search
