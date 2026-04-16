# Kubernetes / GKE Deployment

Production Kubernetes deployment for Litestar applications. Covers Deployment, Service, HPA, Ingress, and GKE-specific patterns (Workload Identity, Cloud SQL Auth Proxy).

## Architecture

```text
Ingress (nginx) -> api-service -> API Deployment (Litestar + Granian)
                                  Worker Deployment (SAQ)
                                  PostgreSQL StatefulSet
                                  Redis StatefulSet
```

## API Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: {{ namespace }}
  labels:
    app: api
    app.kubernetes.io/component: backend
spec:
  replicas: {{ api_replicas }}
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: api
    spec:
      serviceAccountName: {{ service_account_name }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 65532
        runAsGroup: 65532
        fsGroup: 65532
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: api
          image: {{ api_image_repo }}:{{ image_tag }}
          ports:
            - name: http
              containerPort: 8000
          env:
            - name: SAQ_USE_SERVER_LIFESPAN
              value: "false"
          envFrom:
            - configMapRef:
                name: app-config
            - secretRef:
                name: app-secrets
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              memory: "512Mi"
              cpu: "200m"
            limits:
              memory: "1Gi"
              cpu: "1000m"
          volumeMounts:
            - name: tmp-volume
              mountPath: /tmp
          startupProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            periodSeconds: 15
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            periodSeconds: 5
            failureThreshold: 3
      terminationGracePeriodSeconds: 60
      volumes:
        - name: tmp-volume
          emptyDir: {}
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: api
                topologyKey: kubernetes.io/hostname
```

## Worker Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker
  namespace: {{ namespace }}
spec:
  replicas: {{ worker_replicas }}
  selector:
    matchLabels:
      app: worker
  template:
    spec:
      serviceAccountName: {{ service_account_name }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 65532
        runAsGroup: 65532
        fsGroup: 65532
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: worker
          image: {{ worker_image_repo }}:{{ image_tag }}
          # Uses Dockerfile.worker CMD: app workers run
          env:
            - name: SAQ_USE_SERVER_LIFESPAN
              value: "false"
          envFrom:
            - configMapRef:
                name: app-config
            - secretRef:
                name: app-secrets
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              memory: "512Mi"
              cpu: "200m"
            limits:
              memory: "1Gi"
              cpu: "1000m"
          volumeMounts:
            - name: tmp-volume
              mountPath: /tmp
      terminationGracePeriodSeconds: 120
      volumes:
        - name: tmp-volume
          emptyDir: {}
```

No HTTP probes for the worker. Kubernetes restarts the pod if the process exits. Set `terminationGracePeriodSeconds: 120` to allow in-flight tasks to finish.

## HorizontalPodAutoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
  namespace: {{ namespace }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 75
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 25
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
        - type: Pods
          value: 4
          periodSeconds: 15
      selectPolicy: Max
```

## Ingress with TLS

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - app.example.com
      secretName: app-tls
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api-service
                port:
                  number: 80
          - path: /health
            pathType: Exact
            backend:
              service:
                name: api-service
                port:
                  number: 80
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api-service
                port:
                  number: 80
```

## GKE Workload Identity

Bind a Kubernetes ServiceAccount to a GCP service account for secure access to GCP APIs without storing credentials:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: litestar-app
  namespace: {{ namespace }}
  annotations:
    iam.gke.io/gcp-service-account: app-sa@my-project.iam.gserviceaccount.com
```

Then in GCP:

```bash
gcloud iam service-accounts add-iam-policy-binding \
    app-sa@my-project.iam.gserviceaccount.com \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:my-project.svc.id.goog[namespace/litestar-app]"
```

## Deploy tool

The fullstack-spa ships with a Python deploy script (`tools/deploy/k8s/deploy.py`) that renders Jinja2 templates and applies them via kubectl:

```bash
# Deploy to dev
python deploy.py deploy -e dev --env-file .env --api-image-repo gcr.io/my-project/app

# Deploy to production with a pinned tag
python deploy.py deploy -e prod --tag v1.2.3 --env-file .env \
    --api-image-repo gcr.io/my-project/app \
    --gcp-service-account app-sa@my-project.iam.gserviceaccount.com

# Delete dev resources
python deploy.py delete -e dev --env-file .env
```

The deploy tool renders templates in dependency order: namespace, secrets, configmap, statefulsets, services, deployments, HPAs, ingress.

## Environment-specific resource sizing

| Resource | Dev | Prod |
|---|---|---|
| API replicas | 1 | 2-10 (HPA) |
| Worker replicas | 1 | 2-10 (HPA) |
| API CPU request/limit | 100m / 500m | 200m / 1000m |
| API memory request/limit | 256Mi / 512Mi | 512Mi / 1Gi |
| DB storage | 5Gi | 20Gi |
| HPA CPU target | 70% | 60% |
