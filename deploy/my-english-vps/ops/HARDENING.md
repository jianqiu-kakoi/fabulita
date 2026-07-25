# Ubuntu VPS hardening checklist

Do these interactively. Keep the current SSH session open until a second
key-only session succeeds. The install script deliberately does not mutate SSH
or firewall rules because an incorrect source IP can lock you out.

## SSH

1. Create a named administrator; do not use the `myenglish` service account:

   ```sh
   sudo adduser deploy
   sudo usermod -aG sudo deploy
   sudo install -d -m 0700 -o deploy -g deploy /home/deploy/.ssh
   sudoedit /home/deploy/.ssh/authorized_keys
   sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys
   sudo chmod 0600 /home/deploy/.ssh/authorized_keys
   ```

2. Verify a second SSH connection as `deploy`.
3. Add `/etc/ssh/sshd_config.d/90-my-english-hardening.conf`:

   ```text
   PermitRootLogin no
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   PermitEmptyPasswords no
   PubkeyAuthentication yes
   MaxAuthTries 3
   X11Forwarding no
   AllowAgentForwarding no
   PermitTunnel no
   ```

4. Validate before reloading:

   ```sh
   sudo sshd -t
   sudo systemctl reload ssh
   ```

## UFW

Replace `YOUR_ADMIN_IPV4` with the public IP of the machine from which you
administer the VPS. Add an equivalent IPv6 rule if you administer over IPv6.

```sh
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from YOUR_ADMIN_IPV4/32 to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Never expose ports `3000` or `5432`. The API binds only to
`127.0.0.1:3000`; SQLite has no network listener.

## Operations

- Keep Cloudflare SSL/TLS mode at **Full (strict)**.
- Caddy accepts forwarded client IPs only from the Cloudflare CIDRs embedded in
  its `trusted_proxies` configuration. Keep those ranges synchronized with
  <https://www.cloudflare.com/ips-v4> and
  <https://www.cloudflare.com/ips-v6>. Never trust `CF-Connecting-IP`
  unconditionally while the origin remains public.
- Keep the origin IP private where practical. Restricting ports 80/443 to
  Cloudflare's current ranges is stronger than header validation, but do not
  enable that restriction until certificate renewal, CIDR update, and recovery
  procedures have been tested.
- Run `sudo apt update && sudo apt full-upgrade` regularly and reboot when
  `/var/run/reboot-required` exists.
- Do not store Vultr, Cloudflare, SSH, or sudo passwords in the application env.
- Copy encrypted backups to a second provider. Backups on the VPS disk alone do
  not protect against account loss or disk deletion.
