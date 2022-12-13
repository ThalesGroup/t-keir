# Security

## REST API Secure Layer

By default the tools does not use SSL.
All the services provide a way to run on SSL layer. A self signed certificate is provided to test HTTPS but it is mandatory to have signed certicates in production mode.

When you run a service

```shell
python3 thot/<service>_svc.py --config=<path to service configuration file>
```

The confguration file describre network access.

Example of Configuration:

```json title="network configuration"
--8<-- "./docs/configuration/examples/networkconfiguration.json"
```

The ssl networks fields:

- **ssl** : ssl configuration **IN PRODUCTION IT IS MANDATORY TO USE CERTIFICATE AND KEY THAT ARE \*NOT\* SELF SIGNED**

  - **cert** : certificate file
  - **key** : key file

are not mandatory. The provide a way do define the certicate associated to https scheme

## Use your favorite API Gateway

To create token and fine use of the API (billing, number of requests ... ) you can use a third party API gateway like WSO2/am.
