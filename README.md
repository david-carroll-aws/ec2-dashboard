# EC2 Dashboard
A serverless Lambda that powers a live EC2 dashboard — listing every instance in the account, showing per-instance detail, pulling CloudWatch metrics, and letting you **start / stop / reboot** instances directly from the browser.

Built as a portfolio project to explore the EC2 API, CloudWatch metrics, and a single-Lambda REST-style router.

http://davidcarroll.cloud/index.html?service=ec2

<img width="1315" height="583" alt="Screenshot 2026-10-03 001505" src="https://github.com/user-attachments/assets/a6a5e379-362b-4e38-a8f9-8088c1308170" />
<img width="1314" height="576" alt="Screenshot 2026-10-03 001538" src="https://github.com/user-attachments/assets/bb0fa253-ab47-474f-b870-6f9c9cdaa621" />
<img width="532" height="580" alt="Screenshot 2026-10-03 001801" src="https://github.com/user-attachments/assets/2982bfb8-9249-46f9-af48-105b7e759df1" />
<img width="527" height="279" alt="Screenshot 2026-10-03 001642" src="https://github.com/user-attachments/assets/95eced63-6e53-4c39-9367-7e7c3cb912e8" />
<img width="535" height="289" alt="Screenshot 2026-10-03 001656" src="https://github.com/user-attachments/assets/590354de-89b4-4b9c-87e5-ff120fcdb4d9" />


---

## Architecture

```
┌────────────────────┐
│   Browser          │  HTML dashboard (ec2dashboard.html)
│   (dashboard)      │  Renders instance list, detail view, action buttons
└─────────┬──────────┘
          │ GET  /ec2                    → list instances
          │ GET  /ec2/{id}               → instance detail + metrics
          │ POST /ec2/{id}/{action}      → start | stop | reboot
          ▼
┌────────────────────┐
│   API Gateway      │  HTTP API  ·  CORS enabled
└─────────┬──────────┘
          │ Lambda proxy
          ▼
┌────────────────────┐       ┌───────────────────────┐
│   Lambda           │──────▶│  EC2 API              │
│   (ec2-dashboard)  │       │  describe / start /   │
│   Python 3.12      │       │  stop / reboot        │
│                    │       └───────────────────────┘
│                    │       ┌───────────────────────┐
│                    │──────▶│  CloudWatch API       │
│                    │       │  get_metric_statistics│
│                    │◀──────│  (last 1 hour)        │
└────────────────────┘       └───────────────────────┘
```

One Lambda handles everything: routing, EC2 queries, CloudWatch metric fetches, and action dispatch. No database — every request hits AWS live.

---

## What It Does

| Endpoint                        | Method | Purpose                                        |
|---------------------------------|--------|------------------------------------------------|
| `/ec2`                          | GET    | List all instances (id, state, type, IP, AZ)   |
| `/ec2/{id}`                     | GET    | Full detail for one instance + recent metrics  |
| `/ec2/{id}/{action}`            | POST   | Start, stop, or reboot an instance             |

**Detail view includes:**
- Instance ID, state, type, public/private IPs
- Availability zone, VPC, subnet
- Launch time, AMI, key pair
- Security groups, attached volumes
- Tags (as a key/value map)
- **CloudWatch metrics** for the last hour:
  - `CPUUtilization` (Average, 5-min granularity)
  - `NetworkIn` (Sum)
  - `NetworkOut` (Sum)

Metrics are returned as time-series arrays suitable for charting in the frontend.

---

## Behind the Build

**Single Lambda, multiple routes.** Rather than deploying three Lambdas (list, detail, action), everything lives in one handler that branches on the HTTP method and path parameters. It's a small project — one function is easier to reason about than three, and cold-start cost is a non-issue when it's the same function serving every request.

**CloudWatch metrics without a schema.** `get_metric_statistics` returns datapoints in arbitrary order. The Lambda sorts by timestamp before returning, so the frontend can plot them directly without re-sorting. Small detail, but it means the browser code stays simpler.

**Action endpoints are the risky part.** The three mutating operations (`start`, `stop`, `reboot`) are gated behind a `POST` route with an action in the path, so the IAM policy can be scoped tightly — read-only actions on one set of resources, mutating actions on another. Worth being deliberate about when the Lambda can actually change infrastructure state.

---

## Stack

| Layer      | Technology                                    |
|------------|-----------------------------------------------|
| Frontend   | Static HTML + JS (renders lists, charts)      |
| Compute    | AWS Lambda (Python 3.12)                      |
| API        | Amazon API Gateway (HTTP API)                 |
| Data       | EC2 `describe_instances`, CloudWatch metrics  |
| IAM        | Scoped to `ec2:Describe*`, `ec2:Start*`, `ec2:Stop*`, `ec2:Reboot*`, `cloudwatch:GetMetricStatistics` |

---

## Deploying It Yourself

### 1. Deploy the Lambda

- Runtime: **Python 3.12**
- Handler: `lambda_function.lambda_handler`
- No external dependencies — `boto3` is included in the Lambda runtime, so no Docker, no zip, no layers. Paste the code inline in the console.

### 2. IAM permissions

The Lambda's execution role needs:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:RebootInstances",
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    }
  ]
}
```

⚠️ **Production note:** `Resource: "*"` is fine for a personal project, but for anything shared, scope `ec2:Start/Stop/Reboot` to specific instance ARNs to prevent accidental impact on the wrong machines.

### 3. API Gateway routes

Create an HTTP API with these three routes:

| Method | Path                    | Integration     |
|--------|-------------------------|-----------------|
| `GET`  | `/ec2`                  | this Lambda     |
| `GET`  | `/ec2/{id}`             | this Lambda     |
| `POST` | `/ec2/{id}/{action}`    | this Lambda     |

Enable CORS: origin `*` (or your frontend origin), methods `GET, POST, OPTIONS`, headers `Content-Type`.

The Lambda reads `event.pathParameters.id` and `event.pathParameters.action`, so the path parameters must be named exactly `id` and `action` in the route definition.

### 4. Frontend

Serve the accompanying HTML files from any static host (S3, Cloudflare Pages, etc.) and update the API URL to point at your API Gateway endpoint.

---

## Project Structure

```
/
├── README.md
├── lambda_function.py     ← this Lambda (list / detail / action handler)
├── ec2dashboard.html      ← main dashboard view
├── ec2array.html          ← instance list rendering
├── ec2data.html           ← data transformation helpers
└── ec2details.html        ← instance detail view
```

---

## 📌 Notes

- Every request hits the AWS APIs live — no caching, no database. Simple, but it means the dashboard is only as fresh as the last request.
- CloudWatch metrics have a ~5-minute publishing delay, so the "last hour" window reflects data up to a few minutes ago.
- Action endpoints (`start` / `stop` / `reboot`) mutate real infrastructure. Treat with care.
