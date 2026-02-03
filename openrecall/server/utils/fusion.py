from openrecall.server.schema import SemanticSnapshot

def build_fusion_text(snapshot: SemanticSnapshot) -> str:
    """
    Construct the single text string used for embedding using strict tagging.
    Format:
    [APP] {app_name}
    [TITLE] {window_title}
    [SCENE] {scene_tag}
    [ACTION] {action_tag}
    [CAPTION] {caption}
    [KEYWORDS] {comma_separated_keywords}
    [OCR_HEAD] {first_300_chars_of_ocr}
    """
    parts = []
    
    # [APP] {app_name}
    if snapshot.context.app_name:
        parts.append(f"[APP] {snapshot.context.app_name}")
    
    # [TITLE] {window_title}
    if snapshot.context.window_title:
        parts.append(f"[TITLE] {snapshot.context.window_title}")
    
    # [SCENE] {scene_tag}
    if snapshot.content.scene_tag:
        parts.append(f"[SCENE] {snapshot.content.scene_tag}")
        
    # [ACTION] {action_tag}
    if snapshot.content.action_tag:
        parts.append(f"[ACTION] {snapshot.content.action_tag}")
        
    # [CAPTION] {caption}
    if snapshot.content.caption:
        parts.append(f"[CAPTION] {snapshot.content.caption}")
        
    # [KEYWORDS] {comma_separated_keywords}
    if snapshot.content.keywords:
        parts.append(f"[KEYWORDS] {', '.join(snapshot.content.keywords)}")
        
    # [OCR_HEAD] {first_300_chars_of_ocr}
    if snapshot.content.ocr_head:
        parts.append(f"[OCR_HEAD] {snapshot.content.ocr_head}")
        
    return "\n".join(parts)
