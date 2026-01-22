from doctr.models import ocr_predictor

_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is None:
        _ocr = ocr_predictor(
            pretrained=True,
            det_arch="db_mobilenet_v3_large",
            reco_arch="crnn_mobilenet_v3_large",
        )
    return _ocr


def extract_text_from_image(image):
    ocr = _get_ocr()
    result = ocr([image])
    text = ""
    for page in result.pages:
        for block in page.blocks:
            for line in block.lines:
                for word in line.words:
                    text += word.value + " "
                text += "\n"
            text += "\n"
    return text
