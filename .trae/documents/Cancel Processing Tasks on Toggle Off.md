I will implement the logic to cancel processing tasks when the "AI Processing" toggle is turned off.

### Plan

1.  **Modify `openrecall/server/database.py`**:
    *   Update `mark_task_completed` to only allow updating a task if its current status is `PROCESSING`. This prevents the background worker from overwriting a task that has been reset to `PENDING`.

2.  **Modify `openrecall/server/api.py`**:
    *   In the `update_config` route, detect when `ai_processing_enabled` is switched to `False`.
    *   Trigger `reset_stuck_tasks()` to immediately revert all `PROCESSING` tasks to `PENDING` in the database.

### Verification
I will verify the changes by creating a test script that simulates the toggle switch and checks if the task status updates correctly. I will ensure the `MyRecall` conda environment is activated before running any tests.
