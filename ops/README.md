# Verdimetria operations assets

Questa directory e' la fonte versionata per nginx, backup e alerting di `pcc`.
Le copie di rollback nginx devono stare fuori da `sites-enabled`.

## Installazione VPS

1. Installare `nginx/verdimetria-api.conf` in
   `/etc/nginx/sites-available/verdimetria-api` e mantenere un solo symlink in
   `sites-enabled`; eseguire `nginx -t` prima del reload.
2. Installare `scripts/verdimetria-backup-watchdog` in `/usr/local/sbin/` con
   owner root e mode `0755`.
3. Installare le unita' di `systemd/` in `/etc/systemd/system/`, eseguire
   `systemctl daemon-reload`, poi un backup differential manuale tramite la
   nuova unita'. Solo dopo la prova verde, disabilitare le equivalenti righe
   cron e abilitare i timer full, diff e watchdog.
4. Configurare `OPS_ALERT_EMAIL` in `/opt/verdimetria/.env` e provare
   `verdimetria-ops-alert@test.service`. Un exit code zero prova l'accettazione
   SMTP; la ricezione deve essere confermata dal destinatario.

Il watchdog controlla backup oltre 30 ore, pgBackRest non sano, WAL `.ready`
oltre 10 minuti o ultimo errore non recuperato, disco/inode almeno all'80% e
heartbeat mirror oltre 8 ore. I marker in `/var/lib/verdimetria-monitor/`
garantiscono una sola email per transizione sano→guasto.

## Mirror locale

Installare i due file `systemd/user/` in `~/.config/systemd/user/`. L'heartbeat
remoto viene scritto solo dopo un rsync completato; il watchdog VPS rileva anche
un portatile spento o una sincronizzazione interrotta.

## Rollback

Disabilitare i tre timer systemd, ripristinare il crontab salvato prima della
migrazione e rimuovere esclusivamente le unita' Verdimetria installate. Per
nginx ripristinare il file conservato fuori `sites-enabled`, mantenendo sempre
un solo symlink attivo, quindi `nginx -t` e reload.
