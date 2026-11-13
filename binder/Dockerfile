ARG APP_VERSION=1.0.0

FROM ghcr.io/plant-food-research-open/deep-root-gen:${APP_VERSION}

ARG NB_USER=jovyan

ARG NB_UID=1000

ENV USER ${NB_USER}

ENV NB_UID ${NB_UID}

ENV HOME /home/${NB_USER}

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN adduser --disabled-password \
    --gecos "Default user" \
    --uid ${NB_UID} \
    ${NB_USER} \
    && mv /app/* ${HOME} \
    && chown -R ${NB_UID} ${HOME}

USER ${NB_USER}

WORKDIR ${HOME}
