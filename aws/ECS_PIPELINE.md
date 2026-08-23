# Production deployment: GitHub Actions → ECR → ECS Fargate

This is **the** production deployment for the Guardian AI News Assistant. Pushing to `main`
runs the test suites, builds both Docker images, pushes them to ECR, and rolls them out to two
ECS Fargate services behind one Application Load Balancer. Docker Compose remains the local
development stack and is not used in production.

```
Developer ──► git push main ──► GitHub
                                  │
                          GitHub Actions
                             ├── test.yml  (pytest · vitest · docker builds)
                             └── aws.yml   (deploy — gated on tests)
                                  │
                          Docker build ──► Amazon ECR
                                             ├── guardian-backend
                                             └── guardian-frontend
                                  │
                          Amazon ECS Fargate
                             ├── guardian-backend service  (FastAPI + Gunicorn/Uvicorn :8000)
                             └── guardian-frontend service (nginx SPA :80)
                                  │
                          Application Load Balancer (HTTPS)
                             ├── /api/*  ──► backend  :8000
                             └── /*      ──► frontend :80
                                  │
                                Users
```

The deploy workflow is [`.github/workflows/aws.yml`](../.github/workflows/aws.yml). It renders
the task definitions **from this repository**, so environment variables and secret ARNs are
versioned with the code and ship on the same commit as the image.

Supporting services behind the backend:

```
ECS backend task
   ├── Amazon RDS PostgreSQL + pgvector      (DATABASE_URL)
   ├── Amazon ElastiCache Redis              (REDIS_URL)
   ├── SSM Parameter Store / Secrets Manager (all API keys)
   ├── Amazon CloudWatch Logs                (/ecs/guardian-*)
   └── External APIs — Guardian · NYT · Tavily · OpenAI
```

**Cost note:** ALB + 2 Fargate services + RDS + ElastiCache runs roughly **$80–120/month**
minimum. Scale `desired-count`, the RDS instance class and the ElastiCache node type down for
a demo environment.

Set two shell variables used throughout (CloudShell or a configured terminal):

```bash
export AWS_REGION=us-east-2          # the region both task definitions are set to
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
```

> **Region:** `aws/taskdef-backend.json` and `aws/taskdef-frontend.json` are set to
> **`us-east-2`** — in the ECR image URI, the SSM parameter ARNs and `awslogs-region`. To deploy
> elsewhere, change `AWS_REGION` above **and** replace the region in both files:
>
> ```bash
> sed -i "s/us-east-2/$AWS_REGION/g" aws/taskdef-backend.json aws/taskdef-frontend.json
> ```
>
> Keep it in step with `AWS_REGION` in `.github/workflows/aws.yml`, which is also `us-east-2`:
> the workflow pushes to that region's registry, and a mismatch means ECS pulls from a registry
> the deploy never writes to. Nothing else in the repo is region-locked.

---

## 1. Networking

Recommended layout — three subnet tiers across two Availability Zones:

```
VPC (10.0.0.0/16)
├── Public subnets        (2 AZs)  → Application Load Balancer, NAT Gateway
├── Private app subnets   (2 AZs)  → ECS Fargate tasks (backend, frontend, ingest)
└── Private data subnets  (2 AZs)  → RDS PostgreSQL, ElastiCache Redis
```

Security groups — each references the one above it, never a CIDR:

```
Internet ──443──► SG_ALB
SG_ALB   ──8000──► SG_ECS   (backend tasks)
SG_ALB   ──80────► SG_ECS   (frontend tasks)
SG_ECS   ──5432──► SG_DATA  (RDS)
SG_ECS   ──6379──► SG_DATA  (ElastiCache)
```

* `SG_ALB` inbound: 443 (and 80 only to redirect to 443) from `0.0.0.0/0`.
* `SG_ECS` inbound: 8000 and 80 **from `SG_ALB` only**.
* `SG_DATA` inbound: 5432 and 6379 **from `SG_ECS` only**.
* **RDS and ElastiCache must never be publicly accessible** — no public subnet, no public IP,
  `--no-publicly-accessible`.

Tasks in private subnets need a **NAT Gateway** to reach ECR, OpenAI, Guardian, NYT and Tavily
(≈$32/mo). The cheaper alternative is to place tasks in public subnets with
`assignPublicIp=ENABLED` and no NAT; the security groups above still keep them unreachable from
the internet. VPC endpoints for ECR/S3/CloudWatch/SSM are a third option that removes egress
cost for the AWS calls but not for the external APIs.

## 2. ECR repositories

```bash
aws ecr create-repository --repository-name guardian-backend  --image-scanning-configuration scanOnPush=true
aws ecr create-repository --repository-name guardian-frontend --image-scanning-configuration scanOnPush=true
```

Repository names are set per matrix entry (`ecr_repository`) in `.github/workflows/aws.yml`.

## 3. Data layer (RDS + ElastiCache)

**RDS PostgreSQL with pgvector** — engine 15.4+/16 supports `CREATE EXTENSION vector`:

```bash
aws rds create-db-instance \
  --db-instance-identifier guardian-db \
  --engine postgres --engine-version 16.4 \
  --db-instance-class db.t4g.micro \
  --allocated-storage 20 --storage-type gp3 \
  --master-username guardian --master-user-password '<STRONG_PASSWORD>' \
  --db-name guardian_news \
  --no-publicly-accessible \
  --db-subnet-group-name <PRIVATE_DATA_SUBNET_GROUP> \
  --vpc-security-group-ids <SG_DATA>
```

**ElastiCache Redis:**

```bash
aws elasticache create-cache-cluster \
  --cache-cluster-id guardian-redis \
  --engine redis --cache-node-type cache.t4g.micro \
  --num-cache-nodes 1 \
  --cache-subnet-group-name <PRIVATE_DATA_SUBNET_GROUP> \
  --security-group-ids <SG_DATA>
```

The backend creates the `vector` extension and its tables on startup, so no migration step is
needed — the RDS master user has `CREATE EXTENSION` privilege. Application code is unchanged:
it reads `DATABASE_URL` and `REDIS_URL` exactly as it does under Docker Compose.

## 4. Secrets in SSM Parameter Store

Secrets exist **only** in Parameter Store. They are never in the repo, the Dockerfiles, the
images, the workflow, or the task definition JSON — the task definitions carry parameter
ARNs, and ECS injects the values as environment variables at task start.

```bash
aws ssm put-parameter --name /guardian-app/GUARDIAN_API_KEY --type SecureString --value '<key>'
aws ssm put-parameter --name /guardian-app/NYT_API_KEY      --type SecureString --value '<key>'
aws ssm put-parameter --name /guardian-app/TAVILY_API_KEY   --type SecureString --value '<key>'
aws ssm put-parameter --name /guardian-app/OPENAI_API_KEY   --type SecureString --value '<key>'
aws ssm put-parameter --name /guardian-app/DATABASE_URL     --type SecureString \
  --value 'postgresql+asyncpg://guardian:<STRONG_PASSWORD>@<RDS_ENDPOINT>:5432/guardian_news'
aws ssm put-parameter --name /guardian-app/REDIS_URL        --type SecureString \
  --value 'redis://<ELASTICACHE_ENDPOINT>:6379/0'
```

> Every parameter referenced by a task definition must exist, or the task fails to start with
> `ResourceInitializationError`. NYT and Tavily are optional features — if you are not using
> them, **delete those two entries from the `secrets` array** in `aws/taskdef-backend.json`
> rather than creating empty parameters (SSM rejects empty values).

Secrets Manager works identically: put the secret ARN in `valueFrom` (append `:key::` to pick
one JSON key) and grant `secretsmanager:GetSecretValue` instead of `ssm:GetParameters`.

## 5. IAM roles

```bash
# Execution role — ECS agent: pulls images, reads SSM parameters, writes logs
aws iam create-role --role-name guardianEcsExecutionRole \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name guardianEcsExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam put-role-policy --role-name guardianEcsExecutionRole --policy-name ReadGuardianSecrets \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"ssm:GetParameters\"],\"Resource\":\"arn:aws:ssm:$AWS_REGION:$ACCOUNT_ID:parameter/guardian-app/*\"}]}"

# Task role — what the application itself may call (nothing AWS-side today)
aws iam create-role --role-name guardianEcsTaskRole \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
```

Other roles created later in this guide:

| Role | Trusted by | Needs |
|---|---|---|
| `guardianEcsExecutionRole` | `ecs-tasks.amazonaws.com` | `AmazonECSTaskExecutionRolePolicy` + `ssm:GetParameters` on `/guardian-app/*` |
| `guardianEcsTaskRole` | `ecs-tasks.amazonaws.com` | nothing today — the app makes no AWS API calls |
| GitHub Actions deployer | an IAM user (or an OIDC role — see §10) | ECR push set + `sts:GetCallerIdentity` + `ecs:RegisterTaskDefinition`, `ecs:DescribeServices`, `ecs:UpdateService` + `iam:PassRole` for the two task roles |
| `guardianSchedulerRole` | `scheduler.amazonaws.com` | `ecs:RunTask` on the backend task definition + `iam:PassRole` for `guardianEcsExecutionRole` and `guardianEcsTaskRole` — **not needed** while ingestion runs in-process (§9); create it only if you reinstate EventBridge Scheduler |

The scheduler role policy in full — only if you reinstate the scheduler (§9):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": "ecs:RunTask", "Resource": "arn:aws:ecs:us-east-2:<ACCOUNT_ID>:task-definition/guardian-backend:*" },
    { "Effect": "Allow", "Action": "iam:PassRole", "Resource": [
        "arn:aws:iam::<ACCOUNT_ID>:role/guardianEcsExecutionRole",
        "arn:aws:iam::<ACCOUNT_ID>:role/guardianEcsTaskRole"
      ],
      "Condition": { "StringLike": { "iam:PassedToService": "ecs-tasks.amazonaws.com" } } }
  ]
}
```

## 6. Cluster, CloudWatch log groups, task definitions

```bash
aws ecs create-cluster --cluster-name guardian-cluster \
  --capacity-providers FARGATE --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1

aws logs create-log-group --log-group-name /ecs/guardian-backend
aws logs create-log-group --log-group-name /ecs/guardian-frontend
aws logs put-retention-policy --log-group-name /ecs/guardian-backend  --retention-in-days 30
aws logs put-retention-policy --log-group-name /ecs/guardian-frontend --retention-in-days 30
```

Both task definitions use the **`awslogs`** driver into those groups. The backend emits
structured JSON logs with request ids, so CloudWatch Logs Insights can query them directly:

```
fields @timestamp, event, route, latency_ms, request_id | filter event = "chat_complete" | sort @timestamp desc
```

Register the task definitions. The region is already `us-east-2`; substitute your account id
(the files ship with an `<ACCOUNT_ID>` placeholder so no account id is committed):

```bash
sed -i "s/<ACCOUNT_ID>/$ACCOUNT_ID/g" aws/taskdef-backend.json aws/taskdef-frontend.json
# deploying outside us-east-2? also: sed -i "s/us-east-2/$AWS_REGION/g" aws/taskdef-*.json
# also replace <YOUR_DOMAIN> in taskdef-backend.json with the public site origin (CORS)
aws ecs register-task-definition --cli-input-json file://aws/taskdef-backend.json
aws ecs register-task-definition --cli-input-json file://aws/taskdef-frontend.json
```

Both are `FARGATE` / `awsvpc`; the backend exposes **8000** (Gunicorn managing Uvicorn workers)
and the frontend **80** (nginx serving the SPA build). Neither contains a PostgreSQL or Redis
sidecar — those are RDS and ElastiCache. The backend sets **`INGEST_ENABLED=true`** and dedupes across replicas with a Redis tick lock: see §9.

The `image` value in each file is a bootstrap placeholder. The deploy workflow overwrites it on
every run with the immutable commit-SHA tag and registers a new task definition revision, so
this manual registration is only needed once — before the services can be created in §8.

## 7. Application Load Balancer

One ALB, path-based routing: `/api/*` → backend target group (8000), everything else →
frontend target group (80).

```bash
aws elbv2 create-load-balancer --name guardian-alb --type application \
  --subnets <PUBLIC_SUBNET_A> <PUBLIC_SUBNET_B> --security-groups <SG_ALB>

aws elbv2 create-target-group --name guardian-tg-backend --protocol HTTP --port 8000 \
  --vpc-id <VPC_ID> --target-type ip \
  --health-check-path /api/health --health-check-interval-seconds 30

aws elbv2 create-target-group --name guardian-tg-frontend --protocol HTTP --port 80 \
  --vpc-id <VPC_ID> --target-type ip --health-check-path /

# HTTPS listener — request or import a certificate in ACM first
aws elbv2 create-listener --load-balancer-arn <ALB_ARN> --protocol HTTPS --port 443 \
  --certificates CertificateArn=<ACM_CERT_ARN> \
  --default-actions Type=forward,TargetGroupArn=<TG_FRONTEND_ARN>

aws elbv2 create-rule --listener-arn <HTTPS_LISTENER_ARN> --priority 10 \
  --conditions Field=path-pattern,Values='/api/*' \
  --actions Type=forward,TargetGroupArn=<TG_BACKEND_ARN>

# Port 80 → 443 redirect
aws elbv2 create-listener --load-balancer-arn <ALB_ARN> --protocol HTTP --port 80 \
  --default-actions '[{"Type":"redirect","RedirectConfig":{"Protocol":"HTTPS","Port":"443","StatusCode":"HTTP_301"}}]'
```

**Backend health check: `/api/health`.** It reports the database, the `vector` extension, the
cache and each publisher, so an unhealthy dependency fails the target check and blocks a bad
rollout.

**`/api/*` is public — two settings decide what that costs.** The listener rule sends every
`/api/*` path to the backend, so anything mounted there is reachable by anyone who knows the
URL.

* **`TRUSTED_PROXY_HOPS=1`** tells the rate limiter that exactly one proxy (this ALB) sits in
  front. The ALB *appends* the address it saw, so the rightmost `X-Forwarded-For` entry is the
  real client and everything to its left was written by the caller. Reading the leftmost — the
  previous behaviour — let anyone send a different `X-Forwarded-For` per request and get a fresh
  rate-limit bucket every time, which made both limiters decorative. Raise this to `2` if you
  put CloudFront in front of the ALB.
* **`ADMIN_API_KEY`** controls `/api/rag/*` and `/api/intent`. Those spend embeddings, publisher
  quota and LLM calls, and nothing in the UI calls them. With `ENVIRONMENT=production` and no
  key set they return `404` — which is the safe default and needs no parameter created. Only
  add the secret if you want the tooling reachable:

```bash
aws ssm put-parameter --name /guardian/admin-api-key --type SecureString \
  --value "$(openssl rand -hex 24)"
# then add to taskdef-backend.json "secrets":
#   {"name": "ADMIN_API_KEY", "valueFrom": "arn:aws:ssm:<REGION>:<ACCOUNT>:parameter/guardian/admin-api-key"}
# and call with:  curl -H "X-Admin-Key: <value>" https://<YOUR_DOMAIN>/api/rag/retrieve ...
```

**SSE streaming — raise the idle timeout.** `/api/chat` streams tokens over Server-Sent Events;
the ALB's default 60 s idle timeout cuts long answers off mid-stream. Set **300 seconds**:

```bash
aws elbv2 modify-load-balancer-attributes --load-balancer-arn <ALB_ARN> \
  --attributes Key=idle_timeout.timeout_seconds,Value=300
```

Also give the backend target group a deregistration delay long enough for in-flight streams to
finish during a rolling deploy:

```bash
aws elbv2 modify-target-group-attributes --target-group-arn <TG_BACKEND_ARN> \
  --attributes Key=deregistration_delay.timeout_seconds,Value=120
```

**DNS:** point the domain at the ALB — a Route 53 ALIAS A record, or a CNAME to the ALB DNS
name with any other registrar (root domains need ALIAS/ANAME support or a `www` redirect).

## 8. ECS services

```bash
aws ecs create-service --cluster guardian-cluster --service-name guardian-backend \
  --task-definition guardian-backend --desired-count 2 --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<PRIVATE_APP_SUBNET_A>,<PRIVATE_APP_SUBNET_B>],securityGroups=[<SG_ECS>],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=<TG_BACKEND_ARN>,containerName=backend,containerPort=8000" \
  --health-check-grace-period-seconds 60 \
  --deployment-configuration "minimumHealthyPercent=100,maximumPercent=200"

aws ecs create-service --cluster guardian-cluster --service-name guardian-frontend \
  --task-definition guardian-frontend --desired-count 2 --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<PRIVATE_APP_SUBNET_A>,<PRIVATE_APP_SUBNET_B>],securityGroups=[<SG_ECS>],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=<TG_FRONTEND_ARN>,containerName=frontend,containerPort=80"
```

`assignPublicIp=DISABLED` requires the NAT Gateway from §1. Without one, use public subnets and
`assignPublicIp=ENABLED` — the security groups still block inbound traffic that is not from the
ALB.

## 9. Scheduled ingestion (the in-process loop)

Ingestion runs **inside the backend service**: `INGEST_ENABLED=true` in
`aws/taskdef-backend.json`, one desk every `INGEST_INTERVAL_MINUTES` (7). There is no
EventBridge schedule and no one-shot task — see below for why that approach was dropped.

Every replica starts the loop, and a short-lived **Redis lock** in `app/tasks/scheduler.py` means
exactly one performs each tick, so publisher usage is not multiplied by the replica count. The
rotation is derived from the clock rather than from in-process state, so both replicas resolve the
same desk for a tick and a deploy resumes the cycle in place instead of restarting it.

**The arithmetic.** One desk per tick every 7 minutes is 1,440/7 ≈ **205 requests/day per
publisher**, and walks all 13 desks (`ingest_sections()`) in 91 minutes. The ceiling that binds is
not the plan's 500/day but `DAILY_BUDGET - INTERACTIVE_RESERVE` — **350** for the Guardian and the
NYT — because that is where `app/sources/quota.py` cuts background work off to leave readers their
share. Past it the sweep does not slow down, it stops for the rest of the UTC day. Keep
`(1440 / INGEST_INTERVAL_MINUTES) × INGEST_SECTIONS_PER_TICK` under 350 when tuning; two desks
every 7 minutes is 411 and would truncate the day. TheNewsAPI is metered separately and 205 sits
well inside the ~1,500/day its own budget leaves the sweep.

**Verifying it.** Runs appear in the `/ecs/guardian-backend` log group. Filter for `ingest`:
`scheduled_ingest_tick` and `scheduled_ingest_section` every 7 minutes is the healthy state.
`scheduled ingestion disabled` means `INGEST_ENABLED` is not `true`; a stream of those and nothing
else is the failure this section exists to prevent.

### Why not EventBridge Scheduler

An earlier version of this document specified a one-shot Fargate task on
`rate(30 minutes)`, on the reasoning that cron work tied to long-running replicas stops whenever
the service scales to zero. That schedule was never created in the account, so production simply
did not ingest — the index grew only from the incidental on-the-fly indexing that freshness
questions trigger, and the gap went unnoticed because nothing reports a scheduler that isn't
there.

It is also the wrong shape for this workload. Invoking the module directly sweeps **all 13** desks
in one run rather than a rotating slice, so the interval multiplies by 13: `rate(30 minutes)` is
624 requests/day per publisher and `rate(7 minutes)` would be 2,674 — both past the 350 ceiling.
Reaching a short cadence that way would mean teaching the CLI entrypoint to take a rotating slice,
which is precisely what the in-process loop already does.

If you do reinstate it, keep the two mutually exclusive: both spend from the same daily counter,
and running them together doubles consumption while each looks correctly configured on its own.

## 10. The deploy workflow

Deployment is [`.github/workflows/aws.yml`](../.github/workflows/aws.yml) — already in the repo.
All that remains is giving it credentials.

**a. Deployer IAM policy.** Create a policy with exactly what the workflow does — push images,
register a task definition, update a service:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*" },
    { "Effect": "Allow",
      "Action": ["ecr:BatchCheckLayerAvailability","ecr:InitiateLayerUpload","ecr:UploadLayerPart","ecr:CompleteLayerUpload","ecr:PutImage"],
      "Resource": [
        "arn:aws:ecr:us-east-2:<ACCOUNT_ID>:repository/guardian-backend",
        "arn:aws:ecr:us-east-2:<ACCOUNT_ID>:repository/guardian-frontend"
      ] },
    { "Effect": "Allow", "Action": "ecs:RegisterTaskDefinition", "Resource": "*" },
    { "Effect": "Allow",
      "Action": ["ecs:DescribeServices","ecs:UpdateService"],
      "Resource": [
        "arn:aws:ecs:us-east-2:<ACCOUNT_ID>:service/guardian-cluster/guardian-backend",
        "arn:aws:ecs:us-east-2:<ACCOUNT_ID>:service/guardian-cluster/guardian-frontend"
      ] },
    { "Effect": "Allow", "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::<ACCOUNT_ID>:role/guardianEcsExecutionRole",
        "arn:aws:iam::<ACCOUNT_ID>:role/guardianEcsTaskRole"
      ],
      "Condition": { "StringLike": { "iam:PassedToService": "ecs-tasks.amazonaws.com" } } }
  ]
}
```

`ecs:RegisterTaskDefinition` cannot be scoped to a resource — AWS does not support it. The
`iam:PassRole` entries are what stop that from being an escalation path: the workflow can only
register task definitions that run as those two roles.

**b. Credentials — pick one.**

*OIDC (recommended, no long-lived key):* create an IAM role trusting GitHub's OIDC provider,
attach the policy above, and swap the credentials step in `aws.yml` for:

```yaml
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::<ACCOUNT_ID>:role/guardianGitHubDeployRole
          aws-region: ${{ env.AWS_REGION }}
```

and add `id-token: write` to the workflow's `permissions:` block. Scope the role's trust policy
to this repository:

```json
"Condition": { "StringEquals": {
  "token.actions.githubusercontent.com:sub": "repo:AJKumarReddy/Agentic-News-app:ref:refs/heads/main" } }
```

*Access keys (what the workflow ships with):* create an IAM user with the policy above, then add
its key as repository secrets **`AWS_ACCESS_KEY_ID`** and **`AWS_SECRET_ACCESS_KEY`** under
Settings → Secrets and variables → Actions. Rotate them periodically.

**c. Protect the environment (optional).** The deploy job declares `environment: production`.
Adding required reviewers to that environment in Settings → Environments turns every deploy into
an approval gate.

**How a deploy runs.** Push to `main` → `test.yml` runs as a reusable workflow (backend pytest,
frontend vitest, both Docker builds); a failure stops the deploy. Then the matrix job runs once
per service: build the image from its own context, push it to ECR under the commit SHA, resolve
`<ACCOUNT_ID>` in the task definition from `sts:GetCallerIdentity`, render the new image into it,
register the revision, and update the service with `wait-for-service-stability: true`. New tasks
must pass the target-group health check before the old ones drain.

Because the task definition is rendered from the JSON in this repo, **editing
`aws/taskdef-*.json` and pushing is how you change environment variables or secret ARNs** — no
console step.

## 11. Verify

```bash
curl -sf https://<YOUR_DOMAIN>/api/health | jq
bash scripts/health-check.sh https://<YOUR_DOMAIN>
aws logs tail /ecs/guardian-backend --follow
```

## Troubleshooting

| Symptom | Check |
|---|---|
| Tasks go `PROVISIONING` → `STOPPED` | Stopped reason in the ECS console: usually no route to ECR (missing NAT/public IP) or `ResourceInitializationError` reading SSM (execution role policy, or a parameter that doesn't exist) |
| Target group unhealthy | Backend takes ~20 s to boot; the 60 s grace period covers it. Check `/ecs/guardian-backend` in CloudWatch |
| `"database": {"connected": false}` in `/api/health` | `SG_DATA` must allow 5432 from `SG_ECS`; verify the `DATABASE_URL` parameter and that RDS is in the same VPC |
| Chat stream cuts off mid-answer | ALB idle timeout — set it to 300 s (§7) |
| Index stops updating | Filter `/ecs/guardian-backend` for `ingest`. `scheduled_ingest_tick` every 7 minutes is healthy; `scheduled ingestion disabled` means `INGEST_ENABLED` is not `true`; nothing at all means the tasks are not running |
| Index updates for part of the day, then stops | The sweep hit `DAILY_BUDGET - INTERACTIVE_RESERVE` and is refused until UTC midnight — lengthen `INGEST_INTERVAL_MINUTES` or raise that publisher's budget (§9) |
| Ingestion runs twice per tick | Redis is unreachable, so the tick lock fails open and every replica ingests. Check `REDIS_URL` and `SG_DATA` |
| Deploy job hangs on "service stability" | ECS service Events tab — failing health checks roll the deployment back |
| Deploy fails on `RegisterTaskDefinition` | Deployer policy missing `ecs:RegisterTaskDefinition` or `iam:PassRole` for the two task roles (§10) |
| Deploy fails with an invalid-ARN error | `<ACCOUNT_ID>` not substituted — the workflow's "Resolve account id" step needs `sts:GetCallerIdentity` |
| CORS errors in the browser | `FRONTEND_URL` in the backend task definition must match the public origin exactly |
