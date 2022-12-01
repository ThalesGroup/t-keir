docker run --name my-prometheus \
    --mount type=bind,source=/home/blaudez/workspace/tkeir-rc/tkeir/runtimes/docker/prometheus.yml,destination=/etc/prometheus/prometheus.yml \
    --publish published=9090,target=9090,protocol=tcp \
    --network tkeir-net \
    prom/prometheus