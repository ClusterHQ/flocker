# See README for instructions on how to build.
Name:           clusterhq-release
Version:        1
Release:        1%{?dist}
Summary:        ClusterHQ Repository Configuration

License:        ASL 2.0
URL:            https://clusterhq.com/
Source0:        clusterhq.repo

BuildArch:      noarch

%description
ClusterHQ repository for RHEL

%install
cd %{_sourcedir}
install -d -m 755 $RPM_BUILD_ROOT/etc/yum.repos.d
install -m 644 clusterhq.repo $RPM_BUILD_ROOT/etc/yum.repos.d

%files
%config(noreplace) /etc/yum.repos.d/clusterhq.repo


%changelog
* Thu Dec 16 2016 Richard Wall <richard.wall@clusterhq.com> 1-1.el7
- Initial Package
