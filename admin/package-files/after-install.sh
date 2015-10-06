# https://git.fedorahosted.org/cgit/firewalld.git/tree/config/macros.firewalld
test -f /usr/bin/firewall-cmd \
    && /usr/bin/firewall-cmd --reload --quiet \
    && /usr/bin/firewall-cmd --permanent --add-service flocker-control-api \
    && /usr/bin/firewall-cmd --add-service flocker-control-api \
    && /usr/bin/firewall-cmd --permanent --add-service flocker-control-agent \
    && /usr/bin/firewall-cmd --add-service flocker-control-agent || :
which systemctl && systemctl reload-or-restart rsyslog.service || :
