# Search Plugin Template for {{ cookiecutter.plugin_name }}

Current plugin was created using
[search_template](https://github.com/bergercookie/awesome-albert-plugins/tree/master/plugins/search_template/%7B%7B%20cookiecutter.plugin_name%20%7D%7D).

It uses [ddgr](https://github.com/jarun/ddgr) under the hoodto offer suggestions /
search results for {{ cookiecutter.plugin_name }} and display them in Albert.

# Installation instructions

Install `ddgr` either from source or from a package. You can find more
instructions [here](https://github.com/jarun/ddgr#installation=).

On Ubuntu 20.04 the following lines should be enough:

```sh
sudo apt install xclip
pip3 install --user --upgrade ddgr
```

Copy this directory to your local Albert plugins directory. By default, that is
under `~/.local/share/albert/org.albert.extension.python/modules`.
