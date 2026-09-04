#!/usr/bin/env bash
# Publish the AFTERBELL dashboard on a domain.
#
#   sudo ./deploy/publish.sh afterbell.example.xyz
#
# Refuses to touch nginx until DNS actually resolves to this host, because a
# certbot run against a domain that does not point here fails the HTTP-01
# challenge and burns a rate-limit attempt.
set -euo pipefail

DOMAIN="${1:?usage: publish.sh <domain>}"
HOST_IP="$(curl -fsS https://api.ipify.org)"
DNS_IP="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)"

echo "domain     $DOMAIN"
echo "this host  $HOST_IP"
echo "resolves   ${DNS_IP:-<no A record yet>}"

if [ "$DNS_IP" != "$HOST_IP" ]; then
  echo
  echo "DNS does not point here yet. Add an A record:"
  echo "    $DOMAIN.  A  $HOST_IP"
  echo "then re-run. Propagation is usually a minute or two."
  exit 1
fi

if ! curl -fsS localhost:8100/healthz >/dev/null; then
  echo "dashboard is not answering on 8100; start afterbell-dashboard first" >&2
  exit 1
fi

sed "s/AFTERBELL_DOMAIN/$DOMAIN/g" deploy/nginx-afterbell.conf \
  > /etc/nginx/sites-available/afterbell
ln -sf /etc/nginx/sites-available/afterbell /etc/nginx/sites-enabled/afterbell
nginx -t
systemctl reload nginx
certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos \
        --register-unsafely-without-email --redirect

echo
echo "live: https://$DOMAIN"
curl -fsS "https://$DOMAIN/healthz" && echo " <- reachable"
