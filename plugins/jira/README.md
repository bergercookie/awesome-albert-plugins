# jira - Albert plugin

<a href="https://www.codacy.com/manual/bergercookie/jira-albert-plugin">
<img src="https://api.codacy.com/project/badge/Grade/02097c818d9b43ecb35badfb0e4befd7"/></a>
<a href=https://github.com/bergercookie/jira-albert-plugin/blob/master/LICENSE" alt="LICENCE">
<img src="https://img.shields.io/github/license/bergercookie/jira-albert-plugin.svg" /></a>
<a href="https://github.com/psf/black">
<img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>
<a href=" https://github.com/bergercookie/jira-albert-plugin/issues">
<img src="https://img.shields.io/github/issues/bergercookie/jira-albert-plugin/jira.svg"></a>

## Demo

| | |
|:-------------------------:|:-------------------------:|
|<img src="https://raw.githubusercontent.com/bergercookie/jira-albert-plugin/master/misc/demo-setup0.png"> | <img src="https://raw.githubusercontent.com/bergercookie/jira-albert-plugin/master/misc/demo-setup1.png"> |
 <img src="https://raw.githubusercontent.com/bergercookie/jira-albert-plugin/master/misc/demo-setup2.png"> | <img src="https://raw.githubusercontent.com/bergercookie/jira-albert-plugin/master/misc/demo-basic.png"> Basic usage |
 <img src="https://raw.githubusercontent.com/bergercookie/jira-albert-plugin/master/misc/demo-fuzzy-search-title.png"> Fuzzy search | <img src="https://raw.githubusercontent.com/bergercookie/jira-albert-plugin/master/misc/demo-options.png"> Options for issue |

## Description

`jira-albert-plugin` allows you to interact with your jira server via the albert
launcher.

On first run, you'll be guided through a series of setup steps:

- user to use, e.g., youremailforjira@gmail.com
- server to connect to e.g., https://an-example-jira-server.atlassian.net

You also have to create an API key: https://id.atlassian.com/manage/api-tokens

- To make sure the API key is stored safely, the plugin expects to find it
  gpg-encrypted using your default gpg-id under the following path:
  ```
  ~/.password-store/jira-albert-plugin/api-key.gpg
  ```

  You can do that either manually `gpg --encrypt... -o ...` or consider using
  [Pass](https://www.passwordstore.org/), the UNIX password manager.

After having setup the plugin, on trigger the plugin will fetch all the issues
assigned to the current user. You also get an option of creating a new issue
from scratch.

By pressing on one of the issues you'll be redirected to the its jira page.  On
`[ALT]` you have options to copy the jira URL, or to transition it, e.g.,
`Backlog` -> `In Progress` or `Select From Development` -> `Done`.

Issues are sorted and are colored according to their priority

You can narrow down the search to the most relevant items by typing additional
letters/words. The plugin uses fuzzy search to find the most relevant issues to
show.

Additional information:

* To reset/use a different account, delete the config location (by default
    `~/.config/albert/jira`) and substitute the gpg-encrypted api-key.

## Motivation

Navigating to JIRA, searching for your ticket of choice and changing its status
via the web interface is cumbersome. This plugin lets you do that far more
easily and in addition, without leaving the keyboard for a second.

## Manual installation instructions

Requirements:

- Albert - [Installation instructions](https://albertlauncher.github.io/docs/installing/)
    - Albert Python Interface: ``v0.2``

- Python version >= 3.5


Download and run the ``install-plugin.sh`` script or run the following to do
that automatically:

```sh
curl https://raw.githubusercontent.com/bergercookie/jira-albert-plugin/master/install-plugin.sh | bash
```

## Self Promotion

If you find this tool useful, please [star it on
Github](https://github.com/bergercookie/jira-albert-plugin)

## TODO List

See [ISSUES list](https://github.com/bergercookie/jira-albert-plugin/issues) for the things
that I'm currently either working on or interested in implementing in the near
future. In case there's something you are interesting in working on, don't
hesitate to either ask for clarifications or just do it and directly make a PR.
