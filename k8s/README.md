# Kubernetes Deployment

Run pyrobud on Kubernetes with persistent storage for the database and Telegram session.

## Prerequisites

- k3s (or any Kubernetes cluster) with `kubectl` configured
- A Telegram API ID and hash from https://my.telegram.org/apps
- A default StorageClass that supports `ReadWriteOnce` PVCs

## Setup

### 1. Build the image

```bash
docker build -t pyrobud:latest .  # or: podman build --net=host -t pyrobud:latest .
```

k3s imports images from the local Docker daemon automatically via containerd. If your nodes don't share the Docker daemon, import manually:

```bash
docker save pyrobud:latest | sudo k3s ctr images import -
```

### 2. Create your config secret

```bash
cp k8s/secret.yaml.example k8s/secret.yaml
```

Edit `k8s/secret.yaml` and fill in your `api_id` and `api_hash`. The file is gitignored by default.

### 3. Deploy

```bash
kubectl apply -f k8s/secret.yaml
kubectl apply -k k8s/
```

This creates:
- A `pyrobud` namespace
- A StatefulSet with a 1Gi PersistentVolumeClaim for bot data
- An init container that copies your config into the PVC on first run

### 4. First-time Telegram login

Telethon requires an interactive login the first time (phone number + verification code). Attach to the running pod:

```bash
kubectl exec -it -n pyrobud pyrobud-0 -- pyrobud
```

Follow the prompts to authenticate. Once logged in, the session is saved to the PVC. Press `Ctrl+C` to exit — the StatefulSet will restart the pod and it will run autonomously from then on.

### 5. Verify

```bash
kubectl logs -n pyrobud pyrobud-0 -f
```

## Updating config

The bot's config lives on the PVC at `/data/config.toml`. To edit it:

```bash
kubectl exec -it -n pyrobud pyrobud-0 -- vi /data/config.toml
```

Then restart the pod:

```bash
kubectl delete pod -n pyrobud pyrobud-0
```

The StatefulSet will recreate it with the updated config. The init container only copies config on first run (when no `config.toml` exists on the PVC), so your changes are preserved.

## Updating the bot image

```bash
docker build -t pyrobud:latest .  # or: podman build --net=host -t pyrobud:latest .
docker save pyrobud:latest | sudo k3s ctr images import -
kubectl rollout restart -n pyrobud statefulset/pyrobud
```

## Cleanup

```bash
kubectl delete -k k8s/
kubectl delete -f k8s/secret.yaml
# PVC is retained — delete manually if you want to wipe data:
kubectl delete pvc -n pyrobud data-pyrobud-0
kubectl delete namespace pyrobud
```

## Architecture notes

- **StatefulSet** (not Deployment) because the bot has persistent state — a LevelDB database and a Telethon session file. These must survive pod rescheduling.
- The **init container** copies config from the Secret to the PVC only on first boot. This is because the bot modifies `config.toml` in-place during schema upgrades, so it can't be a read-only Secret mount.
- `stdin: true` and `tty: true` are set on the container so `kubectl exec -it` works for initial login.
- Resource defaults: 128Mi-512Mi memory, 100m-1 CPU. Adjust in `statefulset.yaml` as needed.
