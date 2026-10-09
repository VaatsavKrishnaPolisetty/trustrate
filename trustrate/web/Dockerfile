FROM php:8.3-apache
RUN apt-get update && apt-get install -y --no-install-recommends libcurl4-openssl-dev \
    && docker-php-ext-install pdo_mysql curl \
    && rm -rf /var/lib/apt/lists/* \
    && printf 'DirectoryIndex index.php\nServerTokens Prod\nServerSignature Off\n' > /etc/apache2/conf-available/trustrate.conf \
    && a2enconf trustrate
COPY web/ /var/www/html/
COPY db/*.php db/schema.sql /var/www/db/
RUN ln -s /var/www/html /var/www/web
RUN printf 'display_errors=Off\nlog_errors=On\nexpose_php=Off\n' > /usr/local/etc/php/conf.d/trustrate.ini
