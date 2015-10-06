# https://git.fedorahosted.org/cgit/firewalld.git/tree/config/macros.firewalld
test -f /usr/bin/firewall-cmd && firewall-cmd --reload --quiet || :
which systemctl && systemctl reload-or-restart rsyslog.service || :
