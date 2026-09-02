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
