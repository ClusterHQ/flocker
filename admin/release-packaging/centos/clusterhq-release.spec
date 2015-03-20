# See README for instructions on how to build.
Name:           clusterhq-release
Version:        1
Release:        7%{?dist}
Summary:        ClusterHQ Repository Configuration

License:        ASL 2.0
URL:            https://clusterhq.com/
Source0:        clusterhq.repo

BuildArch:      noarch

%description
ClusterHQ repository for CentOS

%install
cd %{_sourcedir}
install -d -m 755 $RPM_BUILD_ROOT/etc/yum.repos.d
install -m 644 clusterhq.repo $RPM_BUILD_ROOT/etc/yum.repos.d

%files
%config(noreplace) /etc/yum.repos.d/clusterhq.repo


%changelog
* Wed Mar 11 2015 Tom Prince <tom.prince@clusterhq.com> - 1-7
- Combine marketing and development packages.

* Mon Mar 9 2015 Adam Dangoor <adam.dangoor@clusterhq.com> - 1-6
- Use development repository location.

* Sun Mar 8 2015 Adam Dangoor <adam.dangoor@clusterhq.com> - 1-5
- Support CentOS 7.
- New location for repository - Amazon S3.

* Fri Sep 11 2014 Tom Prince <tom.prince@clusterhq.com> - 1-4.fc20
- Fix source repository URL.
- Use https URLs.

* Fri Aug 22 2014 Tom Prince <tom.prince@clusterhq.com> - 1-3.fc20
- Disable GPG checks, since we don't have a signing key.

* Thu Jul 17 2014 Tom Prince <tom.prince@clusterhq.com> - 1-2.fc20
- Don't depend on zfs-release, since it isn't needed for flocker-cli.

* Tue Jul 15 2014 Tom Prince <tom.prince@clusterhq.com> - 1-1.fc20
- Initial Package 
