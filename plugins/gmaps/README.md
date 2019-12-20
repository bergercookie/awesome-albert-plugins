# gmaps - Albert plugin

## Description

Specify and open a route in Google Maps.

Current plugin, although working is in kind of a rough state. It uses Selenium
on the background to simulate the user presses, compute the corresponding Google
Maps URL and return it. After that the URL is opened with the default user
browser.

## Manual installation instructions

Requirements:

- Albert - [Installation instructions](https://albertlauncher.github.io/docs/installing/)
    - Albert Python Interface: ``v0.2``

- Python version >= 3.5

Download and run the ``install-plugin.sh`` script or run the following to do
that automatically:

```sh
curl https://raw.githubusercontent.com/bergercookie/awesome-albert-plugins/master/plugins/gmaps/install-plugin.sh | bash
```

## Self Promotion

If you find this tool useful, please [star it on Github](https://github.com/bergercookie/awesome-albert-plugins)

## TODO List

See [ISSUES list](https://github.com/bergercookie/awesome-albert-plugins/issues) for the things that
I'm currently either working on or interested in implementing in the near
future. In case there's something you are interesting in working on, don't
hesitate to either ask for clarifications or just do it and directly make a PR.
