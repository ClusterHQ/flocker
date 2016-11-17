# Flocker-dataset-agent docker container

To build the docker image for a released version of Flocker, run:
```
export FLOCKER_VERSION=1.15.0
docker build \
    --rm \
    --tag "clusterhq/flocker-dataset-agent:${FLOCKER_VERSION}" \
    --build-arg "FLOCKER_VERSION=${FLOCKER_VERSION}-1" \
    .
```

You can also build the latest version of Flocker from a custom repository:

```
docker build \
    --rm
    --tag "clusterhq/flocker-dataset-agent:master" \
    --build-arg "FLOCKER_REPOSITORY=http://build.clusterhq.com/results/omnibus/master/ubuntu-16.04/"
    .
```

To check the image, run the container with the argument ```--version```:
```
$ docker run --rm clusterhq/flocker-dataset-agent:master --version
1.15.0.post2+131.g156c7ca
```
