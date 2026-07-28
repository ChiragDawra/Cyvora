import os
import sys

# Mirrors how the Lambda runtime resolves `handler` - backend/ on the path.
sys.path.insert(0, os.path.dirname(__file__))

# boto3.resource(...) at module import time needs a region even just to construct.
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("IOC_TABLE", "cyvora-iocs-test")
