import os
import sys

# Lets tests do `from common.schema import ...` / `from normalizer.handler import ...`
# the same way the Lambda runtime resolves them (ingestion/ on the path).
sys.path.insert(0, os.path.dirname(__file__))

# boto3.client(...)/resource(...) at module import time (see common/s3_landing.py,
# normalizer/handler.py) needs a region even just to construct the client object.
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
