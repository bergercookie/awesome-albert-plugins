# emoji - Albert plugin

## Description

The `emojis` Albert plugin allows you to quickly lookup and copy various emojis
to your clipboard

Thanks to @hugovk for providing the
[em-keyboard](https://github.com/hugovk/em-keyboard) tool. I'm using that for
the list of emojis as well as their labels.

This plugin supports fuzzy search on both the vanilla emojis of `em-keyboard` as
well as custom emojis in `JSON` format added under `~/.emojis.json`.

## Demo

Without any keyword it shows you your most recently used emojis on top:

![recently_used](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/emoji/misc/demo0.png)

On additional key presses it allows for fuzzy search on the labels of each emoji:

| ![demo1](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/emoji/misc/demo1.png) | ![demo2](https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/emoji/misc/demo2.png) |
| :----------------------------------------------------------------------------------------------------------------: | :----------------------------------------------------------------------------------------------------------------: |

## Installation instructions

### Prerequisites

#### Exec prerequisites

- `xclip`: you must have installed xclip; ensure that xlip path is in PATH environment variable.

##### Python prerequisites

- `em-keyboard`: [link to repository](https://github.com/hugovk/em-keyboard)
- `fuzzywuzzy`
  
Install all dependencies via `pip3`:

```bash
pip3 install em-keyboard fuzzywuzzy
```

Refer to the parent project for more information: [Awesome albert plugins](https://github.com/bergercookie/awesome-albert-plugins)

## Self Promotion

If you find this tool useful, please [star it on Github](https://github.com/bergercookie/awesome-albert-plugins)

## TODO List

See [ISSUES list](https://github.com/bergercookie/awesome-albert-plugins/issues) for the things that
I'm currently either working on or interested in implementing in the near
future. In case there's something you are interesting in working on, don't
hesitate to either ask for clarifications or just do it and directly make a PR.
