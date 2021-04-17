# tldr_pages - Albert plugin

## Description

View [TL;DR](https://github.com/tldr-pages/tldr) pages in Albert. Pages are by
default cached under `~/.cache/albert/tldr_pages/tldr` By default it uses the
English version of the tldr pages. If that's not what you want alter the
following line in `__init__.py` appropriately and restart Albert.

```python
pages_root = tldr_root / "pages"
```

## Demo

![demo_gif](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/tldr.gif)

## Manual installation instructions

Requirements:

- Albert - [Installation instructions](https://albertlauncher.github.io/docs/installing/)
    - Albert Python Interface: ``v0.4``

- Python version >= 3.5

- git for downloading and managing the tldr pages

## Self Promotion

If you find this tool useful, please [star it on Github](https://github.com/bergercookie/awesome-albert-plugins)

## TODO List

See [ISSUES list](https://github.com/bergercookie/awesome-albert-plugins/issues) for the things that
I'm currently either working on or interested in implementing in the near
future. In case there's something you are interesting in working on, don't
hesitate to either ask for clarifications or just do it and directly make a PR.
