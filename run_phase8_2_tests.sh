#!/bin/bash
# Start server and run tests with longer timeout

eval "$(conda shell.bash hook)"
conda activate MyRecall

cd /Users/tiiny/Test/MyRecall/openrecall

echo "Starting server..."
python -m openrecall.server > /tmp/openrecall_server.log 2>&1 &
SERVER_PID=$!

# Wait for server to fully start (up to 30 seconds)
echo "Waiting for server to start (max 30 seconds)..."
for i in {1..30}; do
    if curl -s http://localhost:8083/api/config > /dev/null 2>&1; then
        echo "✓ Server is ready!"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""
echo "Running Phase 8.2 tests..."
python tests/test_phase8_2_quick.py

TEST_RESULT=$?

echo ""
echo "Killing server (PID: $SERVER_PID)"
kill $SERVER_PID 2>/dev/null

# Show server errors if any
if [ $TEST_RESULT -ne 0 ]; then
    echo ""
    echo "Server log (last 30 lines):"
    tail -30 /tmp/openrecall_server.log
fi

exit $TEST_RESULT
