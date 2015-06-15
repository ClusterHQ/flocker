# Build this with `rpmbuild -bb admin/flocker-zfs.spec` on the target distribution.

Name:		flocker-zfs
Version:	0
Release:	2%{?dist}
Summary:	Metapackage installing known working version of ZFS.

Group:		System Environment/Kernel
License:	ASL 2.0
URL:		http://www.clusterhq.com/

BuildArch:	noarch

%define zfs_version 0.6.3-g7f3e466.clusterhq.0%{?dist}
%define spl_version 0.6.3-76_g6ab0866.clusterhq.0%{?dist}

Requires:	libnvpair1 = %{zfs_version}
Requires:	libuutil1 = %{zfs_version}
Requires:	libzfs2 = %{zfs_version}
Conflicts:	libzfs2-devel < %{zfs_version}
Conflicts:	libzfs2-devel > %{zfs_version}
Requires:	libzpool2 = %{zfs_version}
Requires:	spl = %{spl_version}
Conflicts:	spl-debuginfo < %{spl_version}
Conflicts:	spl-debuginfo > %{spl_version}
Requires:	spl-dkms = %{spl_version}
Requires:	zfs = %{zfs_version}
Conflicts:	zfs-debuginfo > %{zfs_version}
Conflicts:	zfs-debuginfo < %{zfs_version}
Requires:	zfs-dkms = %{zfs_version}
Conflicts:	zfs-dracut < %{zfs_version}
Conflicts:	zfs-test > %{zfs_version}

%prep

%clean

%files

%description
This package ensures that a version of ZFSOnLinux that has been validated
by ClusterHQ for use with flocker is installed.

%changelog
* Fri Jun 12 2015 Tom Prince <tom.prince@clusterhq.com> 0-2
- Fix typo in description.

* Thu Jun 11 2015 Richard Yao <richard.yao@clusterhq.com> 0-1
- Initial package
