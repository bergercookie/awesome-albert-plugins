#!/usr/bin/env bash
set -Eeuo pipefail
## do this if there's any error with the installation and you want to report a bug
# set -x

# supplementary funs -----------------------------------------------------------
function announce
{
    echo
    echo "**********************************************************************"
    echo -e "$@"
    echo "**********************************************************************"
    echo
}

function announce_err
{
    announce "[ERROR] $*"
}

function install_pkg
{
    announce "Installing \"$*\""
    pip3 install --user --upgrade "$*"
    announce "Installed $*"
}

function is_installed
{
    test -x "$(which "$*")"
}

# Check prereqs ----------------------------------------------------------------
if  ! is_installed albert
then
    announce_err "Please install [albert] first. Exiting"
    exit 1
fi

if ! is_installed git
then
    announce_err "Please install [git] first. Exiting"
    exit 1
fi

DST="$HOME/.local/share/albert/org.albert.extension.python/modules"
if [[ ! -d "$DST" ]]
then
    announce_err "Local extensions directory [$DST] doesn't exist. Please check your albert installation. Exiting"
    exit 1
fi

# Install ----------------------------------------------------------------------

PLUGIN_DIR="$DST/awesome-albert-plugins"
if [ -d "$PLUGIN_DIR" ]
then
    rm -rf "$PLUGIN_DIR"
fi

if test -f plugins && test -d cookiecutter && test -d themes && test -f LICENSE
then
else
    announce "Cloning awesome-albert-plugins -> $PLUGIN_DIR"
    git clone "https://github.com/bergercookie/awesome-albert-plugins" "$PLUGIN_DIR"
    announce "Installed awesome-albert-plugins -> $PLUGIN_DIR"

cd "$PLUGIN_DIR"
for plugin in $(ls plugins)
do (
    cd "$plugin"
    ./install-plugin.sh
)
done

announce "Plugins installed successfully - Enable them via the Albert settings"
