set -x
ROOT=`dirname ${BASH_SOURCE[0]}`/..
pip3 install --user --upgrade secrets requests googler cookiecutter
"$ROOT"/create_googler_plugins.py

test -d "$ROOT/plugins/search_wikipedia"
test -d "$ROOT/plugins/search_amazon"
