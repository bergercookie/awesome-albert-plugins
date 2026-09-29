# ipshow - Albert plugin

## Description

Show the IPs of the machine at hand. Pretty much like `ip a s` or `ifconfig`.

Each interface is listed with an icon matching its transport type - WiFi,
ethernet, bridge or loopback - falling back to the generic plugin icon for
interface types that can't be identified (tunnels, veth pairs, ...). The type
is read from `/sys/class/net` where available, otherwise inferred from the
interface name.

## Credits

The `wifi.svg`, `ethernet.svg`, `bridge.svg` and `loopback.svg` icons are
derived from [Font Awesome Free 6](https://fontawesome.com) (icons licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), Copyright Fonticons,
Inc.), recoloured to a theme-neutral grey.

## Demo

![demo](https://github.com/bergercookie/awesome-albert-plugins/blob/master/misc/ipshow.png)

## Installation instructions

Refer to the parent project: [Awesome albert plugins](https://github.com/bergercookie/awesome-albert-plugins)

## Self Promotion

If you find this tool useful, please [star it on Github](https://github.com/bergercookie/awesome-albert-plugins)

## TODO List

See [ISSUES list](https://github.com/bergercookie/awesome-albert-plugins/issues) for the things that
I'm currently either working on or interested in implementing in the near
future. In case there's something you are interesting in working on, don't
hesitate to either ask for clarifications or just do it and directly make a PR.
