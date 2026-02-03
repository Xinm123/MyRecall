I will separate the client and server data storage locations and update the configuration as requested.

### 1. Update `openrecall/shared/config.py`
-   **Add New Settings**:
    -   `server_data_dir`: Defaults to `~/MRS` (Alias: `OPENRECALL_SERVER_DATA_DIR`).
    -   `client_data_dir`: Defaults to `~/MRC` (Alias: `OPENRECALL_CLIENT_DATA_DIR`).
-   **Update Path Logic**:
    -   Redirect `base_path` (used by server) to `server_data_dir`.
    -   Redirect `buffer_path` (used by client) to `client_data_dir/buffer`.
    -   Redirect `client_screenshots_path` to `client_data_dir/screenshots`.
    -   Server-side paths (`db`, `lancedb`, `fts`, `screenshots`, `models`) will automatically follow `server_data_dir`.
-   **Update Directory Creation**:
    -   Ensure both `server_data_dir` and `client_data_dir` (and their subdirectories) are created on startup.

### 2. Update `openrecall.env`
-   Add the new configuration options to the environment file with their default values, as requested.
    ```env
    OPENRECALL_SERVER_DATA_DIR=~/MRS
    OPENRECALL_CLIENT_DATA_DIR=~/MRC
    ```

### 3. Verify
-   Check that the configuration loads correctly and paths are resolved as expected.
