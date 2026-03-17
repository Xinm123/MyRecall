## ADDED Requirements

### Requirement: Card header displays app, window, and device

Each frame card in the Grid `/` view MUST display `app_name`, `window_name`, and `device_name` in the card header area.

> **Acceptance impact**: Gate formula `处理来源字段UI展示完整率 = 100%` — spec aligns with p1-s3.md §3.11 table.

#### Scenario: All header fields present

- **WHEN** a frame has `app_name='Safari'`, `window_name='GitHub - main'`, `device_name='monitor_1'`
- **THEN** the card header MUST display all three values visibly

#### Scenario: Null app_name or window_name

- **WHEN** a frame has `app_name=NULL` or `window_name=NULL`
- **THEN** the card header MUST display a placeholder or empty state (not render as the literal string "null")

---

### Requirement: Card footer displays trigger and timestamp

Each frame card footer MUST display the `capture_trigger` type and `timestamp`.

#### Scenario: Trigger and time visible

- **WHEN** a frame has `capture_trigger='app_switch'` and `timestamp='2026-03-17T10:00:00Z'`
- **THEN** the card footer MUST display both the trigger type and a human-readable timestamp

---

### Requirement: Visual status distinction

Frame cards MUST visually distinguish between `pending`, `processing`, `completed`, and `failed` states.

#### Scenario: Completed frame appearance

- **WHEN** `frames.status='completed'`
- **THEN** the card MUST display a visually distinct completed state (e.g., color, icon, or label)

#### Scenario: Failed frame appearance

- **WHEN** `frames.status='failed'`
- **THEN** the card MUST display a visually distinct failed state that is different from completed, pending, and processing

#### Scenario: Pending frame appearance

- **WHEN** `frames.status='pending'`
- **THEN** the card MUST display a visually distinct pending state

#### Scenario: Processing frame appearance

- **WHEN** `frames.status='processing'`
- **THEN** the card MUST display a visually distinct processing state

---

### Requirement: OCR info display for completed frames

For frames with `status='completed'`, the card footer MUST display OCR engine name, `processed_at`, and `text_length`.

#### Scenario: OCR metadata visible on completed frame

- **WHEN** `frames.status='completed'` and `ocr_text.ocr_engine='rapidocr'` and `ocr_text.text_length=542`
- **THEN** the card footer MUST display the OCR engine name, processing completion time, and text character count

---

### Requirement: OCR text preview for completed frames

For frames with `status='completed'`, the card footer MUST display a preview of the extracted OCR text, truncated to 100 characters.

#### Scenario: Text preview within limit

- **WHEN** `ocr_text.text` is 80 characters long
- **THEN** the card footer MUST display the full text (no truncation)

#### Scenario: Text preview exceeds limit

- **WHEN** `ocr_text.text` is 250 characters long
- **THEN** the card footer MUST display only the first 100 characters followed by a truncation indicator (e.g., "…")

---

### Requirement: Error message display for failed frames

For frames with `status='failed'`, the card footer MUST display the `error_message`.

#### Scenario: Error message visible

- **WHEN** `frames.status='failed'` and `frames.error_message='OCR_EMPTY_TEXT'`
- **THEN** the card footer MUST display the error message

---

### Requirement: data-frame-status attribute for automation

Each frame card DOM element MUST include a `data-frame-status` attribute with the value set to the frame's status.

#### Scenario: Attribute present with correct value

- **WHEN** a frame card is rendered with `status='completed'`
- **THEN** the card's DOM element MUST have `data-frame-status="completed"`

#### Scenario: All four status values supported

- **WHEN** frames with `pending`, `processing`, `completed`, and `failed` statuses are rendered
- **THEN** each card MUST have the corresponding `data-frame-status` attribute value

---

### Requirement: Backend API returns OCR fields for Grid

The `/api/memories/recent` and `/api/memories/latest` endpoints MUST return OCR-related fields by LEFT JOIN-ing the `ocr_text` table.

#### Scenario: Completed frame includes OCR fields

- **WHEN** a completed frame is returned by `/api/memories/recent`
- **THEN** the response entry MUST include `text_source`, `text_length`, `ocr_text_preview` (first 100 chars), `ocr_engine`, `processed_at`, `capture_trigger`, `device_name`, and `error_message`

#### Scenario: Pending frame has null OCR fields

- **WHEN** a pending frame is returned by `/api/memories/recent`
- **THEN** the response entry MUST include `text_source=null`, `text_length=null`, `ocr_text_preview=null`, `ocr_engine=null` (LEFT JOIN results)

#### Scenario: Backward compatibility

- **WHEN** a client that does not expect OCR fields calls `/api/memories/recent`
- **THEN** the response MUST NOT break (new fields are purely additive)
