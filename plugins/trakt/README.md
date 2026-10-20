# Trakt - Albert plugin

## Description

Search movies and shows on [Trakt](https://trakt.tv) and rate them, without
leaving the keyboard.

Type `trakt ` with nothing after it and you get the plugin's status: whether it
is signed in, and a one-keypress sign-in when it is not. Anything you type
instead is searched on trakt.tv, and <kbd>ENTER</kbd> on a hit opens its page in
the browser. `rate <1-10> <title>` searches the same way, but
<kbd>ENTER</kbd> rates the hit instead - the only thing that needs a signed-in
session.

## Usage

### Opening a title

`trakt fight club` searches Trakt's movie and show catalogue. Every hit is a
row with its kind and year; <kbd>ENTER</kbd> opens its page on trakt.tv in the
browser. A single character is not searched - it would match most of the
catalogue - only a hint that two are needed.

### Rating a title

`trakt rate 8 fight club` searches exactly the same way, but <kbd>ENTER</kbd>
rates the first hit 8 out of 10. Trakt accepts whole and half stars, 1 to 10:

```
trakt rate 10 breaking bad
trakt rate 8.5 severance
```

The rating is typed into the query rather than picked from a menu, because a
launcher has no way to ask a follow-up question. A leading `rate` word is always
read as this grammar, so a hypothetical title called "Rate My Trainer" needs to
be searched without the first word or opened from trakt.tv directly.

Rating requires a signed-in session; a `rate` query while signed out offers the
sign-in instead of the hits.

### Signing in

Clear the query and press <kbd>ENTER</kbd> on **Sign in to Trakt**. The plugin
asks Trakt for a device code, puts the code and the page to enter it on in a
notification, and shows them as the first row until you have finished. Open
<https://auth.trakt.tv/activate>, type the code, approve - and the plugin stores
the session and greets you by name the next time you clear the query.

A signed-in row offers your Trakt profile and **Sign out of Trakt**.

## Configuration

Open the plugin's configuration window from the Albert settings and fill in:

| Setting         | Meaning                                                     |
| --------------- | ----------------------------------------------------------- |
| `Client ID`     | The Client ID of your Trakt application, from trakt.tv       |
| `Client Secret` | The Client Secret of the same application                    |

Both come from one application you register yourself at
<https://trakt.tv/oauth/applications>; the redirect URI can be left empty and
the plugin never uses it - it signs in with the device code flow instead.

The Client ID alone is enough to search and open titles. The Client Secret is
needed only to sign in and rate, so the plugin is useful before you paste it.

## Notes

- The plugin only ever talks to `api.trakt.tv` (the API) and `auth.trakt.tv`
  (signing in and refreshing the session). Opening a title goes to trakt.tv in
  your browser, like any other link.
- Everything stored - the Client ID and Secret, and the access and refresh
  tokens a sign-in writes - sits in Albert's config in plaintext. Trakt tokens
  are the only way to rate as yourself; treat the config file like the tokens.
- Access tokens last about a week. The plugin refreshes them once, silently,
  the first time Trakt reports one as expired; a refresh that fails signs you
  out and asks you to sign in again.
- Search results are cached in memory for a minute per term, so backspacing
  over a word does not re-query Trakt. Changing the settings clears the cache.
- The plugin reads and writes nothing on Trakt but your ratings.

## Installation instructions

Refer to the parent project: [Awesome albert plugins](https://github.com/bergercookie/awesome-albert-plugins)

## Self Promotion

If you find this tool useful, please [star it on Github](https://github.com/bergercookie/awesome-albert-plugins)

## TODO List

See [ISSUES list](https://github.com/bergercookie/awesome-albert-plugins/issues)
for the things that I'm currently either working on or interested in
implementing in the near future. In case there's something you're interested
in working on, don't hesitate to either ask for clarifications or just do it and
directly make a PR.
