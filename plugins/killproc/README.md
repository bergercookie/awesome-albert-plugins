# killproc - Albert plugin

## Description

Kill process(es) from Albert

- Search for a process using fuzzy search
- A few different modes to choose from:
  - Terminate/Kill the selected process
  - Terminate/Kill processes with a matching name
  - Terminate/Kill processes based on the provided glob search. For example
    `sle*` will kill all the processes that start with `sle` regardless of the
    currently selected process

## Demo

![demo_gif](https://github.com/bergercookie/awesome-albert-plugins/misc/demo.gif)

## Installation instructions

The following `import` statements should succeed:

```python
import psutil
from fuzzywuzzy import process
from gi.repository import GdkPixbuf, Notify
```

Refer to the parent project for more: [Awesome albert plugins](https://github.com/bergercookie/awesome-albert-plugins)

## Self Promotion

If you find this tool useful, please [star it on Github](https://github.com/bergercookie/awesome-albert-plugins)

## TODO List

See [ISSUES list](https://github.com/bergercookie/awesome-albert-plugins/issues) for the things that
I'm currently either working on or interested in implementing in the near
future. In case there's something you are interesting in working on, don't
hesitate to either ask for clarifications or just do it and directly make a PR.
