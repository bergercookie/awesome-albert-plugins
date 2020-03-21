FROM bergercookie/albertlauncher:ubuntu18.04

# Arguments --------------------------------------------------------------------
ARG USERNAME=someuser
ARG ARG_UID=$TARGET_UID
ARG ARG_GID=$TARGET_GID
ARG HOME="/src"

# Environment ------------------------------------------------------------------
ENV UID=$ARG_UID
ENV GID=$ARG_GID

# install packages -------------------------------------------------------------
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install --no-install-recommends -y vim sudo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# don't be root ----------------------------------------------------------------
RUN mkdir -p /src/$USERNAME
RUN echo "$USERNAME:x:$UID:$GID:$USERNAME,,,:$HOME:/bin/bash" >> /etc/passwd
RUN echo "$USERNAME:x:$UID:" >> /etc/group
RUN echo "$USERNAME ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/$USERNAME
RUN chmod 0440 /etc/sudoers.d/$USERNAME
RUN chown "$UID:$GID" -R $HOME

USER $USERNAME
ENV HOME $HOME
WORKDIR $HOME
