FROM bergercookie/albertlauncher:ubuntu18.04

# Arguments --------------------------------------------------------------------
ARG USERNAME=someuser
ARG UID=1000
ARG GID=1000
ARG HOME="/home/someuser"
ARG SRC

# Environment ------------------------------------------------------------------
ENV UID_=$UID
ENV GID_=$GID

# local configuration ----------------------------------------------------------

# install packages -------------------------------------------------------------
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install --no-install-recommends -y vim sudo \
    python3 python3-pip python3-setuptools \
    libsasl2-dev python-dev libldap2-dev libssl-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 install --upgrade wheel pyopenssl
RUN pip3 install --upgrade secrets requests ddgr cookiecutter

# don't be root ----------------------------------------------------------------
RUN echo "$USERNAME:x:$UID_:$GID_:$USERNAME,,,:$HOME:/bin/bash" >> /etc/passwd
RUN echo "$USERNAME:x:$UID_:" >> /etc/group
RUN echo "$USERNAME ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/$USERNAME
RUN chmod 0440 /etc/sudoers.d/$USERNAME
RUN chown "$UID_:$GID_" -R $HOME

RUN mkdir -p $SRC
RUN chown "$UID_:$GID_" -R $SRC

USER $USERNAME
ENV HOME $HOME
WORKDIR $SRC
