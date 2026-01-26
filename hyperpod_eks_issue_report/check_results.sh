#!/bin/bash
# Helper script to check issue report results

if [ $# -lt 3 ]; then
    echo "Usage: $0 <s3-bucket> <cluster-name> <report-id>"
    echo ""
    echo "Example: $0 my-bucket my-cluster 20260126_143022"
    echo ""
    echo "To find your report-id, list the reports:"
    echo "  aws s3 ls s3://my-bucket/hyperpod-issue-reports/my-cluster/"
    exit 1
fi

S3_BUCKET=$1
CLUSTER_NAME=$2
REPORT_ID=$3

S3_PREFIX="hyperpod-issue-reports/${CLUSTER_NAME}/${REPORT_ID}"

echo "Checking HyperPod Issue Report Results"
echo "======================================="
echo "S3 Bucket: ${S3_BUCKET}"
echo "Cluster: ${CLUSTER_NAME}"
echo "Report ID: ${REPORT_ID}"
echo ""

# Check if report exists
echo "1. Checking if report exists..."
aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "   ✗ Report not found at s3://${S3_BUCKET}/${S3_PREFIX}/"
    exit 1
fi
echo "   ✓ Report found"
echo ""

# List all files
echo "2. Files in report:"
aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" --recursive | awk '{print "   " $4}'
echo ""

# Download and display summary
echo "3. Summary:"
SUMMARY=$(aws s3 cp "s3://${S3_BUCKET}/${S3_PREFIX}/summary.json" - 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "$SUMMARY" | python3 -m json.tool 2>/dev/null || echo "$SUMMARY"
    echo ""
    
    # Parse summary for quick stats
    TOTAL=$(echo "$SUMMARY" | python3 -c "import sys, json; print(json.load(sys.stdin)['total_nodes'])" 2>/dev/null)
    SUCCESS=$(echo "$SUMMARY" | python3 -c "import sys, json; print(json.load(sys.stdin)['successful'])" 2>/dev/null)
    FAILED=$(echo "$SUMMARY" | python3 -c "import sys, json; print(json.load(sys.stdin)['failed'])" 2>/dev/null)
    
    echo "4. Quick Stats:"
    echo "   Total nodes: ${TOTAL}"
    echo "   Successful: ${SUCCESS}"
    echo "   Failed: ${FAILED}"
    echo ""
    
    # Check for results
    RESULT_COUNT=$(aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/results/" 2>/dev/null | wc -l)
    echo "5. Result Files:"
    echo "   Found ${RESULT_COUNT} result tarballs"
    
    if [ "$RESULT_COUNT" -eq 0 ]; then
        echo ""
        echo "   ⚠️  No result files found!"
        echo ""
        echo "   Troubleshooting steps:"
        echo "   1. Check if commands succeeded in summary.json above"
        echo "   2. Look for 'Error' fields in the results array"
        echo "   3. If you see CommandId, get detailed output:"
        echo "      aws ssm get-command-invocation --command-id <command-id> --instance-id <instance-id>"
        echo "   4. Verify node IAM role has S3 write permissions"
        echo "   5. Check node can reach S3 endpoints"
    else
        echo ""
        echo "   Result files:"
        aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/results/" | awk '{print "   - " $4}'
        echo ""
        echo "   To download all results:"
        echo "   aws s3 sync s3://${S3_BUCKET}/${S3_PREFIX}/results/ ./results/"
        echo ""
        echo "   To extract a specific result:"
        echo "   tar -xzf results/<filename>.tar.gz"
    fi
else
    echo "   ✗ Could not read summary.json"
fi

echo ""
echo "Full S3 path: s3://${S3_BUCKET}/${S3_PREFIX}/"
