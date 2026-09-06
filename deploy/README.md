# AWS deployment

Production uses one HTTPS CloudFront address. Static frontend files are private in S3. CloudFront routes `/api/*`, `/health`, and `/cmpdi/workbench/*` to the EC2 origin. The EC2 host runs PostgreSQL, FastAPI, the private analytics workbench, and Nginx as native system services. The durable `Data/cil` tree is a versioned S3 bucket mounted at `/srv/cil-data`; OCR and workbench scratch files live on the encrypted EBS volume.

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

The script creates or updates the AWS stack, stores the production environment in Secrets Manager, syncs the current `Data/cil` tree into the versioned data bucket, migrates the local SQLite workflow catalog into PostgreSQL, ships the current checkout to EC2 through the private frontend bucket, starts the native services, publishes the frontend to S3, and invalidates CloudFront. It prints the final URL and S3 data root.

No SSH port is opened. Use AWS Systems Manager Session Manager for host access. The EC2 HTTP port requires a secret header that CloudFront adds, so direct origin requests are rejected by Nginx.

## Operations

Run the same deployment command for later releases. PostgreSQL and processing data live on the encrypted EBS volume. S3 object versioning protects uploaded and generated report objects. Before replacing the EC2 instance, back up the PostgreSQL volume with `pg_dump`; the S3 data bucket is retained if the stack is deleted.

## Manual EC2 setup without Docker

After the instance is created, connect through Systems Manager and clone the repository into `/opt/cil-platform`. Install Python 3.12, Node.js 22, PostgreSQL 16, Nginx, Tesseract, `s3fs`, and the AWS CLI. Create `/opt/cil-platform/.env.production` from Secrets Manager, mount the data bucket at `/srv/cil-data`, then create a Python virtual environment and install `backend/requirements.txt` and `data-analyser/requirements.txt`.

Run the API with Uvicorn on `127.0.0.1:8000`, run `integration/run_data_formulator.py` on `127.0.0.1:5567`, and configure Nginx to proxy `/api/` to port 8000 and `/cmpdi/workbench/` to port 5567. Build the portal and workbench static assets with their normal npm build commands and sync the portal build to the frontend bucket. Enable all three processes with systemd so they restart after reboots. Keep PostgreSQL bound to localhost and allow only CloudFront-origin traffic through the EC2 security group.

The Docker deployment files remain as a rollback path, but do not run both modes at the same time on one instance because they use the same ports.

For a custom domain, add an ACM certificate in `us-east-1`, attach aliases and that certificate to the CloudFront distribution, then change `CORS_ORIGINS` in `.env.production` to the final HTTPS origin and redeploy.
