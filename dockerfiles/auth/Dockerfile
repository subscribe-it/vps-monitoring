# ForwardAuth dla Traefika — nginx z konfiguracją wypaloną w obrazie.
# Hash htpasswd renderuje wpis startowy ze zmiennej środowiskowej,
# dzięki czemu sekret nie trafia ani do repo, ani do labeli Traefika.
FROM nginx:alpine
COPY config/auth/default.conf /etc/nginx/conf.d/default.conf
COPY config/auth/10-render-htpasswd.sh /docker-entrypoint.d/10-render-htpasswd.sh
# Plik treści dla /verify — musi istnieć, bo uwierzytelnianie odbywa się
# dopiero w fazie `try_files` (content), a nie w `return` (rewrite).
RUN printf 'ok\n' > /usr/share/nginx/html/verify-ok.txt \
 && chmod 0755 /docker-entrypoint.d/10-render-htpasswd.sh \
 && chown -R nginx:nginx /etc/nginx/conf.d /usr/share/nginx/html
