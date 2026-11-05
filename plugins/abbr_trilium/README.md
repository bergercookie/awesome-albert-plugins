# abbr_trilium - Albert plugin

## Description

Look up abbreviations stored in a [Trilium](https://triliumnotes.org/) note, and
append new ones to the same note without leaving Albert.

This is the Trilium-backed version of the [abbreviations](../abbr) plugin. Instead
of a plain file on disk, the abbreviation lines live in a note that you choose.
The plugin talks to your Trilium server through its
[ETAPI](https://docs.triliumnotes.org/user-guide/advanced-usage/etapi).

Each line in the note is read as `* abbreviation: description`. Multiple lines
may use the same abbreviation; searching for it shows all of them.

## Usage

Type `abt ` followed by the abbreviation or part of its description. The first
action opens a Google search for the abbreviation, and the other actions copy
the abbreviation or its description.

Type `abt new <abbreviation> <description>` and press <kbd>ENTER</kbd> to append
the abbreviation to the configured note.

## Configuration

Open the plugin's configuration window from the Albert settings and fill in:

| Setting                  | Meaning                                                                 |
| ------------------------ | ----------------------------------------------------------------------- |
| `Trilium URL`            | Base URL of your Trilium server, e.g. `https://trilium.example.com`     |
| `ETAPI token`            | Token created in Trilium under Options > ETAPI                          |
| `Abbreviations note ID`  | ID of the note that holds the abbreviations                             |
| `Verify TLS certificate` | Turn off only if your server uses a self-signed certificate             |

The note ID is the part after the `#` in the note's URL. A Text note is written
as HTML; a Code note with a plain-text MIME type is written as-is.

The plugin only talks to the Trilium server configured above. The note content is
cached in memory for 30 seconds, and saving a new abbreviation clears that cache.

## Installation instructions

* Install the `fuzzywuzzy` and `requests` Python modules.

For more refer to the parent project: [Awesome albert plugins](https://github.com/bergercookie/awesome-albert-plugins)

## Self Promotion

If you find this tool useful, please [star it on Github](https://github.com/bergercookie/awesome-albert-plugins)

## TODO List

See [ISSUES list](https://github.com/bergercookie/awesome-albert-plugins/issues) for the things that
I'm currently either working on or interested in implementing in the near
future. In case there's something you are interesting in working on, don't
hesitate to either ask for clarifications or just do it and directly make a PR.
