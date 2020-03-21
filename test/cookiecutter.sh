#!/usr/bin/env bash
set -x
THIS_DIR=`dirname ${BASH_SOURCE[0]}`/
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
(
cd "$THIS_DIR"
cookiecutter ../cookiecutter/ -o ../plugins/ --no-input
test -d ../plugins/albert_plugin
)

