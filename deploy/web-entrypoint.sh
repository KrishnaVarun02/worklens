#!/bin/sh
set -eu
# Resolve only the internal API before closing all new outbound paths. nginx then
# uses a pinned address; no DNS forwarding or dynamic remote upstream is needed.
api_ip="$(getent hosts api | awk 'NR == 1 {print $1}')"
case "$api_ip" in
  ''|*[!0-9.]*) echo 'Internal API IPv4 resolution failed' >&2; exit 1 ;;
esac
sed "s/api:8000/$api_ip:8000/g" /etc/nginx/nginx.conf > /tmp/worklens-nginx.conf
iptables -P OUTPUT DROP
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -d "$api_ip/32" -p tcp --dport 8000 -m conntrack --ctstate NEW -j ACCEPT
ip6tables -P OUTPUT DROP
ip6tables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
# Remove firewall/raw-socket privileges from the nginx process and all descendants.
exec /bin/setpriv --bounding-set=-net_admin,-net_raw --inh-caps=-all --ambient-caps=-all \
  nginx -c /tmp/worklens-nginx.conf -g 'daemon off;'
