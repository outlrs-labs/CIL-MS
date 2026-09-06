# AWS deployment

Production uses one HTTPS CloudFront address. Static frontend files are private in S3. CloudFront routes `/api/*`, `/health`, and `/cmpdi/workbench/*` to the EC2 edge container. The EC2 host runs the API, private analytics workbench, and PostgreSQL with Docker Compose. The durable `Data/cil` tree is a versioned S3 bucket mounted at `/srv/cil-data`; OCR and workbench scratch files use an EC2 Docker volume.

## Prerequisites

- An AWS account with permission to create CloudFormation, IAM, S3, CloudFront, EC2, Secrets Manager, and Systems Manager resources.
- AWS CLI authenticated on the deployment computer.
- Supabase migrations in `supabase/migrations` already applied.
- `.env.production`, copied from `.env.production.example`, with Supabase and application secrets filled in. Generate `DF_BRIDGE_SECRET`, `POSTGRES_PASSWORD`, and `ORIGIN_VERIFY_HEADER` with `openssl rand -hex 32`.

## Deploy

```bash
cp .env.production.example .env.production
# Edit .env.production, then:
./deploy/aws-deploy.sh cil-platform ap-south-1
```

The script creates or updates the AWS stack, stores the production environment in Secrets Manager, syncs the current `Data/cil` tree into the versioned data bucket, ships the current checkout to EC2 through the private frontend bucket, starts the containers, publishes the frontend to S3, and invalidates CloudFront. It prints the final URL and S3 data root.

No SSH port is opened. Use AWS Systems Manager Session Manager for host access. The EC2 HTTP port requires a secret header that CloudFront adds, so direct origin requests are rejected by Nginx.

## Operations

Run the same deployment command for later releases. PostgreSQL and processing data live in named Docker volumes. S3 object versioning protects uploaded and generated report objects. Before replacing the EC2 instance, back up the PostgreSQL volume with `pg_dump`; the S3 data bucket is retained if the stack is deleted.

For a custom domain, add an ACM certificate in `us-east-1`, attach aliases and that certificate to the CloudFront distribution, then change `CORS_ORIGINS` in `.env.production` to the final HTTPS origin and redeploy.
