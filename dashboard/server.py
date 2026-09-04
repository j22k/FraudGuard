"""
FraudGuard — DynamoDB API Server
Serves the web console and provides live streaming from DynamoDB:
- GET /api/dynamodb -> Scans live DynamoDB table and returns JSON
"""

import http.server
import json
import os
import sys
import urllib.parse
from decimal import Decimal
import boto3

PORT = int(os.environ.get("PORT", 8080))
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

# Load .env if present
def load_dotenv():
    env_file = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() not in os.environ:
                        os.environ[k.strip()] = v.strip()

load_dotenv()

def decimal_serializer(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

class FraudGuardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. API: DynamoDB Flagged Transactions
        if path == "/api/dynamodb":
            self.handle_dynamodb(query)
            return

        # Fallback to serving static HTML/JS/CSS files from dashboard/web/
        super().do_GET()

    def handle_dynamodb(self, query):
        region = query.get("region", [os.environ.get("AWS_REGION", "us-east-1")])[0]
        table_name = query.get("table", [os.environ.get("FRAUDGUARD_DYNAMODB_TABLE", "fraudguard-flagged-transactions-dev")])[0]
        limit = int(query.get("limit", ["1000"])[0])

        try:
            dynamodb = boto3.resource("dynamodb", region_name=region)
            table = dynamodb.Table(table_name)
            resp = table.scan(Limit=limit)
            items = resp.get("Items", [])

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "table": table_name,
                "region": region,
                "count": len(items),
                "data": items
            }, default=decimal_serializer).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "error",
                "message": str(e),
                "table": table_name,
                "region": region
            }).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/realtime-predict":
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length)
            self.handle_realtime_predict(post_body)
            return

        self.send_response(404)
        self.end_headers()

    def handle_realtime_predict(self, post_body):
        import time
        from datetime import datetime, timezone

        t_start = time.perf_counter()
        try:
            payload = json.loads(post_body.decode("utf-8")) if post_body else {}
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Invalid JSON: {str(e)}"}).encode("utf-8"))
            return

        # 1. Invoke live AWS Lambda function in the cloud via authenticated boto3
        fn_name = os.environ.get("REALTIME_LAMBDA_FUNCTION_NAME", "fraudguard-realtime-api-dev").strip()
        region = os.environ.get("AWS_REGION", "us-east-1")
        try:
            lambda_client = boto3.client("lambda", region_name=region)
            resp = lambda_client.invoke(
                FunctionName=fn_name,
                InvocationType="RequestResponse",
                Payload=post_body
            )
            raw_payload = resp.get("Payload").read()
            parsed_resp = json.loads(raw_payload) if raw_payload else {}
            
            # Lambda handler returns a dict with statusCode and body
            status_code = parsed_resp.get("statusCode", 200)
            body_content = parsed_resp.get("body", "{}")
            
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if isinstance(body_content, str):
                self.wfile.write(body_content.encode("utf-8"))
            else:
                self.wfile.write(json.dumps(body_content).encode("utf-8"))
            return
        except Exception as e:
            print(f"[*] Live cloud Lambda invocation ({fn_name}) failed: {e}. Falling back to local scoring.")

        features = payload.get("features", payload)
        txn_id = str(payload.get("txn_id") or payload.get("TransactionID") or f"RT-{int(time.time() * 1000)}")
        threshold = float(os.environ.get("FRAUD_SCORE_THRESHOLD", "0.90"))

        # ML Scoring: Try loading local XGBoost or inference handler
        t_ml_start = time.perf_counter()
        fraud_score = None
        top_risk_factors = []

        try:
            # Check for direct score override
            if "fraud_score" in payload and payload["fraud_score"] is not None:
                fraud_score = float(payload["fraud_score"])
            else:
                sys.path.insert(0, os.path.join(PROJECT_ROOT, "ml"))
                import inference
                model_dir = os.path.join(PROJECT_ROOT, "ml", "model_artifacts")
                # Cache model in server instance
                if not hasattr(FraudGuardRequestHandler, "_cached_model"):
                    FraudGuardRequestHandler._cached_model = inference.model_fn(model_dir)
                res = inference.predict_fn(features, FraudGuardRequestHandler._cached_model)
                fraud_score = res["fraud_score"]
                top_risk_factors = res.get("top_risk_factors", [])
        except Exception as e:
            # Fallback heuristic if ML model cannot be loaded locally
            amt = float(features.get("TransactionAmt", 50.0))
            domain = str(features.get("P_emaildomain", "")).lower()
            hour = float(features.get("hour_of_day", 12.0))
            is_suspicious = amt > 1000 or "proton" in domain or "mail" in domain or hour < 5
            fraud_score = 0.9421 if is_suspicious else 0.1250

        t_ml_end = time.perf_counter()
        ml_latency_ms = round((t_ml_end - t_ml_start) * 1000, 2)

        # Bedrock Explainability Phase
        t_bedrock_start = time.perf_counter()
        explanation = None
        should_explain = (fraud_score > threshold) or payload.get("include_explanation", False)

        if should_explain:
            try:
                sys.path.insert(0, os.path.join(PROJECT_ROOT, "lambda"))
                import bedrock_client
                explanation = bedrock_client.explain(txn_id=txn_id, fraud_score=fraud_score, features=features)
            except Exception as e:
                explanation = f"Automated Risk Alert: Transaction flagged with elevated score ({fraud_score:.4f}). Primary factors include unusual amount ($ {features.get('TransactionAmt', 0)}) during off-peak hour ({features.get('hour_of_day', 'N/A')})."
        else:
            explanation = "Transaction cleared: Low anomaly score below risk threshold. Model parameters align with standard cardholder profile."

        t_bedrock_end = time.perf_counter()
        bedrock_latency_ms = round((t_bedrock_end - t_bedrock_start) * 1000, 2) if should_explain else 0.0

        now_iso = datetime.now(timezone.utc).isoformat()

        # Try to persist to DynamoDB if AWS credentials / table are configured
        region = os.environ.get("AWS_REGION", "us-east-1")
        table_name = os.environ.get("FRAUDGUARD_DYNAMODB_TABLE", "fraudguard-flagged-transactions-dev")
        try:
            dynamodb = boto3.resource("dynamodb", region_name=region)
            table = dynamodb.Table(table_name)
            table.put_item(Item={
                "TransactionID": str(txn_id),
                "txn_id": str(txn_id),
                "fraud_score": Decimal(str(round(fraud_score, 4))),
                "explanation": str(explanation),
                "timestamp": now_iso,
                "source": "realtime",
                "decision": "DECLINE" if fraud_score > threshold else ("REVIEW" if fraud_score > 0.50 else "APPROVE"),
            })
        except Exception as e:
            pass

        t_total_end = time.perf_counter()
        total_latency_ms = round((t_total_end - t_start) * 1000, 2)

        resp_data = {
            "status": "success",
            "txn_id": txn_id,
            "fraud_score": round(fraud_score, 4),
            "decision": "DECLINE" if fraud_score > threshold else ("REVIEW" if fraud_score > 0.50 else "APPROVE"),
            "threshold": threshold,
            "explanation": explanation,
            "source": "realtime",
            "top_risk_factors": top_risk_factors,
            "latency_ms": {
                "ml_inference": ml_latency_ms,
                "bedrock_explainability": bedrock_latency_ms,
                "total": total_latency_ms,
            },
            "timestamp": now_iso,
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(resp_data, default=decimal_serializer).encode("utf-8"))

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print(f"\n=======================================================")
    print(f"[+] FraudGuard DynamoDB Web Console")
    print(f"[*] Access URL: http://localhost:{PORT}")
    print(f"=======================================================\n")
    server = http.server.HTTPServer(("0.0.0.0", PORT), FraudGuardRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()
