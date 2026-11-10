# Caddy with the Tailscale plugin: tailscale_auth asks the host's tailscaled who is connecting,
# so the voice gateway keeps getting Tailscale-User-Login as it did behind `tailscale serve`.
FROM caddy:2-builder AS build
RUN xcaddy build --with github.com/tailscale/caddy-tailscale

FROM caddy:2
COPY --from=build /usr/bin/caddy /usr/bin/caddy
