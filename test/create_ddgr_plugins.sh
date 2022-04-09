#!/usr/bin/env bash
set -ex
ROOT=`dirname ${BASH_SOURCE[0]}`/..
ls -lart .
ls -lart $ROOT
ls -lart $ROOT/plugins

(
cd $ROOT
"$ROOT"/create_ddgr_plugins.py
)
test -d "$ROOT/plugins/search_wikipedia"
test -d "$ROOT/plugins/search_amazon"
