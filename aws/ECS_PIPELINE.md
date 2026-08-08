# AWS-Native CI/CD: GitHub → CodePipeline → CodeBuild → ECR → ECS Fargate

This guide deploys the Guardian AI News Assistant on serverless containers with a fully managed pipeline. It replaces the EC2 + GitHub Actions flow (which remains available — see README). Pushing to `main` automatically builds both Docker images, pushes them to ECR, and rolls them out to ECS with zero downtime.

```
GitHub (main) ──► CodePipeline ──► CodeBuild ──► ECR ──► ECS (Fargate)
                   (source)      (buildspec.yml)          │
                                                          ▼
                              ALB ──► frontend service (nginx :80)
                               └────► backend service (FastAPI :8000, path /api/*)
                                        │
                              RDS PostgreSQL (pgvector) + ElastiCache Redis
                                        │
                              Secrets from SSM Parameter Store
```

**Cost note:** this stack (ALB + 2 Fargate services + RDS + ElastiCache) runs roughly $80–120/month minimum — the single-EC2 docker-compose path in the README is far cheaper. Choose Fargate when you want managed scaling, rolling deploys, and no server maintenance.

Set two shell variables used throughout (run in CloudShell or a configured terminal):

```bash
export AWS_REGION=us-east-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
```

## 1. ECR repositories

```bash
aws ecr create-repository --repository-name guardian-backend  --image-scanning-configuration scanOnPush=true
aws ecr create-repository --repository-name guardian-frontend --image-scanning-configuration scanOnPush=true
```

## 2. Data layer (replaces the postgres/redis containers)

**RDS PostgreSQL with pgvector** (engine 15.4+/16 supports `CREATE EXTENSION vector`):

```bash
aws rds create-db-instance \
  --db-instance-identifier guardian-db \
  --engine postgres --engine-version 16.4 \
  --db-instance-class db.t4g.micro \
  --allocated-storage 20 --storage-type gp3 \
  --master-username guardian --master-user-password '<STRONG_PASSWORD>' \
  --db-name guardian_news \
  --no-publicly-accessible \
  --vpc-security-group-ids <SG_DATABASE>
```

**ElastiCache Redis:**

```bash
aws elasticache create-cache-cluster \
  --cache-cluster-id guardian-redis \
  --engine redis --cache-node-type cache.t4g.micro \
  --num-cache-nodes 1 \
  --security-group-ids <SG_DATABASE>
```

Security groups: `SG_DATABASE` must allow inbound 5432 and 6379 **only from the ECS tasks' security group**. Nothing public. The backend creates the `vector` extension and tables automatically at startup (the RDS master user has that privilege).

## 3. Secrets in SSM Parameter Store

The task definition injects these as container secrets — they never appear in the repo, images, or task definition JSON in plaintext:

```bash
aws ssm put-parameter --name /guardian-app/GUARDIAN_API_KEY --type SecureString --value '<key>'
aws ssm put-parameter --name /guardian-app/OPENAI_API_KEY   --type SecureString --value '<key>'
aws ssm put-parameter --name /guardian-app/DATABASE_URL     --type SecureString \
  --value 'postgresql+asyncpg://guardian:<STRONG_PASSWORD>@<RDS_ENDPOINT>:5432/guardian_news'
aws ssm put-parameter --name /guardian-app/REDIS_URL        --type SecureString \
  --value 'redis://<ELASTICACHE_ENDPOINT>:6379/0'
```

## 4. IAM roles

```bash
# Execution role: pulls images, reads SSM secrets, writes logs
aws iam create-role --role-name guardianEcsExecutionRole \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name guardianEcsExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam put-role-policy --role-name guardianEcsExecutionRole --policy-name ReadGuardianSecrets \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"ssm:GetParameters\"],\"Resource\":\"arn:aws:ssm:$AWS_REGION:$ACCOUNT_ID:parameter/guardian-app/*\"}]}"

# Task role: what the app itself may call (nothing AWS-side needed today)
aws iam create-role --role-name guardianEcsTaskRole \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
```

## 5. ECS cluster, log groups, task definitions

```bash
aws ecs create-cluster --cluster-name guardian-cluster \
  --capacity-providers FARGATE --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1

aws logs create-log-group --log-group-name /ecs/guardian-backend
aws logs create-log-group --log-group-name /ecs/guardian-frontend

# Fill in <ACCOUNT_ID> and <REGION> inside both files first
sed -i "s/<ACCOUNT_ID>/$ACCOUNT_ID/g; s/<REGION>/$AWS_REGION/g" aws/taskdef-backend.json aws/taskdef-frontend.json
aws ecs register-task-definition --cli-input-json file://aws/taskdef-backend.json
aws ecs register-task-definition --cli-input-json file://aws/taskdef-frontend.json
```

## 6. Application Load Balancer

One ALB, path-based routing: `/api/*` → backend target group (port 8000), everything else → frontend target group (port 80).

```bash
aws elbv2 create-load-balancer --name guardian-alb --type application \
  --subnets <PUBLIC_SUBNET_A> <PUBLIC_SUBNET_B> --security-groups <SG_ALB>

aws elbv2 create-target-group --name guardian-tg-backend --protocol HTTP --port 8000 \
  --vpc-id <VPC_ID> --target-type ip \
  --health-check-path /api/health --health-check-interval-seconds 30

aws elbv2 create-target-group --name guardian-tg-frontend --protocol HTTP --port 80 \
  --vpc-id <VPC_ID> --target-type ip --health-check-path /

# HTTPS listener (request/import a certificate in ACM first)
aws elbv2 create-listener --load-balancer-arn <ALB_ARN> --protocol HTTPS --port 443 \
  --certificates CertificateArn=<ACM_CERT_ARN> \
  --default-actions Type=forward,TargetGroupArn=<TG_FRONTEND_ARN>

aws elbv2 create-rule --listener-arn <HTTPS_LISTENER_ARN> --priority 10 \
  --conditions Field=path-pattern,Values='/api/*' \
  --actions Type=forward,TargetGroupArn=<TG_BACKEND_ARN>
```

**SSE streaming:** raise the ALB idle timeout so long chat streams aren't cut off:

```bash
aws elbv2 modify-load-balancer-attributes --load-balancer-arn <ALB_ARN> \
  --attributes Key=idle_timeout.timeout_seconds,Value=300
```

`SG_ALB` allows 80/443 from the internet; the ECS tasks' security group allows 8000 and 80 **only from SG_ALB**.

DNS: in Hostinger, point `mydomain.com` (and/or `api.mydomain.com`) at the ALB with a **CNAME** to the ALB DNS name (root domains need ALIAS support or a `www` redirect; with Route 53 you'd use an ALIAS A record).

## 7. ECS services

```bash
aws ecs create-service --cluster guardian-cluster --service-name guardian-backend \
  --task-definition guardian-backend --desired-count 1 --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<PRIVATE_SUBNET_A>,<PRIVATE_SUBNET_B>],securityGroups=[<SG_TASKS>],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=<TG_BACKEND_ARN>,containerName=backend,containerPort=8000" \
  --health-check-grace-period-seconds 60

aws ecs create-service --cluster guardian-cluster --service-name guardian-frontend \
  --task-definition guardian-frontend --desired-count 1 --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<PRIVATE_SUBNET_A>,<PRIVATE_SUBNET_B>],securityGroups=[<SG_TASKS>],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=<TG_FRONTEND_ARN>,containerName=frontend,containerPort=80"
```

(`assignPublicIp=ENABLED` lets tasks in public subnets reach ECR/OpenAI/Guardian without a NAT gateway — the cheap option. For private subnets, add a NAT gateway and disable public IPs.)

## 8. The pipeline

**a. Connect GitHub** (one-time, needs a browser approval):

```bash
aws codestar-connections create-connection --provider-type GitHub --connection-name guardian-github
# Then: Console → Developer Tools → Connections → "guardian-github" → Update pending connection → authorize the AJKumarReddy/Agentic-News-app repo
```

**b. CodeBuild project** — Console → CodeBuild → Create project:
- Source: none needed here (CodePipeline provides it)
- Environment: Amazon Linux 2023 standard image, **Privileged = ON** (Docker builds)
- Buildspec: *use the repository's `buildspec.yml`*
- Service role: allow the ECR push actions listed at the top of `buildspec.yml`

**c. CodePipeline** — Console → CodePipeline → Create pipeline:
1. **Source stage**: connection `guardian-github`, repo `AJKumarReddy/Agentic-News-app`, branch `main`, output artifact `SourceOutput`.
2. **Build stage**: the CodeBuild project above, output artifact `BuildOutput`.
3. **Deploy stage** with **two actions**, both provider *Amazon ECS*:
   - `deploy-backend`: cluster `guardian-cluster`, service `guardian-backend`, image definitions file `imagedefinitions-backend.json`, input `BuildOutput`
   - `deploy-frontend`: cluster `guardian-cluster`, service `guardian-frontend`, image definitions file `imagedefinitions-frontend.json`, input `BuildOutput`

Every push to `main` now triggers: build → ECR push → rolling ECS deployment (new tasks must pass the `/api/health` target-group check before old tasks drain).

## 9. Disable the GitHub Actions EC2 deploy (optional)

If Fargate becomes your only deployment target, delete `.github/workflows/deploy.yml` or scope it to a tag. Keep `test.yml` — CodeBuild builds images but doesn't run the test suites; GitHub Actions remains your test gate on every push/PR.

## 10. Scheduled ingestion on ECS

Replace the EC2 cron with a scheduled Fargate task:

```bash
aws scheduler create-schedule --name guardian-ingest --schedule-expression "rate(30 minutes)" \
  --flexible-time-window Mode=OFF \
  --target '{"Arn":"arn:aws:ecs:'$AWS_REGION':'$ACCOUNT_ID':cluster/guardian-cluster","RoleArn":"arn:aws:iam::'$ACCOUNT_ID':role/guardianSchedulerRole","EcsParameters":{"TaskDefinitionArn":"guardian-backend","LaunchType":"FARGATE","NetworkConfiguration":{"awsvpcConfiguration":{"Subnets":["<PRIVATE_SUBNET_A>"],"SecurityGroups":["<SG_TASKS>"],"AssignPublicIp":"ENABLED"}}},"Input":"{\"containerOverrides\":[{\"name\":\"backend\",\"command\":[\"python\",\"-m\",\"app.tasks.ingest_recent\"]}]}"}'
```

(`guardianSchedulerRole` needs `ecs:RunTask` + `iam:PassRole` for the two task roles.)

## Troubleshooting

| Symptom | Check |
|---|---|
| Tasks stuck `PROVISIONING`→`STOPPED` | Stopped reason in ECS console: usually can't pull image (no route to ECR — public IP/NAT) or can't read SSM parameters (execution role policy) |
| Target group unhealthy | Backend takes ~20s to boot; grace period 60s is set. Check `/ecs/guardian-backend` logs in CloudWatch |
| `database "connected": false` in `/api/health` | SG_DATABASE must allow 5432 from SG_TASKS; verify DATABASE_URL parameter |
| Chat stream cuts off | ALB idle timeout (step 6) |
| Pipeline deploy hangs | Service events tab — usually failing health checks roll back the deployment |
