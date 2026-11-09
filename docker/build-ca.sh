# Sourced by Dockerfile build steps:
#
#   RUN --mount=type=bind,source=docker/build-ca.sh,target=/tmp/build-ca.sh \
#       --mount=type=secret,id=build_ca,required=false,mode=0444 \
#       . /tmp/build-ca.sh && <the step> && build_ca_done
#
# Normal builds (GitHub Actions, a home server) pass no secret, and then this
# does nothing at all. Builds behind a proxy that re-signs HTTPS pass the
# proxy's CA bundle as a BuildKit secret:
#
#   docker build --secret id=build_ca,src=/path/ca-bundle.crt \
#     --build-arg HTTPS_PROXY=http://proxy:port --network host .
#
# Then the step's tools trust it (pip, npm/node, git, curl, cargo, .NET via
# OpenSSL) and apt fetches over HTTPS, since such proxies usually refuse
# plain-HTTP requests. build_ca_done puts apt's files back before the layer is
# saved; the script and the secret are mounted for the step only, so neither
# the CA nor this file ends up in an image.

build_ca_done() { :; }

if [ -s /run/secrets/build_ca ]; then
    _ca=/run/secrets/build_ca
    export SSL_CERT_FILE="$_ca" NODE_EXTRA_CA_CERTS="$_ca" PIP_CERT="$_ca" REQUESTS_CA_BUNDLE="$_ca" \
           CURL_CA_BUNDLE="$_ca" GIT_SSL_CAINFO="$_ca" CARGO_HTTP_CAINFO="$_ca" DENO_CERT="$_ca"
    if [ -d /etc/apt ]; then
        _apt_backup="$(mktemp -d)"
        for _f in /etc/apt/sources.list /etc/apt/sources.list.d/*; do
            [ -f "$_f" ] || continue
            mkdir -p "$_apt_backup$(dirname "$_f")"
            cp -p "$_f" "$_apt_backup$_f"
            sed -i 's#http://\(deb\.debian\.org\|archive\.ubuntu\.com\|security\.ubuntu\.com\|security\.debian\.org\)#https://\1#g' "$_f"
        done
        printf 'Acquire::https::CAInfo "%s";\n' "$_ca" > /etc/apt/apt.conf.d/99-build-ca
        build_ca_done() {
            rm -f /etc/apt/apt.conf.d/99-build-ca
            (cd "$_apt_backup" && find . -type f) | while IFS= read -r _f; do
                cp -p "$_apt_backup/$_f" "/$_f"
            done
            rm -rf "$_apt_backup"
        }
    fi
fi
