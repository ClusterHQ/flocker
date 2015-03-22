set -e

WHEELHOUSE=$(pwd)/admin/build_targets/centos-7/wheelhouse

docker build -t clusterhq/base-builder -f admin/build_targets/centos-7/Dockerfile.base-builder admin/build_targets/centos-7/

docker build -t clusterhq/wheel-builder -f admin/build_targets/centos-7/Dockerfile.wheel-builder admin/build_targets/centos-7/
docker run --rm -v $(pwd):/application -v ${WHEELHOUSE}:/wheelhouse clusterhq/wheel-builder

docker build -t clusterhq/package-builder -f admin/build_targets/centos-7/Dockerfile.package-builder admin/build_targets/centos-7/
docker run --rm -v $(pwd):/flocker -v ${WHEELHOUSE}:/wheelhouse -v $(pwd):/output clusterhq/package-builder
