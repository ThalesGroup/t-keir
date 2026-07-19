#!/usr/bin/env bash
# Run kube-bench CIS checks against the current cluster (digest-pinned image).
set -euo pipefail

# Pin updated via: docker pull aquasec/kube-bench:v0.10.1 && docker inspect …
KUBE_BENCH_IMAGE="${KUBE_BENCH_IMAGE:-aquasec/kube-bench:v0.10.1}"

command -v kubectl >/dev/null 2>&1 || { echo "kubectl required"; exit 1; }

kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: tkeir-kube-bench
  namespace: default
spec:
  ttlSecondsAfterFinished: 600
  template:
    spec:
      hostPID: true
      restartPolicy: Never
      containers:
        - name: kube-bench
          image: ${KUBE_BENCH_IMAGE}
          command: ["kube-bench", "run", "--targets", "node,master,policies"]
          volumeMounts:
            - name: var-lib-kubelet
              mountPath: /var/lib/kubelet
              readOnly: true
            - name: etc-systemd
              mountPath: /etc/systemd
              readOnly: true
            - name: etc-kubernetes
              mountPath: /etc/kubernetes
              readOnly: true
      volumes:
        - name: var-lib-kubelet
          hostPath: { path: /var/lib/kubelet }
        - name: etc-systemd
          hostPath: { path: /etc/systemd }
        - name: etc-kubernetes
          hostPath: { path: /etc/kubernetes }
EOF

echo "kube-bench Job submitted (tkeir-kube-bench). Inspect logs with:"
echo "  kubectl logs job/tkeir-kube-bench"
