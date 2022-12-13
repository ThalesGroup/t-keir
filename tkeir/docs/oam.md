# Operation and Management With Docker

This section describes the operations and the management of T-KEIR services.

## Start and stop the services

All the services are embedded in a docker-compose file to run the services go in directory **runtime/docker** and run:

```shell
docker-compose -f docker-compose-tkeir.yml up
```

### List services

```shell
docker ps -a
```

```{image} resources/images/tkeir-docker-ps.png
```

### Stop and restart service

To stop a service :

```shell
docker stop <service name>
```

To restart a service

```shell
docker start <service name>
```

### Get output a a service (log)

```shell
docker logs --details <service name>
```

```{image} resources/images/tkeir-docker-log.png
```

## Check the service health

You can check the health of a service by using the endpoint **health** of the service. The rest function will return standard http code 200
and a json description of the running service.

```{image} resources/images/docker-rest-health.png
```

## Tools life cyle and release

This first release is available on Thales Inner Sources repository.
We make a tag for each project and create release when important features and bugs fixes has been done.
