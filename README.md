# Awesome Albert Plugins

<a href="https://www.codacy.com/manual/bergercookie/awesome-albert-plugins">
<img src="https://api.codacy.com/project/badge/Grade/dbefc49bb5f446488da561c7497bb821"/></a>
<a href=https://github.com/bergercookie/awesome-albert-plugins/blob/master/LICENSE" alt="LICENCE">
<img src="https://img.shields.io/github/license/bergercookie/awesome-albert-plugins.svg" /></a>
<a href="https://github.com/psf/black">
<img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>
<a href=" https://github.com/bergercookie/awesome-albert-plugins/issues">
<img src="https://img.shields.io/github/issues/bergercookie/awesome-albert-plugins/awesome-albert-plugins.svg"></a>

## Description

This is a collection of plugins and themes for the
[Albert](https://albertlauncher.github.io/) launcher.

### Plugins

Currently the list of plugins includes:

* Jira - Issue Tracking
* Zoopla - Search Property to Buy, Rent, House Prices
* Xkcd - Fetch xkcd comics like a boss
* Taskwarrior - Interact with Taskwarrior
* Remmina - Search and start remmina connections easily
* Google Maps - Fetch instructions from/to a specific place
* Suggestions-enabled search using [googler](https://github.com/jarun/googler) on a variety of websites. For example:
  * Google
  * Amazon
  * Youtube
  * Github
  * Ebay
  * IMDB
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
| ![](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/albert-suggestions-demo3.gif) | |

## Motivation

It's really so easy writing plugins and automating parts of your workflow using Albert and its python extensions. That's the very reason I started writing them.

## Manual installation instructions

Requirements:

- Albert - [Installation instructions](https://albertlauncher.github.io/docs/installing/)
    - Albert Python Interface: ``v0.2``

Download and run the ``install-plugin.sh`` script or run the following to do
that automatically:

```sh
curl https://raw.githubusercontent.com/bergercookie/awesome-albert-plugins/master/install-plugin.sh | bash
```

This will clone the current repo and then will delegate execution to the
`install-plugin.sh` of each one of the plugins to be installed

## Self Promotion

If you find this tool useful, please [star it on
Github](https://github.com/bergercookie/awesome-albert-plugins)

## TODO List

See [ISSUES list](https://github.com/bergercookie/awesome-albert-plugins/issues) for the things
that I'm currently either working on or interested in implementing in the near
future. In case there's something you are interesting in working on, don't
hesitate to either ask for clarifications or just do it and directly make a PR.

### Plugin ideas

* :construction: Giphy - https://github.com/Giphy/giphy-python-client
* :construction: Abbreviations/Slang lookup
* :construction: Linux directory listing
