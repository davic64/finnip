# Cura 5.14 for Linux (the version the user runs on the Mac): only CuraEngine, its bundled libraries and
# the resources for the Ender-3 V3 SE are kept. Debian 13 ships Cura 5.0, without this printer.
FROM debian:trixie-slim AS cura
ARG CURA_VERSION=5.14.0
ARG CURA_SHA256=988a2a67cce7ee7b9b9a843aad65ec4754d2ceb0a72e70eeaf884b995b75990f
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /tmp/cura
RUN curl -fsSL -o cura.AppImage \
        "https://github.com/Ultimaker/Cura/releases/download/${CURA_VERSION}/UltiMaker-Cura-${CURA_VERSION}-linux-X64.AppImage" \
    && echo "${CURA_SHA256}  cura.AppImage" | sha256sum -c - \
    && chmod +x cura.AppImage && ./cura.AppImage --appimage-extract >/dev/null \
    && S=squashfs-root && R=$S/share/cura/resources && O=/opt/cura \
    && mkdir -p $O/resources/materials $O/resources/variants $O/resources/quality/creality \
    && cp $S/CuraEngine $S/libArcus.so $S/libpolyclipping.so.22 $S/libcura-formulae-engine.so \
          $S/libtbb.so.12 $S/libtbbmalloc.so.2 $S/libtbbmalloc_proxy.so.2 $O/ \
    && cp -r $R/definitions $R/extruders $O/resources/ \
    && cp -r $R/variants/creality $O/resources/variants/ \
    && cp -r $R/quality/creality/base $O/resources/quality/creality/ \
    && cp $R/materials/generic_pla_175.xml.fdm_material $R/materials/generic_petg_175.xml.fdm_material \
          $O/resources/materials/ \
    && chmod -R a+rX $O \
    && rm -rf /tmp/cura

FROM debian:trixie-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends openscad python3 libssl3t64 libzstd1 zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin parts
COPY --from=cura /opt/cura /opt/cura
# The AppImage binary names a relative loader (lib64/ld-linux…); run it through the system one.
RUN printf '#!/bin/sh\nLD_LIBRARY_PATH=/opt/cura exec /lib64/ld-linux-x86-64.so.2 /opt/cura/CuraEngine "$@"\n' \
        > /opt/cura/engine && chmod +x /opt/cura/engine \
    && /opt/cura/engine help | grep -q "version 5.14" && openscad --version
COPY parts /app/parts
COPY tests /app/tests
WORKDIR /app
ENV CURA_ENGINE=/opt/cura/engine CURA_RESOURCES=/opt/cura/resources PARTS_DIR=/data/parts \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER parts
CMD ["python3", "-m", "parts.server"]
