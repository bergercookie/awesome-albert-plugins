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
    if [ "$(which "$*" 2>&1 1>/dev/null)" = "1" ]
    then
        return 1
    else
        return 0
    fi
}

# Check prereqs ----------------------------------------------------------------
ret=$(is_installed albert)
if [ "$ret" = "1" ]
then
    announce_err "Please install albert first. Exiting"
    return 1
fi
ret=$(is_installed git)
if [ "$ret" = "1" ]
then
    announce_err "Please install git first. Exiting"
    return 1
fi

DST="$HOME/.local/share/albert/org.albert.extension.python/modules"
if [[ ! -d "$DST" ]]
then
    announce_err "Local extensions directory doesn't exist. Please check your albert installation. Exiting"
    return 1
fi

# Install ----------------------------------------------------------------------

PLUGIN_DIR="$DST/awesome-albert-plugins"
if [ -d "$PLUGIN_DIR" ]
then
    rm -rf "$PLUGIN_DIR"
fi
announce "Cloning awesome-albert-plugins -> $PLUGIN_DIR"
git clone "https://github.com/bergercookie/awesome-albert-plugins" "$PLUGIN_DIR"
announce "Installed awesome-albert-plugins -> $PLUGIN_DIR"

cd "$PLUGIN_DIR"
for plugin in $(ls plugins);
do (
    cd "$plugin"
    ./install-plugin.sh
)
done

announce "Plugin ready - Enable it from the Albert settings"
