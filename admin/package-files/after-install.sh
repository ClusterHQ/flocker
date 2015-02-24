# https://git.fedorahosted.org/cgit/firewalld.git/tree/config/macros.firewalld
test -f %{_bindir}/firewall-cmd && firewall-cmd --reload --quiet || :
