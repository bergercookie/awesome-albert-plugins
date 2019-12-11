# gmaps-cli: Interact with Google Maps via Selenium

<a href="https://github.com/bergercookie/gmaps-cli/actions" alt="Github Actions">
<img src="https://github.com/bergercookie/python_package_cookiecutter/workflows/CI/badge.svg" /></a>
<a href="https://github.com/bergercookie/gmaps-cli/blob/master/LICENSE" alt="LICENCE">
<img src="https://img.shields.io/github/license/bergercookie/gmaps-cli.svg" /></a>
<a href="https://github.com/psf/black">
<img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>
<a href=" https://github.com/bergercookie/gmaps-cli/issues">
<img src="https://img.shields.io/github/issues/bergercookie/gmaps-cli/gmaps-cli.svg"></a>

`gmaps-cli` is a command-line tool that allows you to interact with Google Maps
using selenium. Currently it supports the following functionalities via the
corresponding executable subcommands:

* `route`: Get a URL to a Google Maps page for the route and means of your choice
  * `gmaps-cli route -s London -d Birmingham -t walk`

    `-> "<computed-google-maps-url>"`
  * `gmaps-cli route --source London --destination Birmingham --travel-by transit`

    `-> "<computed-google-maps-url>"`
  * `gmaps-cli route -s London -d Birmingham -t walk --open`

    `-> Open page on default browser`
* :construction: `autocomplete-place`: Get the Google Maps autocompletion suggestions - same as entering a string in the places field
  * `gmaps-cli autocomplete-place lond`

    ```sh
    -> London
    -> London Borough of Wandsworth
    -> London Eye
    -> London Borough of Lambeth
    ```
