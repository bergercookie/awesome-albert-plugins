# {{ cookiecutter.plugin_name }} - Albert plugin

## TODO Plugin is not ready yet - README info may be inaccurate
## TODO - Register on codacy - replace HTML link
## TODO - Add demo gif/pictures

<a href="https://www.codacy.com/manual/bergercookie/{{ cookiecutter.plugin_name }}">
<img src="https://api.codacy.com/project/badge/Grade/126122966e844bed8e61e7cfbf7023c3"/></a>
<a href={{ cookiecutter.repo_base_url }}/{{ cookiecutter.repo_name }}/blob/master/LICENSE" alt="LICENCE">
<img src="https://img.shields.io/github/license/bergercookie/{{ cookiecutter.repo_name }}.svg" /></a>
<a href="https://github.com/psf/black">
<img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>
<a href=" {{ cookiecutter.repo_base_url }}/{{ cookiecutter.repo_name }}/issues">
<img src="https://img.shields.io/github/issues/bergercookie/{{ cookiecutter.repo_name }}/{{ cookiecutter.plugin_name }}.svg"></a>

## Description

## Demo

![demo_gif]({{ cookiecutter.repo_base_url }}/{{ cookiecutter.repo_name }}/blob/master/misc/demo.gif)

## Motivation

## Manual installation instructions

Requirements:

- Albert - [Installation instructions](https://albertlauncher.github.io/docs/installing/)
    - Albert Python Interface: ``{{ cookiecutter.albert_plugin_interface }}``

- Python version >= 3.5

Download and run the ``install-plugin.sh`` script or run the following to do
that automatically:

```sh
curl https://raw.githubusercontent.com/bergercookie/{{ cookiecutter.repo_name }}/master/install-plugin.sh | bash
```

## Self Promotion

If you find this tool useful, please [star it on
Github]({{ cookiecutter.repo_base_url }}/{{ cookiecutter.repo_name }})

## TODO List

See [ISSUES list]({{ cookiecutter.repo_base_url }}/{{ cookiecutter.repo_name }}/issues) for the things
that I'm currently either working on or interested in implementing in the near
future. In case there's something you are interesting in working on, don't
hesitate to either ask for clarifications or just do it and directly make a PR.
