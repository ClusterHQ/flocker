#!/bin/sh
set -e
[ -f rootfs.tar ] || { 
    echo "Hmm this should run in the directory of rootfs.tar"
    exit 1
}
rm -rf extra
rm -f mongoimage.tar
mkdir extra extra/etc extra/sbin extra/lib extra/lib64 extra/home extra/home/mongodb extra/data extra/data/db
touch extra/etc/resolv.conf
touch extra/sbin/init
cp /lib/x86_64-linux-gnu/libpthread.so.0 /lib/x86_64-linux-gnu/libc.so.6 extra/lib
cp /lib/x86_64-linux-gnu/librt.so.1 extra/lib
cp /lib64/ld-linux-x86-64.so.2 extra/lib64
cp /usr/lib/x86_64-linux-gnu/libstdc++.so.6 /lib/x86_64-linux-gnu/libm.so.6 extra/lib
#CHANGE THE FOLLOWING LINE TO POINT TO A COPY OF THE MONGOD BINARY
cp -R mongo/mongodb-linux-x86_64-2.6.3/bin/mongod extra/home/mongodb
cp mongo/mongo.conf extra/home/mongodb
cp rootfs.tar mongoimage.tar
tar rvf mongoimage.tar -C extra .
docker import - clusterhq/mongolite < mongoimage.tar
