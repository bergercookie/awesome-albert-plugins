set -x
ROOT=`dirname ${BASH_SOURCE[0]}`/..
(
cd "$ROOT"
cookiecutter cookiecutter/ -o plugins/ --no-input
test -d plugins/albert_plugin
)

